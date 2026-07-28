"""
detection/behavior_detector.py

Step 3: Event-level behaviour detection.

Unlike feature_engineering (which produces trip-level aggregate counts),
this module returns a row PER DETECTED EVENT with its timestamp, GPS
location, severity, and context (speed / hour / road type). This
event log powers:
    - The Plotly event-timeline visualizations (Step 9)
    - Context-aware coaching messages (Step 6), e.g. "you brake harshly
      mostly in city traffic" vs "...mostly on the highway"

Detected behaviours:
    - Aggressive Acceleration : acceleration > threshold
    - Harsh Braking           : deceleration < threshold
    - Excessive Idling        : speed == 0 (engine on) for > threshold seconds
    - Overspeeding            : speed > configurable speed limit
    - Rapid Lane Change       : large heading change in a short time at speed
    - Sharp Cornering         : lateral acceleration > threshold
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from config.settings import THRESHOLDS
from feature_engineering.feature_extractor import TripFeatureExtractor
from utils.exceptions import InsufficientDataError
from utils.logger import get_logger

logger = get_logger(__name__)

EVENT_COLUMNS = [
    "veh_id", "trip_id", "global_trip_id", "event_type", "timestamp",
    "latitude", "longitude", "speed_kmh", "magnitude", "severity",
    "road_context", "hour_of_day",
]


@dataclass(frozen=True)
class EventType:
    AGGRESSIVE_ACCELERATION = "aggressive_acceleration"
    HARSH_BRAKING = "harsh_braking"
    EXCESSIVE_IDLING = "excessive_idling"
    OVERSPEEDING = "overspeeding"
    RAPID_LANE_CHANGE = "rapid_lane_change"
    SHARP_CORNERING = "sharp_cornering"


class BehaviorDetector:
    """Detects discrete unsafe/inefficient driving events within a trip."""

    def __init__(self, speed_limit_kmh: Optional[float] = None):
        self._extractor = TripFeatureExtractor()
        self.speed_limit_kmh = speed_limit_kmh or THRESHOLDS.default_speed_limit_kmh
        self._logger = logger

    def _road_context(self, speed_kmh: float) -> str:
        if speed_kmh >= THRESHOLDS.highway_speed_floor_kmh:
            return "highway"
        if speed_kmh <= THRESHOLDS.city_speed_ceiling_kmh:
            return "city"
        return "arterial"

    def _severity(self, magnitude: float, threshold: float) -> str:
        """Classify severity as a ratio of how far magnitude exceeds threshold."""
        ratio = abs(magnitude / threshold) if threshold else 1.0
        if ratio >= 1.75:
            return "severe"
        if ratio >= 1.25:
            return "moderate"
        return "mild"

    def detect_aggressive_acceleration(self, kdf: pd.DataFrame) -> pd.DataFrame:
        mask = kdf["acceleration_mps2"] >= THRESHOLDS.aggressive_acceleration_mps2
        return self._build_events(
            kdf[mask], EventType.AGGRESSIVE_ACCELERATION,
            magnitude_col="acceleration_mps2", threshold=THRESHOLDS.aggressive_acceleration_mps2,
        )

    def detect_harsh_braking(self, kdf: pd.DataFrame) -> pd.DataFrame:
        mask = kdf["acceleration_mps2"] <= THRESHOLDS.harsh_braking_mps2
        return self._build_events(
            kdf[mask], EventType.HARSH_BRAKING,
            magnitude_col="acceleration_mps2", threshold=THRESHOLDS.harsh_braking_mps2,
        )

    def detect_excessive_idling(self, kdf: pd.DataFrame) -> pd.DataFrame:
        """
        Groups contiguous idle rows (speed <= idle_speed_kmh) into idle
        sessions and flags sessions exceeding the excessive-idle threshold.
        """
        idle_mask = kdf["speed_kmh"] <= THRESHOLDS.idle_speed_kmh
        session_id = (idle_mask != idle_mask.shift(1)).cumsum()
        events = []
        for _, session in kdf[idle_mask].groupby(session_id[idle_mask]):
            duration = session["dt_s"].sum()
            if duration >= THRESHOLDS.excessive_idle_seconds:
                row = session.iloc[len(session) // 2]  # midpoint of the idle session
                events.append({
                    "veh_id": row["veh_id"], "trip_id": row["trip_id"],
                    "global_trip_id": row["global_trip_id"],
                    "event_type": EventType.EXCESSIVE_IDLING,
                    "timestamp": row["timestamp"], "latitude": row["latitude"],
                    "longitude": row["longitude"], "speed_kmh": row["speed_kmh"],
                    "magnitude": float(duration), "severity": self._severity(
                        duration, THRESHOLDS.excessive_idle_seconds
                    ),
                    "road_context": self._road_context(row["speed_kmh"]),
                    "hour_of_day": row["hour_of_day"],
                })
        return pd.DataFrame(events, columns=EVENT_COLUMNS)

    def detect_overspeeding(self, kdf: pd.DataFrame, speed_limit: Optional[float] = None) -> pd.DataFrame:
        """
        Flags speeding relative to a road-context-aware limit rather
        than one flat number: VED has no per-road OSM speed-limit
        lookup, so we approximate using the same highway/city/arterial
        split as `_road_context`. This avoids flagging legitimate
        100 km/h highway cruising as "overspeeding" against a city-biased
        default limit. When `speed_limit` is explicitly provided (e.g.
        by the Trip Intelligence module for a known route), it overrides
        the context-based limit everywhere.
        """
        if speed_limit is not None:
            threshold = speed_limit + THRESHOLDS.overspeed_tolerance_kmh
            mask = kdf["speed_kmh"] > threshold
            return self._build_events(
                kdf[mask], EventType.OVERSPEEDING, magnitude_col="speed_kmh", threshold=threshold,
            )

        limits = kdf["speed_kmh"].apply(
            lambda s: THRESHOLDS.highway_speed_limit_kmh if s >= THRESHOLDS.highway_speed_floor_kmh
            else (THRESHOLDS.city_speed_limit_kmh if s <= THRESHOLDS.city_speed_ceiling_kmh
                  else self.speed_limit_kmh)
        )
        thresholds = limits + THRESHOLDS.overspeed_tolerance_kmh
        mask = kdf["speed_kmh"] > thresholds
        subset = kdf[mask]
        if subset.empty:
            return pd.DataFrame(columns=EVENT_COLUMNS)
        out = pd.DataFrame({
            "veh_id": subset["veh_id"], "trip_id": subset["trip_id"],
            "global_trip_id": subset["global_trip_id"], "event_type": EventType.OVERSPEEDING,
            "timestamp": subset["timestamp"], "latitude": subset["latitude"],
            "longitude": subset["longitude"], "speed_kmh": subset["speed_kmh"],
            "magnitude": subset["speed_kmh"] - limits[mask], "hour_of_day": subset["hour_of_day"],
        })
        out["severity"] = (subset["speed_kmh"] - thresholds[mask]).apply(
            lambda excess: "severe" if excess >= 15 else ("moderate" if excess >= 5 else "mild")
        )
        out["road_context"] = subset["speed_kmh"].apply(self._road_context)
        return out[EVENT_COLUMNS]

    def detect_rapid_lane_changes(self, kdf: pd.DataFrame) -> pd.DataFrame:
        """
        Approximates a lane change as a brief heading deviation occurring
        at highway/arterial speed (above `highway_speed_floor_kmh`).

        NOTE ON DESIGN: lateral_accel = speed_mps * heading_rate_rad_s by
        construction (see _compute_point_kinematics), so a naive filter
        of "heading_change >= X AND lateral_accel < sharp_corner_threshold"
        is self-contradictory at highway speed: satisfying the heading-rate
        condition at 60+ km/h *always* pushes lateral_accel past a 3.0
        m/s^2 cornering threshold, making the event undetectable. Instead,
        lane changes and sharp corners are distinguished by speed regime:
        a sustained high-lateral-accel turn above highway speed is
        implausible (that would be a loss-of-control event, not a lane
        change), so anything above the highway floor with a real heading
        deviation is treated as a lane change, while sharp cornering
        (detect_sharp_cornering) is scoped to below that speed.
        """
        mask = (
            (kdf["heading_change_deg_s"] >= THRESHOLDS.rapid_heading_change_deg_s)
            & (kdf["speed_kmh"] > THRESHOLDS.highway_speed_floor_kmh)
        )
        return self._build_events(
            kdf[mask], EventType.RAPID_LANE_CHANGE,
            magnitude_col="heading_change_deg_s", threshold=THRESHOLDS.rapid_heading_change_deg_s,
        )

    def detect_sharp_cornering(self, kdf: pd.DataFrame) -> pd.DataFrame:
        """
        Flags sustained high lateral acceleration below highway speed
        (see detect_rapid_lane_changes docstring for why the speed split
        exists) -- i.e. genuine intersection/curve turns rather than
        highway lane-change maneuvers.
        """
        mask = (
            (kdf["lateral_accel_mps2"] >= THRESHOLDS.sharp_corner_lateral_accel_mps2)
            & (kdf["speed_kmh"] <= THRESHOLDS.highway_speed_floor_kmh)
        )
        return self._build_events(
            kdf[mask], EventType.SHARP_CORNERING,
            magnitude_col="lateral_accel_mps2", threshold=THRESHOLDS.sharp_corner_lateral_accel_mps2,
        )

    def _build_events(self, subset: pd.DataFrame, event_type: str, magnitude_col: str, threshold: float) -> pd.DataFrame:
        if subset.empty:
            return pd.DataFrame(columns=EVENT_COLUMNS)
        out = pd.DataFrame({
            "veh_id": subset["veh_id"],
            "trip_id": subset["trip_id"],
            "global_trip_id": subset["global_trip_id"],
            "event_type": event_type,
            "timestamp": subset["timestamp"],
            "latitude": subset["latitude"],
            "longitude": subset["longitude"],
            "speed_kmh": subset["speed_kmh"],
            "magnitude": subset[magnitude_col],
            "hour_of_day": subset["hour_of_day"],
        })
        out["severity"] = out["magnitude"].apply(lambda m: self._severity(m, threshold))
        out["road_context"] = subset["speed_kmh"].apply(self._road_context)
        return out[EVENT_COLUMNS]

    def detect_all(self, trip_df: pd.DataFrame, speed_limit: Optional[float] = None) -> pd.DataFrame:
        """
        Run all six detectors on a single trip's raw (pre-kinematics)
        DataFrame and return a combined, timestamp-sorted event log.
        """
        if len(trip_df) < THRESHOLDS.min_trip_points:
            raise InsufficientDataError(
                f"Trip has only {len(trip_df)} points; minimum is {THRESHOLDS.min_trip_points}."
            )

        kdf = self._extractor.get_point_level_kinematics(trip_df)

        event_frames = [
            self.detect_aggressive_acceleration(kdf),
            self.detect_harsh_braking(kdf),
            self.detect_excessive_idling(kdf),
            self.detect_overspeeding(kdf, speed_limit),
            self.detect_rapid_lane_changes(kdf),
            self.detect_sharp_cornering(kdf),
        ]
        events = pd.concat(event_frames, ignore_index=True)
        if not events.empty:
            events = events.sort_values("timestamp").reset_index(drop=True)
        self._logger.debug(
            "Detected %d events for trip %s", len(events),
            trip_df["global_trip_id"].iloc[0] if "global_trip_id" in trip_df else "?",
        )
        return events

    def detect_all_trips(self, df: pd.DataFrame, speed_limit: Optional[float] = None) -> pd.DataFrame:
        """Run detection across every trip in a cleaned VED DataFrame."""
        frames: List[pd.DataFrame] = []
        for _, trip_df in df.groupby("global_trip_id"):
            try:
                frames.append(self.detect_all(trip_df, speed_limit))
            except InsufficientDataError:
                continue
        if not frames:
            return pd.DataFrame(columns=EVENT_COLUMNS)
        result = pd.concat(frames, ignore_index=True)
        self._logger.info("Detected %d total events across %d trips", len(result), df["global_trip_id"].nunique())
        return result

    def event_summary(self, events: pd.DataFrame) -> dict:
        """Aggregate an event log into counts per event_type (used by scoring/coaching)."""
        if events.empty:
            return {et: 0 for et in [
                EventType.AGGRESSIVE_ACCELERATION, EventType.HARSH_BRAKING,
                EventType.EXCESSIVE_IDLING, EventType.OVERSPEEDING,
                EventType.RAPID_LANE_CHANGE, EventType.SHARP_CORNERING,
            ]}
        counts = events["event_type"].value_counts().to_dict()
        for et in [
            EventType.AGGRESSIVE_ACCELERATION, EventType.HARSH_BRAKING,
            EventType.EXCESSIVE_IDLING, EventType.OVERSPEEDING,
            EventType.RAPID_LANE_CHANGE, EventType.SHARP_CORNERING,
        ]:
            counts.setdefault(et, 0)
        return counts
