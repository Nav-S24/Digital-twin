"""
services/synchronizer.py
=========================
Synchronizer — Central registry and orchestration layer for all VehicleTwin
instances.

Responsibilities
----------------
1. Build and cache one VehicleTwin per Vehicle_ID on startup.
2. Drive the synchronisation cycle: read merged DataFrame → enrich rows →
   push updates into each twin.
3. Expose thread-safe accessors used by the FastAPI route handlers.
4. Support partial updates (single vehicle) for future live-telemetry feeds.

Architecture note
-----------------
All twins live in a single in-memory dict:
    _twins: Dict[str, VehicleTwin]

When a database layer is added, this dict becomes a write-through cache and
the Synchronizer flushes deltas to the DB at the end of each cycle.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

import pandas as pd

from services.data_loader import get_merged_dataframe, get_vehicle_row, list_vehicle_ids
from services.state_estimator import StateEstimator
from twin.vehicle import VehicleTwin
from utils.helpers import utc_now_iso
from utils.models import VehicleState

logger = logging.getLogger(__name__)


class Synchronizer:
    """
    Singleton-style orchestrator that owns all VehicleTwin instances.

    Thread-safety
    -------------
    A reentrant lock (_lock) protects the _twins dict.  FastAPI is async
    but twin updates are CPU-bound; the lock prevents races if background
    refresh tasks are added later.

    Usage
    -----
        sync = Synchronizer()
        sync.initialise()                    # loads all twins on startup
        twin = sync.get_twin("Vehicle_0001") # read a specific twin
        state = sync.get_state("Vehicle_0001")
        all_states = sync.get_all_states()
    """

    def __init__(self) -> None:
        self._twins:     Dict[str, VehicleTwin] = {}
        self._estimator: StateEstimator          = StateEstimator()
        self._lock:      threading.RLock         = threading.RLock()
        self._initialised: bool                  = False
        self._last_sync:   str                   = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """
        Load all vehicle data and initialise every VehicleTwin.
        Called once at FastAPI startup (lifespan event).
        """
        if self._initialised:
            logger.warning("Synchronizer.initialise() called more than once — skipping.")
            return

        logger.info("Synchronizer: loading merged dataset …")
        df = get_merged_dataframe()

        # Fit StateEstimator on full fleet
        self._estimator.fit(df)

        logger.info("Synchronizer: building %d VehicleTwin instances …", len(df))
        with self._lock:
            for _, row in df.iterrows():
                vid  = str(row["Vehicle_ID"])
                twin = VehicleTwin(vid)
                enriched_row = self._estimator.enrich(row)
                twin.update(enriched_row)
                self._twins[vid] = twin

        self._initialised = True
        self._last_sync   = utc_now_iso()
        logger.info("Synchronizer: initialised with %d vehicles. Ready.", len(self._twins))

    def refresh(self) -> None:
        """
        Re-read the merged DataFrame and push updates to all twins.
        Call this if the CSV files are updated (e.g. new Phase 3 output).
        Clears the LRU cache first to pick up file changes.
        """
        from services.data_loader import get_merged_dataframe
        get_merged_dataframe.cache_clear()

        df = get_merged_dataframe()
        self._estimator.fit(df)

        with self._lock:
            for _, row in df.iterrows():
                vid = str(row["Vehicle_ID"])
                enriched = self._estimator.enrich(row)
                if vid in self._twins:
                    self._twins[vid].update(enriched)
                else:
                    twin = VehicleTwin(vid)
                    twin.update(enriched)
                    self._twins[vid] = twin

        self._last_sync = utc_now_iso()
        logger.info("Synchronizer: refreshed %d vehicles at %s", len(self._twins), self._last_sync)

    def update_single(self, vehicle_id: str, row: pd.Series) -> None:
        """
        Update a single vehicle twin from a new data row.
        Designed for future live-telemetry ingestion (MQTT/Kafka).

        Parameters
        ----------
        vehicle_id : Target vehicle identifier
        row        : New sensor reading row
        """
        enriched = self._estimator.enrich(row)
        with self._lock:
            if vehicle_id not in self._twins:
                self._twins[vehicle_id] = VehicleTwin(vehicle_id)
            self._twins[vehicle_id].update(enriched)
        logger.debug("Synchronizer: single update for %s", vehicle_id)

    # ------------------------------------------------------------------
    # Read accessors (used by API route handlers)
    # ------------------------------------------------------------------

    def get_twin(self, vehicle_id: str) -> Optional[VehicleTwin]:
        """Return the VehicleTwin for the given ID, or None if not found."""
        with self._lock:
            return self._twins.get(vehicle_id)

    def get_state(self, vehicle_id: str) -> Optional[VehicleState]:
        """Return a validated VehicleState Pydantic model for one vehicle."""
        twin = self.get_twin(vehicle_id)
        return twin.to_model() if twin else None

    def get_all_states(
        self,
        page: int = 1,
        per_page: int = 50,
        health_class: Optional[str] = None,
        urgency: Optional[str] = None,
        sort_by: str = "overall_health",
        ascending: bool = True,
    ) -> Dict:
        """
        Return a paginated, filterable list of all vehicle states.

        Parameters
        ----------
        page         : 1-based page number
        per_page     : Items per page (max 500)
        health_class : Filter by health class (Excellent/Good/Warning/Critical)
        urgency      : Filter by urgency (LOW/MEDIUM/CRITICAL)
        sort_by      : Field to sort by (overall_health, vehicle_id, etc.)
        ascending    : Sort direction

        Returns
        -------
        Dict with pagination metadata and 'items' list of VehicleState dicts
        """
        with self._lock:
            twins = list(self._twins.values())

        # Apply filters
        if health_class:
            twins = [t for t in twins if t._health_class.lower() == health_class.lower()]
        if urgency:
            twins = [t for t in twins if t._urgency.upper() == urgency.upper()]

        # Sort
        reverse = not ascending
        if sort_by == "vehicle_id":
            twins.sort(key=lambda t: t.vehicle_id, reverse=reverse)
        elif sort_by == "overall_health":
            twins.sort(key=lambda t: t.overall_health, reverse=reverse)
        elif sort_by == "failure_probability":
            twins.sort(key=lambda t: t.overall_failure_probability, reverse=reverse)
        elif sort_by == "book_service_within_days":
            twins.sort(key=lambda t: t.book_service_within_days, reverse=reverse)

        total = len(twins)
        per_page = min(per_page, 500)
        start = (page - 1) * per_page
        end   = start + per_page
        page_items = twins[start:end]

        return {
            "total":    total,
            "page":     page,
            "per_page": per_page,
            "items":    [t.to_dict() for t in page_items],
        }

    def get_history(self, vehicle_id: str) -> Optional[List[Dict]]:
        """Return merged history for a vehicle, or None if not found."""
        twin = self.get_twin(vehicle_id)
        return twin.get_history() if twin else None

    def get_component_states(self, vehicle_id: str) -> Optional[Dict]:
        """Return all four component twin dicts for a vehicle."""
        twin = self.get_twin(vehicle_id)
        if not twin:
            return None
        return {
            "vehicle_id": vehicle_id,
            "engine":     twin.engine.to_dict(),
            "battery":    twin.battery.to_dict(),
            "fuel":       twin.fuel.to_dict(),
            "brake":      twin.brake.to_dict(),
        }

    def get_risk_summary(self, vehicle_id: str) -> Optional[Dict]:
        """Return failure risk digest for a vehicle."""
        twin = self.get_twin(vehicle_id)
        if not twin:
            return None
        row = get_vehicle_row(vehicle_id)
        return {
            "vehicle_id":              vehicle_id,
            "timestamp":               twin._last_updated,
            "failure_probability":     round(twin.overall_failure_probability, 4),
            "failure_risk_percentage": f"{twin.overall_failure_probability * 100:.1f}%",
            "urgency":                 twin._urgency,
            "top_risk_sensor":         twin.engine._top_risk_sensor,
            "top_risk_shap_value":     float(row.get("SHAP_Value", 0.0)) if row is not None else None,
            "affected_system":         twin.engine._affected_system,
            "book_service_within_days": twin.book_service_within_days,
            "maintenance_priority":    twin._priority,
            "recommended_action":      twin._recommended_action,
            "reason":                  twin.engine._shap_explanation,
        }

    def get_rul_summary(self, vehicle_id: str) -> Optional[Dict]:
        """Return RUL digest for a vehicle."""
        twin = self.get_twin(vehicle_id)
        if not twin:
            return None
        return {
            "vehicle_id":  vehicle_id,
            "timestamp":   twin._last_updated,
            "rul_cycles":  twin.engine.rul_cycles,
            "rul_km":      twin.engine.rul_km,
            "urgency":     twin._urgency,
            "health_class": twin._health_class,
        }

    def fleet_summary(self) -> Dict:
        """Return aggregate fleet-level statistics."""
        with self._lock:
            twins = list(self._twins.values())

        if not twins:
            return {}

        healths = [t.overall_health for t in twins]
        fps     = [t.overall_failure_probability for t in twins]

        return {
            "total_vehicles":          len(twins),
            "last_sync":               self._last_sync,
            "mean_overall_health":     round(sum(healths) / len(healths), 2),
            "mean_failure_probability": round(sum(fps) / len(fps), 4),
            "critical_count":          sum(1 for t in twins if t._health_class == "Critical"),
            "warning_count":           sum(1 for t in twins if t._health_class == "Warning"),
            "good_count":              sum(1 for t in twins if t._health_class == "Good"),
            "excellent_count":         sum(1 for t in twins if t._health_class == "Excellent"),
            "urgent_service_count":    sum(1 for t in twins if t._urgency == "CRITICAL"),
            "service_within_7days":    sum(1 for t in twins if t.book_service_within_days <= 7),
        }

    def list_vehicle_ids(self) -> List[str]:
        """Return sorted list of all loaded Vehicle_IDs."""
        with self._lock:
            return sorted(self._twins.keys())

    @property
    def total_vehicles(self) -> int:
        with self._lock:
            return len(self._twins)

    @property
    def is_ready(self) -> bool:
        return self._initialised


# ---------------------------------------------------------------------------
# Application-level singleton
# ---------------------------------------------------------------------------

_synchronizer: Optional[Synchronizer] = None


def get_synchronizer() -> Synchronizer:
    """
    Return (and lazily create) the application-level Synchronizer singleton.
    FastAPI dependency injection uses this function.
    """
    global _synchronizer
    if _synchronizer is None:
        _synchronizer = Synchronizer()
    return _synchronizer
