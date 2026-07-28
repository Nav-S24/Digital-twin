"""
test_api.py
===========
Integration tests for the Phase 2 Health Score API, exercised via
TestClient against the real trained model artefacts (models/*.joblib)
and the real reference fleet (data/Output.csv).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api as api_module


@pytest.fixture(scope="module")
def client():
    return TestClient(api_module.app)


def test_health_endpoint_reports_models_loaded(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["classifier_loaded"] is True
    assert body["regressor_loaded"] is True


def test_score_happy_path(client):
    response = client.post("/score", json={
        "temperature": 89.57, "pressure": 27.29, "rpm": 2702.6, "vibration": 0.168,
        "battery_voltage": 12.06, "battery_current": 33.72, "battery_temp": 23.63,
        "fault_count": 9,
    })
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["engine_health"] <= 100.0
    assert 0.0 <= body["battery_health"] <= 100.0
    assert 0.0 <= body["vehicle_health"] <= 100.0
    assert body["health_class"] in {"Excellent", "Good", "Warning", "Critical"}
    assert body["ml_health_score"] is not None
    assert body["predicted_rul"] is not None


def test_score_matches_known_reference_row(client):
    """This exact reading is row 0 of Output.csv; the API's rule-based
    scores must match the values baked into the reference dataset."""
    response = client.post("/score", json={
        "temperature": 89.57075619631647, "pressure": 27.28829412087895,
        "rpm": 2702.56360823628, "vibration": 0.1682903461466361,
        "battery_voltage": 12.060143585945646, "battery_current": 33.72273588296507,
        "battery_temp": 23.63213508946296, "fault_count": 9,
    })
    body = response.json()
    assert body["engine_health"] == pytest.approx(80.0, abs=0.1)
    assert body["battery_health"] == pytest.approx(77.73, abs=0.1)
    assert body["vehicle_health"] == pytest.approx(79.32, abs=0.1)


def test_score_rejects_missing_field(client):
    response = client.post("/score", json={"temperature": 85.0})
    assert response.status_code == 422


def test_fleet_summary(client):
    response = client.get("/fleet/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_vehicles"] == 2000
    assert 0.0 <= body["failure_rate"] <= 1.0


def test_fleet_vehicle_known_index(client):
    response = client.get("/fleet/vehicle/0")
    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_health"] == pytest.approx(79.32, abs=0.1)


def test_fleet_vehicle_out_of_range_returns_404(client):
    response = client.get("/fleet/vehicle/999999")
    assert response.status_code == 404
