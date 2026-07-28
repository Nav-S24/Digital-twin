"""
test_diagnostic_service.py
===========================
Unit tests for services.diagnostic_service.DiagnosticService: OBD-II code
extraction from free text, and the Phase5 -> KB -> raw fallback lookup
chain. Uses the real CSVs shipped under data/, since they're small,
static, and part of the deliverable (no mocking needed / no network).
"""

from __future__ import annotations

from services.diagnostic_service import DiagnosticService


# --- extract_codes -----------------------------------------------------------------

def test_extract_codes_finds_standard_code():
    assert DiagnosticService.extract_codes("What does P0420 mean?") == ["P0420"]


def test_extract_codes_is_case_insensitive_and_normalizes_upper():
    assert DiagnosticService.extract_codes("check code p0101 please") == ["P0101"]


def test_extract_codes_handles_multiple_distinct_codes_in_order():
    codes = DiagnosticService.extract_codes("I have both P0101 and P0420 showing.")
    assert codes == ["P0101", "P0420"]


def test_extract_codes_dedupes_repeated_code():
    codes = DiagnosticService.extract_codes("P0101 again, still P0101 on the scanner.")
    assert codes == ["P0101"]


def test_extract_codes_returns_empty_list_for_no_code():
    assert DiagnosticService.extract_codes("Why is my engine health dropping?") == []


def test_extract_codes_handles_empty_and_none_input():
    assert DiagnosticService.extract_codes("") == []
    assert DiagnosticService.extract_codes(None) == []


# --- lookup chain -----------------------------------------------------------------

def test_lookup_prefers_phase5_when_present():
    result = DiagnosticService.lookup("P0101")
    assert result["source"] == "Phase 5 Diagnostic Store"
    assert result["data"] is not None
    assert result["code"] == "P0101"


def test_lookup_falls_back_to_raw_reference_when_not_in_phase5_or_kb():
    # P1487 exists only in the raw obd-trouble-codes.csv fallback list.
    result = DiagnosticService.lookup("P1487")
    assert result["source"] == "OBD Fallback Reference"
    assert result["data"]["code"] == "P1487"
    assert result["data"]["description"]


def test_lookup_returns_not_found_for_unknown_code():
    result = DiagnosticService.lookup("P9999")
    assert result["source"] == "NOT_FOUND"
    assert result["data"] is None


def test_lookup_normalizes_lowercase_code():
    result = DiagnosticService.lookup("p0101")
    assert result["code"] == "P0101"
    assert result["source"] == "Phase 5 Diagnostic Store"


def test_lookup_many_returns_one_result_per_code():
    results = DiagnosticService.lookup_many(["P0101", "P9999"])
    assert [r["code"] for r in results] == ["P0101", "P9999"]
    assert results[0]["source"] == "Phase 5 Diagnostic Store"
    assert results[1]["source"] == "NOT_FOUND"
