"""tests/test_scoring_and_profiling.py"""

from detection.behavior_detector import BehaviorDetector
from feature_engineering.feature_extractor import TripFeatureExtractor
from profiling.driver_profiler import DriverProfiler
from scoring.driver_scorer import DriverScorer


class TestDriverScorer:
    def setup_method(self):
        self.extractor = TripFeatureExtractor()
        self.detector = BehaviorDetector()
        self.scorer = DriverScorer()

    def test_score_within_bounds(self, harsh_trip_df):
        features = self.extractor.extract_trip_features(harsh_trip_df)
        import pandas as pd
        features_series = pd.Series(features)
        events = self.detector.detect_all(harsh_trip_df)
        counts = self.detector.event_summary(events)
        result = self.scorer.score_trip(features_series, counts)
        assert 0 <= result["score"] <= 100

    def test_smooth_trip_scores_higher_than_harsh_trip(self, smooth_trip_df, harsh_trip_df):
        import pandas as pd

        smooth_features = pd.Series(self.extractor.extract_trip_features(smooth_trip_df))
        harsh_features = pd.Series(self.extractor.extract_trip_features(harsh_trip_df))

        smooth_counts = self.detector.event_summary(self.detector.detect_all(smooth_trip_df))
        harsh_counts = self.detector.event_summary(self.detector.detect_all(harsh_trip_df))

        smooth_score = self.scorer.score_trip(smooth_features, smooth_counts)["score"]
        harsh_score = self.scorer.score_trip(harsh_features, harsh_counts)["score"]

        assert smooth_score >= harsh_score

    def test_score_all_trips_appends_columns(self, combined_raw_df):
        features_df = self.extractor.extract_all_trips(combined_raw_df)
        events_df = self.detector.detect_all_trips(combined_raw_df)
        scored = self.scorer.score_all_trips(features_df, events_df)
        assert "driver_score" in scored.columns
        assert scored["driver_score"].between(0, 100).all()


class TestDriverProfiler:
    def setup_method(self):
        self.extractor = TripFeatureExtractor()
        self.detector = BehaviorDetector()
        self.scorer = DriverScorer()
        self.profiler = DriverProfiler()

    def test_classify_all_trips_assigns_valid_profiles(self, combined_raw_df):
        features_df = self.extractor.extract_all_trips(combined_raw_df)
        events_df = self.detector.detect_all_trips(combined_raw_df)
        scored = self.scorer.score_all_trips(features_df, events_df)
        profiled = self.profiler.classify_all_trips(scored)

        valid_profiles = {
            "Safe Driver", "Eco Driver", "Normal Driver",
            "Aggressive Driver", "High Risk Driver",
        }
        assert set(profiled["driver_profile"].unique()).issubset(valid_profiles)

    def test_profile_driver_returns_summary(self, combined_raw_df):
        features_df = self.extractor.extract_all_trips(combined_raw_df)
        events_df = self.detector.detect_all_trips(combined_raw_df)
        scored = self.scorer.score_all_trips(features_df, events_df)
        profiled = self.profiler.classify_all_trips(scored)

        summary = self.profiler.profile_driver(profiled, veh_id=1)
        assert summary["veh_id"] == 1
        assert summary["trip_count"] == 1
        assert summary["profile"] is not None

    def test_profile_unknown_driver_returns_empty(self, combined_raw_df):
        features_df = self.extractor.extract_all_trips(combined_raw_df)
        events_df = self.detector.detect_all_trips(combined_raw_df)
        scored = self.scorer.score_all_trips(features_df, events_df)
        profiled = self.profiler.classify_all_trips(scored)

        summary = self.profiler.profile_driver(profiled, veh_id=9999)
        assert summary["trip_count"] == 0
        assert summary["profile"] is None
