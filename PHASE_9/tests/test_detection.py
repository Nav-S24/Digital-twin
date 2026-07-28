"""tests/test_detection.py"""

from detection.behavior_detector import BehaviorDetector, EventType
from utils.exceptions import InsufficientDataError
import pytest


class TestBehaviorDetector:
    def setup_method(self):
        self.detector = BehaviorDetector()

    def test_detect_all_returns_expected_columns(self, smooth_trip_df):
        events = self.detector.detect_all(smooth_trip_df)
        expected_cols = {
            "veh_id", "trip_id", "global_trip_id", "event_type", "timestamp",
            "latitude", "longitude", "speed_kmh", "magnitude", "severity",
            "road_context", "hour_of_day",
        }
        assert expected_cols.issubset(set(events.columns))

    def test_harsh_trip_produces_more_events(self, smooth_trip_df, harsh_trip_df):
        smooth_events = self.detector.detect_all(smooth_trip_df)
        harsh_events = self.detector.detect_all(harsh_trip_df)
        assert len(harsh_events) >= len(smooth_events)

    def test_idle_trip_detects_excessive_idling(self, idle_trip_df):
        events = self.detector.detect_all(idle_trip_df)
        assert (events["event_type"] == EventType.EXCESSIVE_IDLING).any()

    def test_insufficient_data_raises(self, smooth_trip_df):
        with pytest.raises(InsufficientDataError):
            self.detector.detect_all(smooth_trip_df.head(2))

    def test_event_summary_has_all_types(self, smooth_trip_df):
        events = self.detector.detect_all(smooth_trip_df)
        summary = self.detector.event_summary(events)
        for event_type in [
            EventType.AGGRESSIVE_ACCELERATION, EventType.HARSH_BRAKING,
            EventType.EXCESSIVE_IDLING, EventType.OVERSPEEDING,
            EventType.RAPID_LANE_CHANGE, EventType.SHARP_CORNERING,
        ]:
            assert event_type in summary

    def test_detect_all_trips_combines_results(self, combined_raw_df):
        events = self.detector.detect_all_trips(combined_raw_df)
        assert set(events["global_trip_id"].unique()).issubset({"1_101", "2_202", "3_303"})

    def test_severity_classification_bounds(self, harsh_trip_df):
        events = self.detector.detect_all(harsh_trip_df)
        if not events.empty:
            assert events["severity"].isin(["mild", "moderate", "severe"]).all()
