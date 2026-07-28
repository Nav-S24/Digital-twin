"""
test_rules.py
=============
Unit tests for the pure, model-free helper functions in phase2_pipeline.py:
get_urgency(), get_top_sensors(), and build_recommendations(). None of
these touch the trained models on disk, so they run fast and need no
fixtures beyond plain Python values.
"""

from __future__ import annotations

import numpy as np
import pytest

from phase2_pipeline import build_recommendations, get_top_sensors, get_urgency


# --- get_urgency -----------------------------------------------------------------

@pytest.mark.parametrize("fail_prob,rul_cycles,expected", [
    (0.90, 100, "CRITICAL"),   # fail_prob alone triggers CRITICAL
    (0.10, 8,   "CRITICAL"),   # rul_cycles alone triggers CRITICAL
    (0.60, 100, "HIGH"),
    (0.10, 25,  "HIGH"),
    (0.35, 100, "MEDIUM"),
    (0.10, 45,  "MEDIUM"),
    (0.05, 100, "LOW"),
])
def test_get_urgency_thresholds(fail_prob, rul_cycles, expected):
    assert get_urgency(fail_prob, rul_cycles) == expected


def test_get_urgency_boundary_values_are_inclusive():
    # Spec: fail_prob >= 0.80 or rul_cycles <= 10 -> CRITICAL
    assert get_urgency(0.80, 999) == "CRITICAL"
    assert get_urgency(0.0, 10) == "CRITICAL"


# --- get_top_sensors -----------------------------------------------------------------

def test_get_top_sensors_orders_by_absolute_shap_value():
    shap_vals = np.array([0.1, -0.9, 0.5])
    feat_names = ["temperature", "pressure", "rpm"]
    result = get_top_sensors(shap_vals, feat_names, top_n=3)
    assert [r["sensor"] for r in result] == ["pressure", "rpm", "temperature"]


def test_get_top_sensors_respects_top_n():
    shap_vals = np.array([0.1, -0.9, 0.5, 0.05])
    feat_names = ["a", "b", "c", "d"]
    result = get_top_sensors(shap_vals, feat_names, top_n=2)
    assert len(result) == 2


# --- build_recommendations -----------------------------------------------------------------

def test_build_recommendations_returns_one_item_per_sensor():
    top_sensors = [
        {"sensor": "temperature", "shap_value": 0.5},
        {"sensor": "fault_count", "shap_value": -0.2},
    ]
    recs = build_recommendations(top_sensors, rul_cycles=60, fail_prob=0.2)
    assert len(recs) == 2
    assert recs[0]["priority"] == 1
    assert recs[1]["priority"] == 2
    for r in recs:
        assert "system" in r and "action" in r and "reason" in r and "book_within_days" in r


def test_build_recommendations_labels_high_shap_as_rapidly_deteriorating():
    top_sensors = [{"sensor": "vibration", "shap_value": 0.5}]
    recs = build_recommendations(top_sensors, rul_cycles=60, fail_prob=0.2)
    assert "rapidly deteriorating" in recs[0]["reason"]


def test_build_recommendations_labels_low_shap_as_elevated():
    top_sensors = [{"sensor": "vibration", "shap_value": 0.1}]
    recs = build_recommendations(top_sensors, rul_cycles=60, fail_prob=0.2)
    assert "elevated" in recs[0]["reason"]


def test_build_recommendations_book_within_days_is_at_least_one():
    top_sensors = [{"sensor": "temperature", "shap_value": 0.9}]
    recs = build_recommendations(top_sensors, rul_cycles=1, fail_prob=0.95)
    assert recs[0]["book_within_days"] >= 1
