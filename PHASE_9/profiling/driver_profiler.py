"""
profiling/driver_profiler.py

Step 4: Assign a Driver Behaviour Profile using a weighted combination
of the driver score (Step 5) and supporting signals (fuel efficiency,
risk-event rate). The profiler depends on DriverScorer, so scoring
technically executes first internally even though it's presented as
Step 4 in the spec -- both are exposed independently so callers can
use either module standalone.

Categories: Safe Driver, Eco Driver, Normal Driver, Aggressive Driver,
High Risk Driver.
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd

from config.settings import PROFILE_LABELS, PROFILES
from utils.exceptions import ScoringError
from utils.logger import get_logger

logger = get_logger(__name__)


class DriverProfiler:
    """Assigns a categorical behaviour profile to each trip and each driver."""

    def __init__(self):
        self._logger = logger

    def _risk_events_per_hour(self, trip_row: pd.Series) -> float:
        duration_s = max(float(trip_row.get("trip_duration_s", 0.0)), 0.0)
        effective_hours = max(duration_s / 3600.0, 5.0 / 60.0)  # 5-minute floor
        risk_events = (
            trip_row.get("num_harsh_brakes", 0)
            + trip_row.get("num_accelerations", 0)
            + trip_row.get("num_sharp_turns", 0)
        )
        return risk_events / effective_hours

    def classify_trip(self, trip_row: pd.Series) -> str:
        """
        Classify a single scored trip row into one of the 5 profile
        categories using score bands, with a fuel-efficiency and
        risk-event override to distinguish Eco vs Safe drivers (both
        can have high scores, but Eco drivers specifically optimize
        for fuel economy) and to catch High Risk drivers whose score
        band overlaps with Aggressive.
        """
        score = float(trip_row.get("driver_score", 0.0) or 0.0)
        fuel_eff = trip_row.get("fuel_efficiency_km_per_l")
        risk_rate = self._risk_events_per_hour(trip_row)
        is_fuel_efficient = (
            fuel_eff is not None
            and not (isinstance(fuel_eff, float) and np.isnan(fuel_eff))
            and fuel_eff >= PROFILES.eco_min_fuel_efficiency_km_per_l
        )

        if risk_rate >= PROFILES.high_risk_events_per_hour and score < PROFILES.normal_driver_min_score:
            return PROFILE_LABELS["HIGH_RISK"]

        if score >= PROFILES.eco_driver_min_score:
            # Any driver scoring in the "safe" range or above who is
            # also fuel-efficient is specifically an Eco Driver; the
            # rest of that band are Safe Drivers.
            if is_fuel_efficient:
                return PROFILE_LABELS["ECO"]
            return PROFILE_LABELS["SAFE"]

        if score >= PROFILES.normal_driver_min_score:
            return PROFILE_LABELS["NORMAL"]

        if score >= PROFILES.aggressive_driver_min_score:
            return PROFILE_LABELS["AGGRESSIVE"]

        return PROFILE_LABELS["HIGH_RISK"]

    def classify_all_trips(self, scored_trips: pd.DataFrame) -> pd.DataFrame:
        """Append a `driver_profile` column to a DataFrame of scored trips."""
        if "driver_score" not in scored_trips.columns:
            raise ScoringError("scored_trips must contain a 'driver_score' column; run DriverScorer first.")

        result = scored_trips.copy()
        result["driver_profile"] = result.apply(self.classify_trip, axis=1)
        self._logger.info(
            "Trip profile distribution: %s", result["driver_profile"].value_counts().to_dict()
        )
        return result

    def profile_driver(self, scored_trips: pd.DataFrame, veh_id) -> Dict:
        """
        Aggregate a single driver's overall profile across all their
        trips: the modal (most frequent) trip-level profile, weighted
        by distance travelled, plus summary statistics.
        """
        driver_trips = scored_trips[scored_trips["veh_id"] == veh_id]
        if driver_trips.empty:
            return {
                "veh_id": veh_id, "profile": None, "trip_count": 0,
                "avg_score": None, "total_distance_km": 0.0,
            }

        if "driver_profile" not in driver_trips.columns:
            driver_trips = driver_trips.copy()
            driver_trips["driver_profile"] = driver_trips.apply(self.classify_trip, axis=1)

        weights = driver_trips["distance_travelled_km"].clip(lower=0.01)
        weighted_votes = (
            driver_trips.assign(weight=weights)
            .groupby("driver_profile")["weight"]
            .sum()
            .sort_values(ascending=False)
        )
        dominant_profile = weighted_votes.index[0]

        return {
            "veh_id": veh_id,
            "profile": dominant_profile,
            "trip_count": int(len(driver_trips)),
            "avg_score": round(float(np.average(driver_trips["driver_score"], weights=weights)), 2),
            "total_distance_km": round(float(driver_trips["distance_travelled_km"].sum()), 2),
            "profile_distribution": {
                k: round(float(v), 2) for k, v in weighted_votes.to_dict().items()
            },
        }

    def profile_all_drivers(self, scored_trips: pd.DataFrame) -> pd.DataFrame:
        """Profile every unique driver (veh_id) present in scored_trips."""
        if "driver_profile" not in scored_trips.columns:
            scored_trips = self.classify_all_trips(scored_trips)

        profiles = [self.profile_driver(scored_trips, veh_id) for veh_id in scored_trips["veh_id"].unique()]
        result = pd.DataFrame(profiles)
        self._logger.info("Profiled %d drivers", len(result))
        return result
