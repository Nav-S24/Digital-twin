"""
test_api.py
===========
End-to-end integration tests for the Vehicle Digital Twin FastAPI app.
Uses `with TestClient(main.app) as client:` so the lifespan handler runs
and the full 2000-vehicle twin registry is loaded, exactly as it would
be in production.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["health"] == "/digital_twin/health"


def test_health_endpoint_reports_ready(client):
    response = client.get("/digital_twin/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["vehicles_loaded"] == 2000


def test_fleet_summary(client):
    response = client.get("/digital_twin/fleet")
    assert response.status_code == 200
    body = response.json()
    assert body["total_vehicles"] == 2000
    assert body["critical_count"] + body["warning_count"] + body["good_count"] + body["excellent_count"] == 2000


def test_current_state_for_known_vehicle(client):
    response = client.get("/digital_twin/current/Vehicle_0001")
    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_id"] == "Vehicle_0001"
    assert 0.0 <= body["overall_failure_probability"] <= 1.0


def test_current_state_for_unknown_vehicle_returns_404(client):
    response = client.get("/digital_twin/current/Vehicle_9999999")
    assert response.status_code == 404


def test_components_endpoint_returns_all_four_systems(client):
    response = client.get("/digital_twin/components/Vehicle_0001")
    assert response.status_code == 200
    body = response.json()
    assert set(["engine", "battery", "fuel", "brake"]).issubset(body.keys())


def test_risk_endpoint(client):
    response = client.get("/digital_twin/risk/Vehicle_0001")
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_rul_endpoint(client):
    response = client.get("/digital_twin/rul/Vehicle_0001")
    assert response.status_code == 200
    assert response.json()["rul_cycles"] >= 0


def test_ids_endpoint_lists_all_vehicles(client):
    response = client.get("/digital_twin/ids")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2000
    assert "Vehicle_0001" in body["vehicle_ids"]


def test_simulate_happy_path(client):
    response = client.post("/digital_twin/simulate", json={"vehicle_id": "Vehicle_0001", "days": 30})
    assert response.status_code == 200
    body = response.json()
    assert len(body["trajectory"]) == 30
    for point in body["trajectory"]:
        assert 0.0 <= point["failure_probability"] <= 1.0


def test_simulate_rejects_missing_days_field(client):
    response = client.post("/digital_twin/simulate", json={"vehicle_id": "Vehicle_0001"})
    assert response.status_code == 422


def test_simulate_unknown_vehicle_returns_404(client):
    response = client.post("/digital_twin/simulate", json={"vehicle_id": "Vehicle_9999999", "days": 10})
    assert response.status_code == 404
