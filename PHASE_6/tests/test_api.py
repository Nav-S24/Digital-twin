"""
test_api.py
============
Smoke tests for app.api using FastAPI's TestClient. The vector store and
RAG pipeline are monkeypatched so these tests never load a real embedding
model, touch ChromaDB, or call Gemini.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import api
from app.rag_pipeline import RagResult
from app.retriever import RetrievedChunk


@pytest.fixture
def client(monkeypatch):
    # Simulate a successfully-loaded vector store at startup without touching Chroma.
    monkeypatch.setattr(api, "load_vector_store", lambda: object())
    with TestClient(api.app) as test_client:
        yield test_client


def test_health_when_vector_store_unavailable(monkeypatch):
    monkeypatch.setattr(
        api, "load_vector_store",
        lambda: (_ for _ in ()).throw(FileNotFoundError("no vector store")),
    )
    with TestClient(api.app) as test_client:
        response = test_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["vector_store_loaded"] is False


def test_ask_happy_path(client, monkeypatch):
    chunk = RetrievedChunk(
        text="Torque to 35 Nm.",
        metadata={"file_name": "brake.pdf", "category": "service_guides", "page": 5},
        score=0.12,
    )
    fake_result = RagResult(answer="Torque the bolts to 35 Nm.", sources=[chunk], confidence=0.9)
    monkeypatch.setattr(api, "run_rag_pipeline", lambda question, top_k=None, category=None: fake_result)

    response = client.post("/ask", json={"question": "How tight should the caliper bolts be?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Torque the bolts to 35 Nm."
    assert body["confidence"] == 0.9
    assert body["sources"][0]["file_name"] == "brake.pdf"


def test_ask_rejects_blank_question(client):
    response = client.post("/ask", json={"question": ""})
    assert response.status_code == 422  # pydantic min_length validation


def test_search_returns_raw_chunks(client, monkeypatch):
    chunk = RetrievedChunk(text="raw chunk text", metadata={"file_name": "manual.pdf"}, score=0.3)
    monkeypatch.setattr(api, "retrieve", lambda query, **kwargs: [chunk])

    response = client.post("/search", json={"query": "brake pads"})

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["text"] == "raw chunk text"


def test_documents_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        api, "list_indexed_documents",
        lambda category=None: [{"file_name": "brake.pdf", "category": "service_guides", "chunk_count": 42}],
    )

    response = client.get("/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 1
    assert body["documents"][0]["chunk_count"] == 42
