"""
test_obd_knowledge_base.py
===========================
Unit tests for services.obd_knowledge_base.OBDKnowledgeBase - the pure,
model-free lookup layer backing /obd/{code} and /obd/search.
"""

from __future__ import annotations

from services.obd_knowledge_base import OBDKnowledgeBase


def test_singleton_returns_same_instance():
    assert OBDKnowledgeBase.get() is OBDKnowledgeBase.get()


def test_lookup_known_code_has_required_fields():
    kb = OBDKnowledgeBase.get()
    result = kb.lookup("P0420")
    assert result["code"] == "P0420"
    for field in ("description", "severity", "affected_system", "recommendation"):
        assert field in result and result[field]


def test_lookup_unknown_code_falls_back_gracefully():
    kb = OBDKnowledgeBase.get()
    result = kb.lookup("Q9999")
    assert result["code"] == "Q9999"
    assert result["severity"] == "Unknown"


def test_lookup_many_preserves_order_and_count():
    kb = OBDKnowledgeBase.get()
    codes = ["P0420", "P0300", "Q9999"]
    results = kb.lookup_many(codes)
    assert [r["code"] for r in results] == codes


def test_max_severity_empty_list_is_unknown():
    kb = OBDKnowledgeBase.get()
    assert kb.max_severity([]) == "Unknown"


def test_all_codes_is_non_empty_and_unique():
    kb = OBDKnowledgeBase.get()
    codes = kb.all_codes()
    assert len(codes) > 0
    assert len(codes) == len(set(codes))
