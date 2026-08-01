"""
pipeline.py

Orchestrates the full Phase 9 pipeline end-to-end:
    Load -> Preprocess -> Feature Engineer -> Detect Events
    -> Score -> Profile -> (Coaching is computed on-demand per trip/driver)

This module is the single shared entry point used by:
    - api/main.py      (FastAPI REST endpoints)
    - dashboard/app.py  (Streamlit dashboard)
    - main.py           (CLI entry point / batch run)

Results are cached in-memory on the `DriverAnalyticsPipeline` instance
so the (relatively expensive) preprocessing + feature extraction only
runs once per process, not once per API request.
"""

from typing import Dict, Optional

import pandas as pd

from coaching.coaching_engine import CoachingEngine
from config.settings import LLM
from detection.behavior_detector import BehaviorDetector
from feature_engineering.feature_extractor import TripFeatureExtractor
from preprocessing.data_loader import VEDDataLoader
from profiling.driver_profiler import DriverProfiler
from scoring.driver_scorer import DriverScorer
from utils.exceptions import DriverNotFoundError, TripNotFoundError
from utils.logger import get_logger

logger = get_logger(__name__)


class DriverAnalyticsPipeline:
    """Stateful pipeline holding processed data for the current session/dataset."""

    def __init__(self):
        self.loader = VEDDataLoader()
        self.extractor = TripFeatureExtractor()
        self.detector = BehaviorDetector()
        self.scorer = DriverScorer()
        self.profiler = DriverProfiler()

        llm_coach = None
        if LLM.google_api_key:
            from coaching.llm_coach import LLMCoach
            llm_coach = LLMCoach()
        self.coaching_engine = CoachingEngine(llm_coach=llm_coach)

        self.raw_df: Optional[pd.DataFrame] = None
        self.events_df: Optional[pd.DataFrame] = None
        self.scored_trips_df: Optional[pd.DataFrame] = None
        self._logger = logger

    def run(self, source) -> None:
        """Run the full pipeline on a data source and cache all results."""
        self._logger.info("Running full Phase 9 pipeline on source: %s", source)
        self.raw_df = self.loader.run_pipeline(source)
        features_df = self.extractor.extract_all_trips(self.raw_df)
        self.events_df = self.detector.detect_all_trips(self.raw_df)
        scored_df = self.scorer.score_all_trips(features_df, self.events_df)
        self.scored_trips_df = self.profiler.classify_all_trips(scored_df)
        self._logger.info(
            "Pipeline run complete: %d trips, %d drivers, %d events",
            len(self.scored_trips_df), self.scored_trips_df["veh_id"].nunique(), len(self.events_df),
        )

    def is_ready(self) -> bool:
        return self.scored_trips_df is not None and not self.scored_trips_df.empty

    # ------------------------------------------------------------------
    # Query helpers used by the API / dashboard
    # ------------------------------------------------------------------
    def get_driver_trips(self, veh_id: int) -> pd.DataFrame:
        trips = self.scored_trips_df[self.scored_trips_df["veh_id"] == veh_id]
        if trips.empty:
            raise DriverNotFoundError(f"No trips found for veh_id={veh_id}")
        return trips

    def get_trip(self, global_trip_id: str) -> pd.Series:
        trip = self.scored_trips_df[self.scored_trips_df["global_trip_id"] == global_trip_id]
        if trip.empty:
            raise TripNotFoundError(f"Trip not found: {global_trip_id}")
        return trip.iloc[0]

    def get_trip_events(self, global_trip_id: str) -> pd.DataFrame:
        if self.events_df is None or self.events_df.empty:
            return pd.DataFrame()
        return self.events_df[self.events_df["global_trip_id"] == global_trip_id]

    def get_driver_events(self, veh_id: int) -> pd.DataFrame:
        if self.events_df is None or self.events_df.empty:
            return pd.DataFrame()
        return self.events_df[self.events_df["veh_id"] == veh_id]

    def get_driver_profile(self, veh_id: int) -> Dict:
        self.get_driver_trips(veh_id)  # raises DriverNotFoundError if absent
        return self.profiler.profile_driver(self.scored_trips_df, veh_id)

    def get_driver_score(self, veh_id: int) -> Optional[float]:
        self.get_driver_trips(veh_id)
        return self.scorer.aggregate_driver_score(self.scored_trips_df, veh_id)

    def get_driver_score_detail(self, veh_id: int) -> Dict:
        self.get_driver_trips(veh_id)
        detail = self.scorer.aggregate_driver_score_detail(self.scored_trips_df, veh_id)
        if detail is None:
            raise DriverNotFoundError(f"No score available for veh_id={veh_id}")
        return detail

    def get_driver_statistics(self, veh_id: int) -> Dict:
        trips = self.get_driver_trips(veh_id)
        total_duration_s = trips["trip_duration_s"].sum()
        fuel_eff_series = trips["fuel_efficiency_km_per_l"].dropna()

        return {
            "veh_id": veh_id,
            "trip_count": int(len(trips)),
            "total_distance_km": round(float(trips["distance_travelled_km"].sum()), 2),
            "total_duration_hours": round(float(total_duration_s) / 3600.0, 2),
            "avg_speed_kmh": round(float(trips["avg_speed_kmh"].mean()), 2),
            "total_harsh_brakes": int(trips["num_harsh_brakes"].sum()),
            "total_aggressive_accelerations": int(trips["num_accelerations"].sum()),
            "total_sharp_turns": int(trips["num_sharp_turns"].sum()),
            "avg_fuel_efficiency_km_per_l": (
                round(float(fuel_eff_series.mean()), 2) if not fuel_eff_series.empty else None
            ),
            "avg_eco_driving_score": round(float(trips["eco_driving_score"].mean()), 2),
            "highway_driving_pct": round(float(trips["highway_driving_pct"].mean()), 2),
            "city_driving_pct": round(float(trips["city_driving_pct"].mean()), 2),
            "night_driving_pct": round(float(trips["night_driving_pct"].mean()), 2),
        }

    def get_trip_coaching(self, global_trip_id: str, use_llm: bool = True) -> Dict:
        trip = self.get_trip(global_trip_id)
        trip_dict = trip.to_dict()
        trip_events = self.get_trip_events(global_trip_id)
        trip_dict["event_counts"] = self.detector.event_summary(trip_events)
        return self.coaching_engine.generate_coaching(trip_dict, use_llm=use_llm)

    def get_driver_coaching(self, veh_id: int, use_llm: bool = True) -> Dict:
        """Coaching based on the driver's most recent (or lowest-scoring) trip."""
        trips = self.get_driver_trips(veh_id)
        worst_trip = trips.sort_values("driver_score").iloc[0]
        return self.get_trip_coaching(worst_trip["global_trip_id"], use_llm=use_llm)

    def list_driver_trips(self, veh_id: int) -> pd.DataFrame:
        return self.get_driver_trips(veh_id).sort_values("trip_start_time")

    def all_drivers(self) -> pd.DataFrame:
        if not self.is_ready():
            return pd.DataFrame()
        return self.profiler.profile_all_drivers(self.scored_trips_df)


# Module-level singleton used by the API and dashboard so both share one
# in-memory cache within the same process.
pipeline = DriverAnalyticsPipeline()
