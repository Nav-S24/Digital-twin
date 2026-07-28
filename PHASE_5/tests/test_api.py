"""
test_api.py
===========
Integration tests for the Phase 5 OBD Diagnostics Intelligence API,
exercised through TestClient with the real startup event (loads the
trained AI4I/NASA/Scania models and the OBD knowledge base). No mocking
of the ML models - these hit the actual pickled artefacts shipped under
models/.

NHTSA-dependent endpoints (/vehicle/makes, /vehicle/recalls) require
internet access this sandbox blocks; those tests only assert the app
degrades gracefully (a clean 502, not a crash) rather than asserting a
successful NHTSA response.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.routes as routes


@pytest.fixture(scope="module")
def client():
    with TestClient(routes.app) as c:
        yield c


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert all(body["services"].values())
    assert body["obd_codes_loaded"] > 0


def test_obd_lookup_known_code(client):
    response = client.get("/obd/P0420")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "P0420"
    assert "Catalyst" in body["description"]


def test_obd_lookup_unknown_code_does_not_error(client):
    response = client.get("/obd/ZZZZ")
    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "Unknown"


def test_obd_search_returns_relevant_matches(client):
    response = client.get("/obd/search", params={"q": "misfire"})
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_diagnose_happy_path_with_known_codes(client):
    response = client.post("/diagnose", json={
        "fault_codes": ["P0420", "P0300"],
        "temperature": 305.0,
        "rpm": 2200,
        "torque": 45,
        "tool_wear": 120,
    })
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["failure_probability"] <= 1.0
    assert body["remaining_life"] >= 0
    assert body["trip_status"] in {"OK", "CAUTION", "NO-GO"}
    assert len(body["obd_details"]) == 2


def test_diagnose_with_no_fault_codes_reports_healthy(client):
    response = client.post("/diagnose", json={
        "fault_codes": [], "temperature": 298, "rpm": 800, "torque": 10, "tool_wear": 5,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "No codes supplied"
    assert body["maintenance_urgency"] == "None"


def test_diagnose_with_unrecognised_code_does_not_error(client):
    response = client.post("/diagnose", json={
        "fault_codes": ["NOTREAL"], "temperature": 298, "rpm": 800, "torque": 10, "tool_wear": 5,
    })
    assert response.status_code == 200
    assert response.json()["description"].startswith("Unknown DTC code")


def test_diagnose_rejects_out_of_range_temperature(client):
    response = client.post("/diagnose", json={
        "temperature": 900, "rpm": 800, "torque": 10, "tool_wear": 5,
    })
    assert response.status_code == 422


def test_diagnose_aps_sensor_mode(client):
    response = client.post("/diagnose/aps", json={
        "sensors": {"aa_000": 52.0, "ab_000": 0.0, "ag_001": 1.2},
    })
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "full_aps_sensor_model"
    assert 0.0 <= body["risk_score"] <= 1.0


def test_vehicle_makes_degrades_gracefully_without_network(client):
    """This sandbox blocks vpic.nhtsa.dot.gov, so we only assert the API
    fails cleanly (502) instead of crashing the process."""
    response = client.get("/vehicle/makes")
    assert response.status_code in (200, 502)
