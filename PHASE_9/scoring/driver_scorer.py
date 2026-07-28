"""
scoring/driver_scorer.py

Step 5: Compute a 0-100 Driver Score per trip (and aggregated per driver)
from a combination of trip features and detected behaviour events.

Score = base_score
        - penalties (aggressive accel, harsh braking, overspeeding,
                      excessive idling, unsafe cornering)
        + bonuses (smooth acceleration, consistent speed,
                    fuel-efficient driving, low idle time)

Penalties and bonuses are normalized per hour of driving time so that
longer trips are not unfairly punished/rewarded purely for accumulating
more (or fewer) raw events than a short trip. Time-based normalization
is used instead of distance-based normalization because congested,
low-speed city driving covers little distance per unit time -- a
distance-based rate would inflate normal stop-and-go behaviour into an
apparent "high event rate" just because the denominator (km) is small.
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd

from config.settings import PROFILES, SCORING
from utils.exceptions import ScoringError
from utils.logger import get_logger

logger = get_logger(__name__)


class DriverScorer:
    """Computes weighted 0-100 driver scores from trip features + events."""

    def __init__(self):
        self._logger = logger

    # Trips shorter than this are floored to this duration before
    # normalizing event counts. Without a floor, a single harsh-brake
    # event on a 30-second trip would compute as an absurd "events per
    # hour" rate purely from the tiny time denominator.
    _MIN_NORMALIZATION_HOURS = 5.0 / 60.0  # 5 minutes

    def _events_per_hour(self, count: int, duration_s: float) -> float:
        effective_hours = max(duration_s / 3600.0, self._MIN_NORMALIZATION_HOURS)
        return count / effective_hours

    def score_trip(self, trip_features: pd.Series, event_counts: Dict[str, int]) -> Dict:
        """
        Compute the driver score for a single trip.

        Args:
            trip_features: one row (as a Series) from the trip feature
                table produced by TripFeatureExtractor.
            event_counts: dict of event_type -> count for this trip,
                as produced by BehaviorDetector.event_summary().

        Returns:
            dict with `score`, `penalty_breakdown`, `bonus_breakdown`,
            and `events_per_hour`.
        """
        try:
            distance_km = max(float(trip_features.get("distance_travelled_km", 0.0)), 0.0)
            duration_s = max(float(trip_features.get("trip_duration_s", 0.0)), 0.0)

            rate = {
                "aggressive_acceleration": self._events_per_hour(
                    event_counts.get("aggressive_acceleration", 0), duration_s),
                "harsh_braking": self._events_per_hour(
                    event_counts.get("harsh_braking", 0), duration_s),
                "overspeeding": self._events_per_hour(
                    event_counts.get("overspeeding", 0), duration_s),
                "excessive_idling": self._events_per_hour(
                    event_counts.get("excessive_idling", 0), duration_s),
                "sharp_cornering": self._events_per_hour(
                    event_counts.get("sharp_cornering", 0), duration_s),
                "rapid_lane_change": self._events_per_hour(
                    event_counts.get("rapid_lane_change", 0), duration_s),
            }

            penalty_breakdown = {
                "aggressive_acceleration": rate["aggressive_acceleration"] * SCORING.penalty_aggressive_acceleration,
                "harsh_braking": rate["harsh_braking"] * SCORING.penalty_harsh_braking,
                "overspeeding": rate["overspeeding"] * SCORING.penalty_overspeeding,
                "excessive_idling": rate["excessive_idling"] * SCORING.penalty_excessive_idling,
                "unsafe_cornering": rate["sharp_cornering"] * SCORING.penalty_unsafe_cornering,
                "rapid_lane_change": rate["rapid_lane_change"] * SCORING.penalty_rapid_lane_change,
            }
            total_penalty = min(sum(penalty_breakdown.values()), SCORING.max_penalty_cap)

            avg_accel = float(trip_features.get("avg_acceleration_mps2", 0.0) or 0.0)
            smooth_accel_bonus = (
                SCORING.bonus_smooth_acceleration * max(0.0, (2.0 - avg_accel))
                if avg_accel < 2.0 else 0.0
            )

            avg_speed = float(trip_features.get("avg_speed_kmh", 0.0) or 0.0)
            max_speed = float(trip_features.get("max_speed_kmh", 0.0) or 0.0)
            speed_consistency = 1 - (
                abs(max_speed - avg_speed) / max_speed if max_speed > 0 else 0
            )
            consistent_speed_bonus = SCORING.bonus_consistent_speed * max(0.0, speed_consistency)

            fuel_eff = trip_features.get("fuel_efficiency_km_per_l")
            fuel_bonus = 0.0
            if fuel_eff is not None and not (isinstance(fuel_eff, float) and np.isnan(fuel_eff)):
                if fuel_eff >= PROFILES.eco_min_fuel_efficiency_km_per_l:
                    fuel_bonus = SCORING.bonus_fuel_efficiency

            duration_s = max(float(trip_features.get("trip_duration_s", 0.0)), 1.0)
            idle_ratio = float(trip_features.get("idle_time_s", 0.0)) / duration_s
            low_idle_bonus = SCORING.bonus_low_idle_time * max(0.0, (1 - idle_ratio * 4))

            bonus_breakdown = {
                "smooth_acceleration": smooth_accel_bonus,
                "consistent_speed": consistent_speed_bonus,
                "fuel_efficiency": fuel_bonus,
                "low_idle_time": low_idle_bonus,
            }
            total_bonus = min(sum(bonus_breakdown.values()), SCORING.max_bonus_cap)

            score = SCORING.base_score - total_penalty + total_bonus
            score = float(np.clip(score, 0, 100))

            return {
                "score": round(score, 2),
                "penalty_breakdown": {k: round(v, 2) for k, v in penalty_breakdown.items()},
                "bonus_breakdown": {k: round(v, 2) for k, v in bonus_breakdown.items()},
                "total_penalty": round(total_penalty, 2),
                "total_bonus": round(total_bonus, 2),
                "events_per_hour": {k: round(v, 2) for k, v in rate.items()},
            }
        except Exception as exc:  # noqa: BLE001
            raise ScoringError(f"Failed to score trip: {exc}") from exc

    def score_all_trips(self, features_df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
        """
        Score every trip in `features_df`, matching events by
        `global_trip_id`. Returns `features_df` with score columns appended.
        """
        from detection.behavior_detector import BehaviorDetector

        detector = BehaviorDetector()
        rows = []
        for _, trip in features_df.iterrows():
            trip_events = events_df[events_df["global_trip_id"] == trip["global_trip_id"]] \
                if not events_df.empty else events_df
            counts = detector.event_summary(trip_events) if trip_events is not None else {}
            result = self.score_trip(trip, counts)
            rows.append({
                "global_trip_id": trip["global_trip_id"],
                "driver_score": result["score"],
                "total_penalty": result["total_penalty"],
                "total_bonus": result["total_bonus"],
            })

        scores_df = pd.DataFrame(rows)
        merged = features_df.merge(scores_df, on="global_trip_id", how="left")
        self._logger.info(
            "Scored %d trips (mean score=%.2f)", len(merged), merged["driver_score"].mean()
        )
        return merged

    def aggregate_driver_score(self, trip_scores: pd.DataFrame, veh_id) -> Optional[float]:
        """
        Aggregate a driver's overall score as the distance-weighted mean
        of their trip scores (longer trips carry proportionally more
        weight, matching how driving behaviour actually accumulates risk).
        """
        driver_trips = trip_scores[trip_scores["veh_id"] == veh_id]
        if driver_trips.empty:
            return None
        weights = driver_trips["distance_travelled_km"].clip(lower=0.01)
        weighted_score = np.average(driver_trips["driver_score"], weights=weights)
        return round(float(weighted_score), 2)

    def aggregate_driver_score_detail(self, trip_scores: pd.DataFrame, veh_id) -> Optional[Dict]:
        """
        Same as `aggregate_driver_score` but also returns the
        distance-weighted average penalty/bonus so API consumers get a
        real breakdown instead of just the final number.
        """
        driver_trips = trip_scores[trip_scores["veh_id"] == veh_id]
        if driver_trips.empty:
            return None
        weights = driver_trips["distance_travelled_km"].clip(lower=0.01)
        return {
            "driver_score": round(float(np.average(driver_trips["driver_score"], weights=weights)), 2),
            "total_penalty": round(float(np.average(driver_trips["total_penalty"], weights=weights)), 2),
            "total_bonus": round(float(np.average(driver_trips["total_bonus"], weights=weights)), 2),
        }
