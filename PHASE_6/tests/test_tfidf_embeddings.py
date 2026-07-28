"""
test_tfidf_embeddings.py
==========================
Unit tests for app.services.tfidf_embeddings.TfidfEmbeddings - the
offline fallback embedding backend for environments without
huggingface.co access.

Includes a regression test for a bug where embed_documents() was called
once per ingestion batch (vector_store.py batches at 200 chunks) and
re-fit a brand new vocabulary/dimensionality on every batch, causing
ChromaDB to reject later batches with a dimension mismatch once the
first batch's dimensionality had already been set for the collection.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.embeddings import Embeddings

from app.services.tfidf_embeddings import TfidfEmbeddings


def test_is_a_langchain_embeddings_subclass():
    assert issubclass(TfidfEmbeddings, Embeddings)


def test_embed_documents_returns_one_vector_per_text(tmp_path: Path):
    emb = TfidfEmbeddings(persist_dir=tmp_path, max_features=32)
    vectors = emb.embed_documents(["the engine is overheating", "brake pads are worn"])
    assert len(vectors) == 2
    assert all(isinstance(v, list) for v in vectors)


def test_embed_documents_persists_vectorizer_to_disk(tmp_path: Path):
    emb = TfidfEmbeddings(persist_dir=tmp_path, max_features=32)
    emb.embed_documents(["the engine is overheating"])
    assert (tmp_path / "tfidf_vectorizer.joblib").exists()


def test_embed_query_reuses_persisted_vectorizer_after_restart(tmp_path: Path):
    """Simulates a fresh process: a new TfidfEmbeddings instance with no
    in-memory state should still be able to embed a query, by loading the
    vectorizer a prior instance persisted to disk."""
    writer = TfidfEmbeddings(persist_dir=tmp_path, max_features=32)
    writer.embed_documents(["the engine is overheating", "brake pads are worn"])

    fresh_instance = TfidfEmbeddings(persist_dir=tmp_path, max_features=32)
    query_vector = fresh_instance.embed_query("overheating engine")
    assert isinstance(query_vector, list)
    assert len(query_vector) > 0


def test_multiple_embed_documents_calls_produce_consistent_dimensionality(tmp_path: Path):
    """Regression test: ingestion calls embed_documents() once per batch
    (see vector_store.store_chunks_in_batches), not once for the whole
    corpus. Every call must return vectors of the same dimensionality, or
    ChromaDB rejects the second batch outright with a dimension-mismatch
    error - this previously happened because each call re-fit a fresh
    vocabulary from scratch instead of reusing the first call's."""
    emb = TfidfEmbeddings(persist_dir=tmp_path, max_features=32)

    first_batch = emb.embed_documents(["the engine is overheating", "brake pads are worn"])
    second_batch = emb.embed_documents(["a completely different vocabulary entirely here"])

    assert len(first_batch[0]) == len(second_batch[0])


def test_query_and_document_vectors_share_dimensionality(tmp_path: Path):
    emb = TfidfEmbeddings(persist_dir=tmp_path, max_features=32)
    doc_vectors = emb.embed_documents(["the engine is overheating"])
    query_vector = emb.embed_query("overheating")
    assert len(doc_vectors[0]) == len(query_vector)


def test_embed_query_before_any_ingestion_raises_helpful_error(tmp_path: Path):
    emb = TfidfEmbeddings(persist_dir=tmp_path, max_features=32)
    try:
        emb.embed_query("anything")
        assert False, "expected a RuntimeError when no fitted vectorizer exists yet"
    except RuntimeError as exc:
        assert "ingestion" in str(exc).lower() or "build_vectordb" in str(exc)
