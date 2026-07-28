"""tests/test_feature_engineering.py"""

import pytest

from feature_engineering.feature_extractor import TripFeatureExtractor
from utils.exceptions import InsufficientDataError


class TestTripFeatureExtractor:
    def setup_method(self):
        self.extractor = TripFeatureExtractor()

    def test_extract_trip_features_returns_expected_keys(self, smooth_trip_df):
        features = self.extractor.extract_trip_features(smooth_trip_df)
        expected_keys = {
            "avg_speed_kmh", "max_speed_kmh", "min_speed_kmh",
            "avg_acceleration_mps2", "max_acceleration_mps2",
            "avg_deceleration_mps2", "max_deceleration_mps2",
            "trip_duration_s", "distance_travelled_km", "idle_time_s",
            "stop_count", "num_accelerations", "num_harsh_brakes",
            "num_sharp_turns", "energy_consumption_kwh",
            "estimated_fuel_consumption_l", "fuel_efficiency_km_per_l",
            "eco_driving_score", "highway_driving_pct", "city_driving_pct",
            "night_driving_pct", "peak_hour_driving_pct",
        }
        assert expected_keys.issubset(set(features.keys()))

    def test_insufficient_points_raises(self, smooth_trip_df):
        tiny = smooth_trip_df.head(3)
        with pytest.raises(InsufficientDataError):
            self.extractor.extract_trip_features(tiny)

    def test_harsh_trip_has_more_events_than_smooth_trip(self, smooth_trip_df, harsh_trip_df):
        smooth_features = self.extractor.extract_trip_features(smooth_trip_df)
        harsh_features = self.extractor.extract_trip_features(harsh_trip_df)
        assert (
            harsh_features["num_harsh_brakes"] + harsh_features["num_accelerations"]
            >= smooth_features["num_harsh_brakes"] + smooth_features["num_accelerations"]
        )

    def test_idle_trip_has_high_idle_time(self, idle_trip_df):
        features = self.extractor.extract_trip_features(idle_trip_df)
        assert features["idle_time_s"] > features["trip_duration_s"] * 0.5

    def test_extract_all_trips(self, combined_raw_df):
        result = self.extractor.extract_all_trips(combined_raw_df)
        assert len(result) == 3
        assert set(result["global_trip_id"]) == {"1_101", "2_202", "3_303"}

    def test_distance_is_non_negative(self, smooth_trip_df):
        features = self.extractor.extract_trip_features(smooth_trip_df)
        assert features["distance_travelled_km"] >= 0

    def test_speed_stats_consistent(self, smooth_trip_df):
        features = self.extractor.extract_trip_features(smooth_trip_df)
        assert features["min_speed_kmh"] <= features["avg_speed_kmh"] <= features["max_speed_kmh"]
