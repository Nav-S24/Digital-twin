"""
test_chat_routes.py
====================
End-to-end smoke tests for the FastAPI app (main.py -> routes/chat.py),
exercised via TestClient. No ANTHROPIC_API_KEY is set, so responses come
from LLMService's deterministic debug mode - these tests validate
routing, request/response schemas, and the full retrieval pipeline
without needing network access.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main
from services.chat_orchestrator import _SESSION_MEMORY, _SESSION_VEHICLE


@pytest.fixture(autouse=True)
def _clean_sessions():
    _SESSION_MEMORY.clear()
    _SESSION_VEHICLE.clear()
    yield
    _SESSION_MEMORY.clear()
    _SESSION_VEHICLE.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_happy_path_with_known_vehicle(client):
    response = client.post("/chat", json={
        "vehicle_id": "Vehicle_0001",
        "session_id": "route_sess_1",
        "message": "Why is my engine health dropping?",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "HEALTH_EXPLANATION"
    assert body["vehicle_id"] == "Vehicle_0001"
    assert "Merged Vehicle Intelligence" in body["data_sources"]


def test_chat_without_vehicle_id_is_optional(client):
    response = client.post("/chat", json={
        "session_id": "route_sess_2",
        "message": "What does P0420 mean?",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "FAULT_DIAGNOSIS"
    assert body["obd_codes"] == ["P0420"]


def test_chat_missing_required_field_returns_422(client):
    response = client.post("/chat", json={"message": "hello"})  # missing session_id
    assert response.status_code == 422


def test_chat_clear_endpoint(client):
    client.post("/chat", json={
        "session_id": "route_sess_3",
        "message": "What does P0101 mean?",
    })
    response = client.post("/chat/clear", json={"session_id": "route_sess_3"})
    assert response.status_code == 200
    assert response.json() == {"status": "cleared", "session_id": "route_sess_3"}
