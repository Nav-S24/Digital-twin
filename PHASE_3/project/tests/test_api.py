"""
test_api.py
===========
Integration tests for the Phase 3 FastAPI app (/,  /health, /predict),
exercised via TestClient against the pretrained model artefacts already
committed under models/. No training happens in these tests - they load
the same artefacts the real service would load in production.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import phase2_pipeline as p3


@pytest.fixture(scope="module")
def client():
    return TestClient(p3.app)


@pytest.fixture(scope="module")
def sample_payload():
    """A real Phase 1 output row, plus the vehicle_id the API also requires."""
    df = pd.read_csv("Output.csv")
    row = df.iloc[0].to_dict()
    row["vehicle_id"] = "Vehicle_TEST_001"
    # SensorPayload doesn't declare a `failure` or `health_class` field.
    row.pop("failure", None)
    row.pop("health_class", None)
    return row


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["health"] == "/health"


def test_health_endpoint_reports_models_loaded(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["models_loaded"] is True


def test_predict_happy_path(client, sample_payload):
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 200
    body = response.json()

    assert body["vehicle_id"] == "Vehicle_TEST_001"
    preds = body["predictions"]
    assert 0.0 <= preds["failure_probability"] <= 1.0
    assert preds["rul_cycles"] > 0
    assert preds["urgency"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert len(body["top_risk_sensors"]) == 3
    assert len(body["recommendations"]) == 3


def test_predict_urgency_is_consistent_with_failure_probability(client, sample_payload):
    """A clearly-healthy vehicle (low fault count, good health scores) should
    not come back CRITICAL."""
    healthy_payload = dict(sample_payload)
    healthy_payload.update({
        "engine_health": 95.0, "battery_health": 95.0, "vehicle_health": 95.0,
        "ml_health_score": 95.0, "trip_readiness": 95.0, "fault_count": 0.0,
        "health_class_id": 0,
    })
    response = client.post("/predict", json=healthy_payload)
    assert response.status_code == 200
    assert response.json()["predictions"]["urgency"] != "CRITICAL"


def test_predict_rejects_missing_required_field(client, sample_payload):
    incomplete = dict(sample_payload)
    del incomplete["engine_health"]
    response = client.post("/predict", json=incomplete)
    assert response.status_code == 422


def test_predict_rejects_missing_vehicle_id(client, sample_payload):
    incomplete = dict(sample_payload)
    del incomplete["vehicle_id"]
    response = client.post("/predict", json=incomplete)
    assert response.status_code == 422
