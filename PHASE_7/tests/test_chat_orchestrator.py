"""
test_chat_orchestrator.py
==========================
Unit tests for services.chat_orchestrator.ChatOrchestrator. No
ANTHROPIC_API_KEY is set in the test environment, so LLMService always
runs in deterministic debug mode — these tests exercise the orchestration
logic (intent routing, session memory, vehicle-switch isolation) without
needing network access or mocking the Anthropic client.
"""

from __future__ import annotations

import os

import pytest

from services.chat_orchestrator import ChatOrchestrator, _SESSION_MEMORY, _SESSION_VEHICLE


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """Guarantee debug mode regardless of the host environment's own env vars."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import services.llm_service as llm_service
    monkeypatch.setattr(llm_service, "ANTHROPIC_API_KEY", None)
    yield


@pytest.fixture(autouse=True)
def _clean_sessions():
    _SESSION_MEMORY.clear()
    _SESSION_VEHICLE.clear()
    yield
    _SESSION_MEMORY.clear()
    _SESSION_VEHICLE.clear()


def test_process_chat_returns_expected_shape():
    result = ChatOrchestrator.process_chat("Vehicle_0001", "sess_a", "What is my failure risk?")
    assert result["vehicle_id"] == "Vehicle_0001"
    assert result["session_id"] == "sess_a"
    assert result["intent"] == "FAILURE_RISK"
    assert "DEBUG MODE" in result["answer"]
    assert result["data_sources"] == ["Merged Vehicle Intelligence"]
    assert result["obd_codes"] == []


def test_session_memory_accumulates_turns():
    ChatOrchestrator.process_chat(None, "sess_b", "What does P0420 mean?")
    ChatOrchestrator.process_chat(None, "sess_b", "And P0101?")
    history = list(_SESSION_MEMORY["sess_b"])
    # 2 user + 2 assistant turns
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_vehicle_switch_clears_prior_session_history():
    ChatOrchestrator.process_chat("Vehicle_0001", "sess_c", "Why is my engine health dropping?")
    assert len(_SESSION_MEMORY["sess_c"]) == 2

    # Same session_id, different vehicle -> prior history must be dropped.
    ChatOrchestrator.process_chat("Vehicle_0002", "sess_c", "What is my failure risk?")
    history = list(_SESSION_MEMORY["sess_c"])
    assert len(history) == 2  # only the new turn, not 4 - old vehicle's turn was dropped


def test_clear_session_removes_memory_and_vehicle_binding():
    ChatOrchestrator.process_chat("Vehicle_0001", "sess_d", "How is my vehicle status?")
    assert "sess_d" in _SESSION_MEMORY
    ChatOrchestrator.clear_session("sess_d")
    assert "sess_d" not in _SESSION_MEMORY
    assert "sess_d" not in _SESSION_VEHICLE
