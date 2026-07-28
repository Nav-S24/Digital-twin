"""
test_context_builder.py
========================
Unit tests for services.context_builder.ContextBuilder — verifies each
intent pulls exactly the right narrow slice of data and reports accurate
data_sources / vehicle_error.
"""

from __future__ import annotations

from services.context_builder import ContextBuilder, SOURCE_MERGED, SOURCE_GENERAL
from services.intent_detector import Intent

KNOWN_VEHICLE = "Vehicle_0001"
UNKNOWN_VEHICLE = "Vehicle_9999999"


def test_health_explanation_with_known_vehicle():
    ctx = ContextBuilder.build(Intent.HEALTH_EXPLANATION, KNOWN_VEHICLE, [])
    assert ctx["vehicle_context"] is not None
    assert ctx["vehicle_context"]["Vehicle_ID"] == KNOWN_VEHICLE
    assert ctx["vehicle_error"] is None
    assert SOURCE_MERGED in ctx["data_sources"]


def test_health_explanation_with_no_vehicle_selected():
    ctx = ContextBuilder.build(Intent.HEALTH_EXPLANATION, None, [])
    assert ctx["vehicle_context"] is None
    assert ctx["vehicle_error"] is not None


def test_health_explanation_with_unknown_vehicle():
    ctx = ContextBuilder.build(Intent.HEALTH_EXPLANATION, UNKNOWN_VEHICLE, [])
    assert ctx["vehicle_context"] is None
    assert "not found" in ctx["vehicle_error"]


def test_fault_diagnosis_with_code():
    ctx = ContextBuilder.build(Intent.FAULT_DIAGNOSIS, None, ["P0101"])
    assert len(ctx["diagnostic_context"]) == 1
    assert ctx["diagnostic_context"][0]["code"] == "P0101"
    assert ctx["data_sources"] == ["Phase 5 Diagnostic Store"]


def test_fault_diagnosis_without_code_sets_error():
    ctx = ContextBuilder.build(Intent.FAULT_DIAGNOSIS, None, [])
    assert ctx["vehicle_error"] is not None
    assert ctx["diagnostic_context"] == []


def test_driving_safety_with_vehicle_and_code():
    ctx = ContextBuilder.build(Intent.DRIVING_SAFETY, KNOWN_VEHICLE, ["P0101"])
    assert ctx["vehicle_context"] is not None
    assert len(ctx["diagnostic_context"]) == 1
    assert SOURCE_MERGED in ctx["data_sources"]
    assert "Phase 5 Diagnostic Store" in ctx["data_sources"]


def test_driving_safety_with_neither_vehicle_nor_code_sets_error():
    ctx = ContextBuilder.build(Intent.DRIVING_SAFETY, None, [])
    assert ctx["vehicle_error"] == "No vehicle selected and no OBD code provided."


def test_vehicle_knowledge_never_touches_vehicle_data():
    ctx = ContextBuilder.build(Intent.VEHICLE_KNOWLEDGE, KNOWN_VEHICLE, [])
    assert ctx["vehicle_context"] is None
    assert ctx["diagnostic_context"] == []
    assert ctx["data_sources"] == [SOURCE_GENERAL]


def test_maintenance_query_pulls_phase5_when_code_given():
    ctx = ContextBuilder.build(Intent.MAINTENANCE_QUERY, KNOWN_VEHICLE, ["P0101"])
    assert ctx["vehicle_context"] is not None
    assert len(ctx["diagnostic_context"]) == 1
    assert SOURCE_MERGED in ctx["data_sources"]
    assert "Phase 5 Diagnostic Store" in ctx["data_sources"]
