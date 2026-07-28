"""
service_centre_engine.py
Phase 8 - Trip Intelligence Module

NEW MODULE (this revision)
---------------------------
Service Centre Recommendation
------------------------------
Recommends the nearest Tata Authorized Service Centre when:
  - Trip status is CAUTION or NO-GO, OR
  - A critical vehicle component is unhealthy
    (see config.RiskThresholds.critical_component_health_threshold)

Data is currently backed by a static JSON file
(data/service_centres.json) so it can be swapped for a real
dealer-locator API later WITHOUT changing this module's public interface
(`recommend(...)` keeps the same signature/return shape).

If real coordinates for the vehicle's current location are available
(source_coords on the TripRequest), distance is computed with the
haversine formula. Otherwise a deterministic mock distance/time is
generated (seeded on the vehicle_id + centre name) so results stay
reproducible for demos/tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from typing import List, Optional, Tuple

from config import settings
from utils import get_logger, haversine_km

logger = get_logger(__name__)

# Assumed average driving speed used to convert a haversine distance into an
# estimated travel time when no live routing call is made for the service
# centre leg (keeps this module lightweight / independent of RouteEngine).
_ASSUMED_AVG_SPEED_KMPH = 40.0


class ServiceCentreEngine:
    def __init__(self, data_path: str = settings.service_centre_data_path):
        self.data_path = data_path
        self._centres: Optional[List[dict]] = None

    # ------------------------------------------------------------------ #
    def _load_centres(self) -> List[dict]:
        if self._centres is not None:
            return self._centres
        if not os.path.exists(self.data_path):
            logger.warning("Service centre data file not found at %s; using empty list.", self.data_path)
            self._centres = []
            return self._centres
        try:
            with open(self.data_path, "r") as f:
                data = json.load(f)
            self._centres = data.get("service_centres", [])
            logger.info("Loaded %d service centres from %s.", len(self._centres), self.data_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load service centre data: %s", exc)
            self._centres = []
        return self._centres

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def recommend(
        self,
        vehicle_id: str,
        reason: str,
        current_coords: Optional[Tuple[float, float]] = None,
    ) -> Optional[dict]:
        """
        Returns dict: name, address, distance_km, estimated_travel_time_min,
        contact, reason, source_mode. Returns None if no centre data is
        available at all.
        """
        centres = self._load_centres()
        if not centres:
            return None

        if current_coords is not None:
            nearest = self._nearest_by_coords(centres, current_coords)
            distance_km = round(haversine_km(current_coords[0], current_coords[1],
                                              nearest["lat"], nearest["lon"]), 1)
            duration_min = round((distance_km / _ASSUMED_AVG_SPEED_KMPH) * 60, 1)
            source_mode = "mock-geo"  # real distance math, but over a mocked centre directory
        else:
            nearest, distance_km, duration_min = self._mock_nearest(vehicle_id, centres)
            source_mode = "mock"

        return {
            "name": nearest["name"],
            "address": nearest["address"],
            "distance_km": distance_km,
            "estimated_travel_time_min": duration_min,
            "contact": nearest.get("contact"),
            "reason": reason,
            "source_mode": source_mode,
        }

    # ------------------------------------------------------------------ #
    def _nearest_by_coords(self, centres: List[dict], coords: Tuple[float, float]) -> dict:
        return min(
            centres,
            key=lambda c: haversine_km(coords[0], coords[1], c["lat"], c["lon"]),
        )

    def _mock_nearest(self, vehicle_id: str, centres: List[dict]) -> Tuple[dict, float, float]:
        """Deterministic mock pick + distance/time when no coordinates are known."""
        seed = int(hashlib.sha256(f"service_centre::{vehicle_id}".encode()).hexdigest(), 16) % (10**6)
        rng = random.Random(seed)

        nearest = rng.choice(centres)
        distance_km = round(rng.uniform(2.0, 35.0), 1)
        duration_min = round((distance_km / _ASSUMED_AVG_SPEED_KMPH) * 60, 1)
        return nearest, distance_km, duration_min
