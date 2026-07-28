"""
test_health_scoring.py
=======================
Unit tests for src.health_scoring - the rule-based engine/battery/vehicle
health scoring that both the API and dashboard call directly.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.health_scoring import add_all_health_scores


def _reading(**overrides):
    base = dict(
        temperature=85.0, pressure=28.0, rpm=2800.0, vibration=0.3,
        battery_voltage=12.4, battery_current=40.0, battery_temp=30.0, fault_count=1,
    )
    base.update(overrides)
    return pd.DataFrame([base])


def test_healthy_reading_scores_high():
    scored = add_all_health_scores(_reading())
    row = scored.iloc[0]
    assert row["engine_health"] >= 90
    assert row["battery_health"] >= 80
    assert row["health_class"] in {"Excellent", "Good"}


def test_all_scores_are_bounded_0_to_100():
    scored = add_all_health_scores(_reading(temperature=200, vibration=5, fault_count=50))
    row = scored.iloc[0]
    for col in ("engine_health", "battery_health", "vehicle_health", "trip_readiness"):
        assert 0.0 <= row[col] <= 100.0


def test_critical_temperature_tanks_engine_health():
    healthy = add_all_health_scores(_reading()).iloc[0]["engine_health"]
    overheated = add_all_health_scores(_reading(temperature=130)).iloc[0]["engine_health"]
    assert overheated < healthy


def test_high_fault_count_lowers_health_class():
    clean = add_all_health_scores(_reading(fault_count=0)).iloc[0]
    faulty = add_all_health_scores(_reading(fault_count=10)).iloc[0]
    assert faulty["vehicle_health"] < clean["vehicle_health"]


def test_low_battery_voltage_lowers_battery_health():
    nominal = add_all_health_scores(_reading(battery_voltage=12.6)).iloc[0]["battery_health"]
    low = add_all_health_scores(_reading(battery_voltage=10.5)).iloc[0]["battery_health"]
    assert low < nominal


def test_vehicle_health_is_weighted_composite():
    scored = add_all_health_scores(_reading()).iloc[0]
    expected = 0.7 * scored["engine_health"] + 0.3 * scored["battery_health"]
    assert scored["vehicle_health"] == pytest.approx(expected, abs=0.01)


def test_health_class_thresholds():
    # vehicle_health >= 90 -> Excellent; a clean reading with generous
    # thresholds should land there.
    scored = add_all_health_scores(_reading(
        temperature=70, pressure=30, rpm=2000, vibration=0.1,
        battery_voltage=12.6, battery_current=20, battery_temp=25, fault_count=0,
    )).iloc[0]
    assert scored["health_class"] == "Excellent"
    assert scored["health_class_id"] == 0


def test_trip_readiness_label_matches_score():
    scored = add_all_health_scores(_reading(fault_count=0)).iloc[0]
    if scored["trip_readiness"] >= 70:
        assert scored["trip_readiness_label"] == "Ready"


def test_add_all_health_scores_does_not_mutate_input():
    original = _reading()
    original_copy = original.copy()
    add_all_health_scores(original)
    pd.testing.assert_frame_equal(original, original_copy)
