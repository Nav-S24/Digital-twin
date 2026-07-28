"""
test_retriever.py
==================
Unit tests for app.retriever. The actual ChromaDB store is mocked out via
monkeypatch, so these tests never download an embedding model or touch disk.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from app import retriever


class _FakeStore:
    """Stands in for a langchain_chroma.Chroma instance."""

    def __init__(self, scored_docs):
        self._scored_docs = scored_docs  # list[(Document, score)]

    def similarity_search_with_score(self, query, k, **kwargs):
        return self._scored_docs[:k]

    def max_marginal_relevance_search(self, query, k, lambda_mult, **kwargs):
        return [doc for doc, _ in self._scored_docs[:k]]


def test_retrieve_rejects_blank_query():
    with pytest.raises(ValueError):
        retriever.retrieve("   ")


def test_retrieve_filters_by_similarity_threshold(monkeypatch):
    docs = [
        (Document(page_content="close match", metadata={"file_name": "a.pdf"}), 0.1),
        (Document(page_content="far match", metadata={"file_name": "b.pdf"}), 0.9),
    ]
    monkeypatch.setattr(retriever, "load_vector_store", lambda: _FakeStore(docs))

    results = retriever.retrieve("brake pads", top_k=2, similarity_threshold=0.5)

    assert len(results) == 1
    assert results[0].text == "close match"
    assert results[0].metadata["file_name"] == "a.pdf"


def test_retrieved_chunk_to_dict_roundtrip():
    chunk = retriever.RetrievedChunk(text="hello", metadata={"page": 3}, score=0.2)
    assert chunk.to_dict() == {"text": "hello", "metadata": {"page": 3}, "score": 0.2}


def test_retrieve_by_dtc_code_builds_expected_query(monkeypatch):
    captured = {}

    def fake_retrieve(query, top_k=None, **kwargs):
        captured["query"] = query
        captured["top_k"] = top_k
        return []

    monkeypatch.setattr(retriever, "retrieve", fake_retrieve)

    retriever.retrieve_by_dtc_code(" p0301 ", top_k=3)

    assert captured["query"] == "Diagnostic trouble code P0301"
    assert captured["top_k"] == 3
