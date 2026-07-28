"""
tests/conftest.py

Shared pytest fixtures for Phase 9 tests. Uses a small synthetic
DataFrame (not the full VED CSV) so the test suite runs in milliseconds
without needing the dataset on disk.
"""

import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_trip(veh_id: int, trip_id: int, n_points: int, start_time: datetime,
                speed_profile, lat0=42.28, lon0=-83.70) -> pd.DataFrame:
    """Build a synthetic single-trip DataFrame with a given speed profile (km/h list)."""
    rows = []
    lat, lon = lat0, lon0
    t = start_time
    for i, speed in enumerate(speed_profile):
        t = start_time + timedelta(seconds=i)
        # advance position roughly consistent with speed (very rough, fine for tests)
        lat += (speed / 3.6) * 1.0 / 111_000.0
        rows.append({
            "veh_id": veh_id, "trip_id": trip_id,
            "global_trip_id": f"{veh_id}_{trip_id}",
            "timestamp": t, "hour_of_day": t.hour, "day_of_week": t.weekday(),
            "latitude": lat, "longitude": lon,
            "speed_kmh": speed,
            "fuel_rate_l_hr": max(0.5, speed * 0.05),
            "maf_g_s": max(1.0, speed * 0.3),
            "engine_rpm": 1000 + speed * 20,
            "hv_battery_current_a": np.nan,
            "hv_battery_voltage_v": np.nan,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def smooth_trip_df():
    """A calm trip: gentle acceleration, steady cruise, gentle stop. Should score high."""
    speeds = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 50, 50, 50, 50, 45, 40, 30, 20, 10, 5, 0]
    return _make_trip(veh_id=1, trip_id=101, n_points=len(speeds),
                       start_time=datetime(2017, 11, 1, 10, 0, 0), speed_profile=speeds)


@pytest.fixture
def harsh_trip_df():
    """An aggressive trip: sharp accelerations and hard braking. Should score low."""
    speeds = [0, 30, 60, 80, 20, 70, 10, 90, 5, 60, 0, 50, 90, 0, 70, 0, 80, 10, 0]
    return _make_trip(veh_id=2, trip_id=202, n_points=len(speeds),
                       start_time=datetime(2017, 11, 1, 18, 0, 0), speed_profile=speeds)


@pytest.fixture
def idle_trip_df():
    """A trip dominated by idling (stationary for most of the duration)."""
    speeds = [0] * 250 + [20, 25, 30, 25, 20, 0, 0, 0]
    return _make_trip(veh_id=3, trip_id=303, n_points=len(speeds),
                       start_time=datetime(2017, 11, 1, 8, 0, 0), speed_profile=speeds)


@pytest.fixture
def combined_raw_df(smooth_trip_df, harsh_trip_df, idle_trip_df):
    return pd.concat([smooth_trip_df, harsh_trip_df, idle_trip_df], ignore_index=True)
