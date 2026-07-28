"""
test_intent_detector.py
========================
Unit tests for services.intent_detector.IntentDetector.
"""

from __future__ import annotations

import pytest

from services.intent_detector import IntentDetector, Intent


@pytest.mark.parametrize("message,expected", [
    ("Why is my engine health dropping?", Intent.HEALTH_EXPLANATION),
    ("What is my battery health?", Intent.HEALTH_EXPLANATION),
    ("What is my failure risk?", Intent.FAILURE_RISK),
    ("How much useful life is left?", Intent.RUL_QUERY),
    ("What maintenance should I do next?", Intent.MAINTENANCE_QUERY),
    ("How is my vehicle status?", Intent.VEHICLE_STATUS),
])
def test_rule_based_intents(message, expected):
    assert IntentDetector.detect(message) == expected


def test_bare_code_with_no_context_is_fault_diagnosis():
    assert IntentDetector.detect("P0420") == Intent.FAULT_DIAGNOSIS


def test_code_with_diagnostic_language_is_fault_diagnosis():
    assert IntentDetector.detect("What does P0420 mean?") == Intent.FAULT_DIAGNOSIS


def test_code_with_driving_language_is_driving_safety():
    assert IntentDetector.detect("Can I drive with P0101?") == Intent.DRIVING_SAFETY


def test_unmatched_message_falls_back_to_vehicle_knowledge():
    assert IntentDetector.detect("Tell me a joke about cars") == Intent.VEHICLE_KNOWLEDGE


def test_extract_obd_codes_delegates_to_diagnostic_service():
    assert IntentDetector.extract_obd_codes("Seeing P0101 and P0420") == ["P0101", "P0420"]
