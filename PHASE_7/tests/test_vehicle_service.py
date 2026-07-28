"""
test_vehicle_service.py
========================
Unit tests for services.vehicle_service.VehicleService against the real
merged_vehicle_state.csv fixture data (small, static, part of the
deliverable).
"""

from __future__ import annotations

import pytest

from services.vehicle_service import VehicleService, VehicleNotFoundError


KNOWN_VEHICLE = "Vehicle_0001"
UNKNOWN_VEHICLE = "Vehicle_9999999"


def test_exists_true_for_known_vehicle():
    assert VehicleService.exists(KNOWN_VEHICLE) is True


def test_exists_false_for_unknown_vehicle():
    assert VehicleService.exists(UNKNOWN_VEHICLE) is False


def test_lookup_raises_for_unknown_vehicle():
    with pytest.raises(VehicleNotFoundError):
        VehicleService.lookup(UNKNOWN_VEHICLE)


def test_health_view_contains_expected_fields_only():
    view = VehicleService.health_view(KNOWN_VEHICLE)
    assert set(view.keys()) == {
        "Vehicle_ID", "engine_health", "battery_health", "vehicle_health",
        "health_class", "ml_health_score", "Top_Risk_Sensor",
        "Top_Risk_SHAP_Value", "Affected_System", "Reason",
    }
    assert view["Vehicle_ID"] == KNOWN_VEHICLE


def test_status_view_contains_expected_fields_only():
    view = VehicleService.status_view(KNOWN_VEHICLE)
    assert set(view.keys()) == {
        "Vehicle_ID", "vehicle_health", "health_class",
        "trip_readiness", "fault_count", "Urgency",
    }


def test_failure_risk_view_contains_expected_fields_only():
    view = VehicleService.failure_risk_view(KNOWN_VEHICLE)
    assert set(view.keys()) == {
        "Vehicle_ID", "Failure_Probability", "Failure_Risk_Percentage",
        "Urgency", "Top_Risk_Sensor", "Top_Risk_SHAP_Value",
        "Affected_System", "Reason",
    }


def test_rul_view_contains_expected_fields_only():
    view = VehicleService.rul_view(KNOWN_VEHICLE)
    assert set(view.keys()) == {
        "Vehicle_ID", "Remaining_Useful_Life_Cycles",
        "Remaining_Useful_Life_KM", "Urgency", "Book_Service_Within_Days",
    }


def test_maintenance_view_contains_expected_fields_only():
    view = VehicleService.maintenance_view(KNOWN_VEHICLE)
    assert set(view.keys()) == {
        "Vehicle_ID", "Recommended_Action", "Maintenance_Priority",
        "Book_Service_Within_Days", "Affected_System", "Reason",
    }


@pytest.mark.parametrize("view_fn", [
    VehicleService.health_view,
    VehicleService.status_view,
    VehicleService.failure_risk_view,
    VehicleService.rul_view,
    VehicleService.maintenance_view,
])
def test_all_views_raise_for_unknown_vehicle(view_fn):
    with pytest.raises(VehicleNotFoundError):
        view_fn(UNKNOWN_VEHICLE)
