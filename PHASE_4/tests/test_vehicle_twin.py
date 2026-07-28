"""
test_vehicle_twin.py
=====================
Unit tests for twin.vehicle.VehicleTwin: composite health weighting,
aggregated failure probability, and the simulate() trajectory.

Includes a regression test for the parenthesisation bug where the
engine's fallback failure-probability estimate was used directly as a
"survival" term instead of `1.0 - fallback`, inflating the simulated
failure probability to ~90%+ on every call regardless of vehicle health.
"""

from __future__ import annotations

import pytest

from services.synchronizer import get_synchronizer


@pytest.fixture(scope="module")
def synchronizer():
    sync = get_synchronizer()
    if sync.total_vehicles == 0:
        sync.initialise()
    return sync


@pytest.fixture(scope="module")
def healthy_twin(synchronizer):
    """Vehicle_0001 is a known 'Good' health-class vehicle in the fixture data."""
    return synchronizer.get_twin("Vehicle_0001")


def test_overall_health_is_bounded(healthy_twin):
    assert 0.0 <= healthy_twin.to_dict()["overall_health"] <= 100.0


def test_overall_failure_probability_is_bounded(healthy_twin):
    fp = healthy_twin.to_dict()["overall_failure_probability"]
    assert 0.0 <= fp <= 1.0


def test_overall_health_matches_weighted_composite(healthy_twin):
    d = healthy_twin.to_dict()
    expected = (
        d["engine"]["health_score"] * 0.40
        + d["battery"]["health_score"] * 0.30
        + d["fuel"]["health_score"] * 0.20
        + d["brake"]["health_score"] * 0.10
    )
    assert d["overall_health"] == pytest.approx(round(expected, 2), abs=0.05)


# --- simulate() regression coverage -----------------------------------------------------------------

def test_simulate_failure_probability_stays_bounded(healthy_twin):
    result = healthy_twin.simulate(30)
    for point in result.trajectory:
        assert 0.0 <= point.failure_probability <= 1.0


def test_simulate_failure_probability_is_not_inflated_by_missing_engine_key(healthy_twin):
    """
    Regression test: EngineTwin.simulate() never emits a per-day
    'failure_probability' key, so VehicleTwin.simulate() always falls
    back to a health-derived estimate for the engine term. That fallback
    must be treated as a genuine failure probability (i.e. its
    complement is the survival term) - not used raw as a survival term.
    A healthy vehicle's simulated failure probability on day 1 should be
    in the same ballpark as its *current*, non-simulated failure
    probability, not wildly higher.
    """
    current_fp = healthy_twin.to_dict()["overall_failure_probability"]
    day1_fp = healthy_twin.simulate(1).trajectory[0].failure_probability
    # The bug produced ~0.91 regardless of vehicle health; a correct
    # implementation stays within a reasonable band of the current value
    # for a vehicle whose health barely changes in a single day.
    assert day1_fp < 0.5
    assert abs(day1_fp - current_fp) < 0.5


def test_simulate_vehicle_health_decreases_monotonically_under_linear_decay(healthy_twin):
    result = healthy_twin.simulate(10)
    healths = [p.vehicle_health for p in result.trajectory]
    assert healths == sorted(healths, reverse=True)


def test_simulate_trajectory_length_matches_requested_days(healthy_twin):
    result = healthy_twin.simulate(45)
    assert len(result.trajectory) == 45
    assert result.trajectory[0].day == 1
    assert result.trajectory[-1].day == 45


def test_simulate_baseline_health_matches_current_overall_health(healthy_twin):
    result = healthy_twin.simulate(5)
    assert result.baseline_health == healthy_twin.to_dict()["overall_health"]
