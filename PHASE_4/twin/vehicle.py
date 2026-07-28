"""
twin/vehicle.py
===============
VehicleTwin — Top-level Digital Twin that aggregates all component twins
(Engine, Battery, Fuel, Brake) into a single coherent vehicle representation.

Responsibilities
----------------
1. Own one instance of each component twin.
2. Forward data-row updates to every component twin.
3. Compute the overall vehicle health as a weighted composite.
4. Identify the critical (worst) component.
5. Expose the full vehicle state as a Pydantic VehicleState model.
6. Delegate future-degradation simulation to component twins and
   combine their projections into a unified timeline.

Overall Vehicle Health — Weighting
------------------------------------
Component weights reflect relative impact on overall vehicle operability:

    Engine  : 40%  — primary powertrain; failure = vehicle immobilised
    Battery : 30%  — critical for starting, ECU, and ADAS systems
    Fuel    : 20%  — affects drivability; managed by service intervals
    Brake   : 10%  — safety-critical but pad wear is predictable

These weights are intentionally exposed in this module (not hidden in config)
so reviewers can audit the decision easily.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from twin.battery import BatteryTwin
from twin.brake import BrakeTwin
from twin.engine import EngineTwin
from twin.fuel import FuelTwin
from utils.helpers import (
    classify_health,
    clamp,
    maintenance_status_label,
    utc_now_iso,
)
from utils.models import VehicleState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component weighting for overall vehicle health
# ---------------------------------------------------------------------------
_COMPONENT_WEIGHTS: Dict[str, float] = {
    "engine":  0.40,
    "battery": 0.30,
    "fuel":    0.20,
    "brake":   0.10,
}


class VehicleTwin:
    """
    Top-level Digital Twin for a single vehicle.

    Instantiated once per Vehicle_ID and updated on every synchronisation
    cycle by the Synchronizer service.

    Attributes
    ----------
    vehicle_id       : Unique identifier (e.g. 'Vehicle_0001')
    engine           : EngineTwin instance
    battery          : BatteryTwin instance
    fuel             : FuelTwin instance
    brake            : BrakeTwin instance
    _overall_health  : Weighted composite health [0–100]
    _overall_fp      : Aggregated failure probability [0–1]
    _health_class    : Categorical health label
    _trip_readiness  : Phase 2 trip_readiness score [0–100]
    _ml_health_score : Phase 2 ML health score [0–100]
    _failure_flag    : Phase 2 binary failure indicator
    _urgency         : Phase 3 urgency label
    _priority        : Phase 3 maintenance priority
    _book_within     : Days until service needed (Phase 3)
    _recommended_action : Phase 3 recommended action string
    _critical_component : Name of the worst-performing component
    _last_updated    : ISO-8601 timestamp of last synchronisation
    """

    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id

        # Component twins
        self.engine:  EngineTwin  = EngineTwin(vehicle_id)
        self.battery: BatteryTwin = BatteryTwin(vehicle_id)
        self.fuel:    FuelTwin    = FuelTwin(vehicle_id)
        self.brake:   BrakeTwin   = BrakeTwin(vehicle_id)

        # Vehicle-level fields (populated on first update)
        self._overall_health:  float = 100.0
        self._overall_fp:      float = 0.0
        self._health_class:    str   = "Excellent"
        self._trip_readiness:  float = 100.0
        self._ml_health_score: float = 100.0
        self._failure_flag:    int   = 0

        # Phase 3 fields
        self._urgency:            str = "LOW"
        self._priority:           str = "LOW"
        self._book_within:        int = 31
        self._recommended_action: str = "No action required"

        self._critical_component: Optional[str] = None
        self._last_updated: str = utc_now_iso()

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def update(self, row: pd.Series) -> None:
        """
        Synchronise the entire vehicle twin with a new data row.

        Update order:
          1. Update all component twins (they compute their own states).
          2. Compute overall vehicle health from component scores.
          3. Extract vehicle-level Phase 2 / Phase 3 fields.
          4. Identify the critical component.

        Parameters
        ----------
        row : Single-vehicle row from the merged Phase 2 + Phase 3 dataset
        """
        # 1 — Update component twins
        self.engine.update(row)
        self.battery.update(row)
        self.fuel.update(row)
        self.brake.update(row)

        # 2 — Overall vehicle health (weighted composite)
        component_scores = {
            "engine":  self.engine.health_score,
            "battery": self.battery.health_score,
            "fuel":    self.fuel.health_score,
            "brake":   self.brake.health_score,
        }
        self._overall_health = clamp(
            sum(
                score * _COMPONENT_WEIGHTS[name]
                for name, score in component_scores.items()
            )
        )

        # 3 — Aggregate failure probability (non-linear pooling)
        # P(at least one fails) ≈ 1 − Π(1 − P_i)  for small probabilities
        self._overall_fp = clamp(
            1.0 - (
                (1.0 - self.engine.failure_probability)
                * (1.0 - self.battery.failure_probability)
                * (1.0 - self.fuel.failure_probability)
                * (1.0 - self.brake.failure_probability)
            ),
            lo=0.0, hi=1.0,
        )

        # 4 — Vehicle-level Phase 2 fields
        self._health_class    = str(row.get("health_class",    self._health_class))
        self._trip_readiness  = clamp(float(row.get("trip_readiness",  self._trip_readiness)))
        self._ml_health_score = clamp(float(row.get("ml_health_score", self._ml_health_score)))
        self._failure_flag    = int(row.get("failure", self._failure_flag))

        # 5 — Vehicle-level Phase 3 fields
        self._urgency            = str(row.get("Urgency",            self._urgency))
        self._priority           = str(row.get("Maintenance_Priority", self._priority))
        self._book_within        = int(row.get("Book_Service_Within_Days", self._book_within))
        self._recommended_action = str(row.get("Recommended_Action", self._recommended_action))

        # 6 — Identify critical component
        self._critical_component = min(component_scores, key=component_scores.get)

        self._last_updated = utc_now_iso()
        logger.debug(
            "VehicleTwin [%s] updated → overall_health=%.1f, critical=%s",
            self.vehicle_id, self._overall_health, self._critical_component,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the full vehicle twin state to a nested dictionary."""
        return {
            "vehicle_id":                   self.vehicle_id,
            "timestamp":                    self._last_updated,
            "overall_health":               round(self._overall_health, 2),
            "overall_failure_probability":  round(self._overall_fp, 4),
            "overall_rul_cycles":           self.engine.rul_cycles,
            "overall_rul_km":               self.engine.rul_km,
            "health_class":                 self._health_class,
            "trip_readiness":               round(self._trip_readiness, 2),
            "ml_health_score":              round(self._ml_health_score, 2),
            "failure_flag":                 self._failure_flag,
            "urgency":                      self._urgency,
            "maintenance_priority":         self._priority,
            "book_service_within_days":     self._book_within,
            "recommended_action":           self._recommended_action,
            "critical_component":           self._critical_component,
            "last_updated":                 self._last_updated,
            # Nested component states
            "engine":                       self.engine.to_dict(),
            "battery":                      self.battery.to_dict(),
            "fuel":                         self.fuel.to_dict(),
            "brake":                        self.brake.to_dict(),
        }

    def to_model(self) -> VehicleState:
        """Return a fully validated Pydantic VehicleState model."""
        d = self.to_dict()
        d["engine"]  = self.engine.to_model()
        d["battery"] = self.battery.to_model()
        d["fuel"]    = self.fuel.to_model()
        d["brake"]   = self.brake.to_model()
        return VehicleState(**d)

    def simulate(self, days: int) -> Dict[str, Any]:
        """
        Project the full vehicle state forward by `days` days.

        Delegates simulation to each component twin, then merges the
        per-day results into a unified vehicle-level timeline.

        Parameters
        ----------
        days : Simulation horizon (1–365)

        Returns
        -------
        Dict with metadata and a 'trajectory' list of daily snapshots.
        """
        from datetime import datetime, timedelta, timezone
        from utils.models import SimulationDataPoint, SimulationResult

        e_sim = self.engine.simulate(days)
        b_sim = self.battery.simulate(days)
        f_sim = self.fuel.simulate(days)
        k_sim = self.brake.simulate(days)

        trajectory: List[SimulationDataPoint] = []
        projected_failure_day: Optional[int] = None

        for i in range(days):
            eh = e_sim[i]["engine_health"]
            bh = b_sim[i]["battery_health"]
            fh = f_sim[i]["fuel_health"]
            kh = k_sim[i]["brake_health"]

            vh = clamp(
                eh * _COMPONENT_WEIGHTS["engine"]
                + bh * _COMPONENT_WEIGHTS["battery"]
                + fh * _COMPONENT_WEIGHTS["fuel"]
                + kh * _COMPONENT_WEIGHTS["brake"]
            )

            # NOTE: EngineTwin.simulate() does not emit a "failure_probability"
            # key per day (only BatteryTwin, FuelTwin, BrakeTwin do), so this
            # fallback estimate is always the one used for the engine term.
            # It MUST be parenthesised as a whole before being subtracted from
            # 1.0 - previously the ternary bound tighter than the surrounding
            # subtraction, so the raw fallback (a *failure* estimate) was used
            # directly as if it were a *survival* term, inverting its meaning
            # and inflating the composite failure probability to ~90%+ on
            # every simulated day regardless of actual vehicle health.
            engine_fp = (
                e_sim[i]["failure_probability"]
                if "failure_probability" in e_sim[i]
                else (100 - eh) / 100 * 0.5
            )

            fp = clamp(
                1.0 - (
                    (1.0 - engine_fp)
                    * (1.0 - b_sim[i].get("failure_probability", (100 - bh) / 100 * 0.3))
                    * (1.0 - f_sim[i]["failure_probability"])
                    * (1.0 - k_sim[i]["failure_probability"])
                ),
                lo=0.0, hi=1.0,
            )

            day_num   = e_sim[i]["day"]
            day_date  = e_sim[i]["date"]
            rul_c     = e_sim[i]["rul_cycles"]
            rul_km    = self.engine.rul_km - day_num * 20  # ~20 km/day proxy

            # Mark first day vehicle health drops below 40 as projected failure
            if projected_failure_day is None and vh < 40.0:
                projected_failure_day = day_num

            status = maintenance_status_label(
                max(1, self._book_within - day_num),
                self._urgency,
            )

            trajectory.append(SimulationDataPoint(
                day=day_num,
                date=day_date,
                engine_health=round(eh, 2),
                battery_health=round(bh, 2),
                fuel_health=round(fh, 2),
                brake_health=round(kh, 2),
                vehicle_health=round(vh, 2),
                failure_probability=round(fp, 4),
                rul_cycles=max(0, rul_c),
                rul_km=max(0, rul_km),
                maintenance_status=status,
            ))

        return SimulationResult(
            vehicle_id=self.vehicle_id,
            simulation_days=days,
            generated_at=utc_now_iso(),
            baseline_health=round(self._overall_health, 2),
            projected_failure_day=projected_failure_day,
            trajectory=trajectory,
        )

    def health_status(self) -> str:
        return classify_health(self._overall_health)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def overall_health(self) -> float:
        return self._overall_health

    @property
    def overall_failure_probability(self) -> float:
        return self._overall_fp

    @property
    def critical_component(self) -> Optional[str]:
        return self._critical_component

    @property
    def urgency(self) -> str:
        return self._urgency

    @property
    def book_service_within_days(self) -> int:
        return self._book_within

    # ------------------------------------------------------------------
    # History helpers (delegated to engine as primary timeline)
    # ------------------------------------------------------------------

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Return merged history across all component twins.
        Aligns by index (same update call order).
        """
        e_hist = self.engine.get_history()
        b_hist = self.battery.get_history()
        f_hist = self.fuel.get_history()
        k_hist = self.brake.get_history()
        length = min(len(e_hist), len(b_hist), len(f_hist), len(k_hist))

        merged = []
        for i in range(length):
            merged.append({
                "timestamp":           e_hist[i]["timestamp"],
                "engine_health":       e_hist[i]["engine_health"],
                "battery_health":      b_hist[i]["battery_health"],
                "fuel_health":         f_hist[i]["fuel_health"],
                "brake_health":        k_hist[i]["brake_health"],
                "vehicle_health":      round(
                    e_hist[i]["engine_health"]  * _COMPONENT_WEIGHTS["engine"]
                    + b_hist[i]["battery_health"] * _COMPONENT_WEIGHTS["battery"]
                    + f_hist[i]["fuel_health"]    * _COMPONENT_WEIGHTS["fuel"]
                    + k_hist[i]["brake_health"]   * _COMPONENT_WEIGHTS["brake"],
                    2,
                ),
                "failure_probability": e_hist[i]["failure_probability"],
                "rul_cycles":          e_hist[i]["rul_cycles"],
                "rul_km":              self.engine.rul_km,
                "temperature":         e_hist[i]["temperature"],
                "rpm":                 e_hist[i]["rpm"],
                "battery_voltage":     b_hist[i]["voltage"],
            })
        return merged

    def __repr__(self) -> str:
        return (
            f"VehicleTwin(id={self.vehicle_id}, "
            f"health={self._overall_health:.1f}, "
            f"class={self._health_class}, "
            f"critical={self._critical_component})"
        )
