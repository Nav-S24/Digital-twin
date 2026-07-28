"""
test_rag.py
===========
Unit tests for app.rag_pipeline. Gemini and retrieval are mocked out, so
these tests never make a network call or require GOOGLE_API_KEY.
"""

from __future__ import annotations

import pytest

from app import rag_pipeline
from app.retriever import RetrievedChunk


def test_compute_confidence_empty_chunks_is_zero():
    assert rag_pipeline.compute_confidence([]) == 0.0


def test_compute_confidence_uses_best_distance():
    chunks = [
        RetrievedChunk(text="a", metadata={}, score=0.2),
        RetrievedChunk(text="b", metadata={}, score=0.8),
    ]
    # confidence = 1 - (best_distance / 2) = 1 - 0.1 = 0.9
    assert rag_pipeline.compute_confidence(chunks) == pytest.approx(0.9)


def test_compute_confidence_is_clamped_to_zero_one():
    chunks = [RetrievedChunk(text="a", metadata={}, score=5.0)]
    assert rag_pipeline.compute_confidence(chunks) == 0.0


def test_format_context_includes_source_numbering():
    chunks = [
        RetrievedChunk(text="Check the caliper.", metadata={"file_name": "brake.pdf", "page": 4}, score=0.1),
        RetrievedChunk(text="Torque to 35 Nm.", metadata={"file_name": "brake.pdf", "page": 5}, score=0.2),
    ]
    context = rag_pipeline.format_context(chunks)
    assert "[Source 1] brake.pdf, page 4" in context
    assert "[Source 2] brake.pdf, page 5" in context


def test_build_prompt_includes_question_and_context():
    chunks = [RetrievedChunk(text="Torque to 35 Nm.", metadata={"file_name": "brake.pdf", "page": 5}, score=0.1)]
    prompt = rag_pipeline.build_prompt("How tight should the caliper bolts be?", chunks)
    assert "How tight should the caliper bolts be?" in prompt
    assert "Torque to 35 Nm." in prompt
    assert "Answer ONLY using the information" in prompt  # from system_prompt.txt


def test_run_rag_pipeline_rejects_blank_question():
    with pytest.raises(ValueError):
        rag_pipeline.run_rag_pipeline("   ")


def test_run_rag_pipeline_short_circuits_when_no_chunks(monkeypatch):
    """The core hallucination guardrail: no relevant chunks -> never call the LLM."""
    monkeypatch.setattr(rag_pipeline, "retrieve", lambda *a, **k: [])

    def fail_if_called(*a, **k):
        raise AssertionError("call_gemini must not be called when there is no relevant context")

    monkeypatch.setattr(rag_pipeline, "call_gemini", fail_if_called)

    result = rag_pipeline.run_rag_pipeline("What is the torque spec for a Nexon wheel bolt?")

    assert result.answer == rag_pipeline.NO_CONTEXT_ANSWER
    assert result.sources == []
    assert result.confidence == 0.0


def test_run_rag_pipeline_calls_llm_when_chunks_found(monkeypatch):
    chunk = RetrievedChunk(text="Torque to 35 Nm.", metadata={"file_name": "brake.pdf", "page": 5}, score=0.1)
    monkeypatch.setattr(rag_pipeline, "retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(rag_pipeline, "call_gemini", lambda prompt: "Torque the bolts to 35 Nm [Source 1].")

    result = rag_pipeline.run_rag_pipeline("How tight should the caliper bolts be?")

    assert result.answer == "Torque the bolts to 35 Nm [Source 1]."
    assert result.sources == [chunk]
    assert result.confidence > 0.0
