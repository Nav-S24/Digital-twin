"""
vector_store.py
================
All ChromaDB access — persisting chunks, loading the collection for
queries, and the small amount of metadata scanning needed for dedup and
the /documents endpoint — lives in this one module. ingest.py, retriever.py
and api.py should never import Chroma directly; they call through here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

try:
    from langchain_chroma import Chroma
except ImportError:  # pragma: no cover
    from langchain_community.vectorstores import Chroma  # type: ignore

from app.config import settings
from app.services.embedding_service import get_embedding_model
from app.utils import get_logger, timed

logger = get_logger(__name__)

BATCH_SIZE = 200  # chunks embedded/inserted per batch, keeps memory bounded on large corpora

_vector_store: Optional[Chroma] = None


def _open_store(persist_dir: Path, collection_name: str) -> Chroma:
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding_model(),
        persist_directory=str(persist_dir),
    )


def load_vector_store() -> Chroma:
    """Load (or return the cached) persisted Chroma collection written by ingest.py."""
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    if not settings.persist_dir.exists():
        raise FileNotFoundError(
            f"Vector store not found at '{settings.persist_dir}'. Run build_vectordb.py first."
        )

    logger.info("Loading Chroma collection '%s' from '%s'", settings.collection_name, settings.persist_dir)
    store = _open_store(settings.persist_dir, settings.collection_name)

    count = store._collection.count()  # noqa: SLF001 - startup sanity log only
    logger.info("Loaded vector store with %d stored chunk(s)", count)
    if count == 0:
        logger.warning("Vector store is empty. Did build_vectordb.py run successfully?")

    _vector_store = store
    return store


def reset_cache() -> None:
    """Drops the cached store handle so the next load_vector_store() call re-opens it from disk."""
    global _vector_store
    _vector_store = None


def fetch_existing_hashes(persist_dir: Path, collection_name: str) -> set[str]:
    """Load content_hash values already present in the persisted collection, if any."""
    if not persist_dir.exists():
        return set()
    try:
        store = _open_store(persist_dir, collection_name)
        raw = store._collection.get(include=["metadatas"])  # noqa: SLF001 - no public listing API in Chroma
        hashes = {m.get("content_hash") for m in (raw.get("metadatas") or []) if m.get("content_hash")}
        logger.info("Found %d existing chunk hash(es) in persisted collection", len(hashes))
        return hashes
    except Exception as exc:  # noqa: BLE001 - a missing/corrupt store just means "no existing hashes"
        logger.info("No usable existing collection found (%s) — treating as first ingestion run.", exc)
        return set()


@timed("Vector store ingestion")
def store_chunks_in_batches(
    chunks: list[Document],
    persist_dir: Path,
    collection_name: str,
    batch_size: int = BATCH_SIZE,
) -> None:
    """
    Insert chunks in fixed-size batches rather than one giant call, so
    memory usage stays bounded and progress is visible/loggable on large
    document sets.
    """
    persist_dir.mkdir(parents=True, exist_ok=True)
    store = _open_store(persist_dir, collection_name)

    total = len(chunks)
    for start in range(0, total, batch_size):
        batch = chunks[start:start + batch_size]
        store.add_documents(batch)
        logger.info("Inserted batch %d-%d of %d chunks", start + 1, min(start + batch_size, total), total)

    logger.info("Vector store persisted at '%s' (collection='%s')", persist_dir, collection_name)
    reset_cache()  # force retriever.py to pick up the freshly written data on next load


def list_indexed_documents(category: Optional[str] = None) -> list[dict]:
    """
    Returns a summary of distinct documents currently indexed (file name,
    category, chunk count) — powers the /documents endpoint without
    duplicating this Chroma-scanning logic inside api.py.
    """
    store = load_vector_store()
    raw = store._collection.get(include=["metadatas"])  # noqa: SLF001 - Chroma has no public listing API
    metadatas = raw.get("metadatas", []) or []

    counts: dict[tuple[str, str], int] = {}
    for meta in metadatas:
        file_name = meta.get("file_name", "unknown")
        doc_category = meta.get("category", "uncategorized")
        if category and doc_category != category:
            continue
        key = (file_name, doc_category)
        counts[key] = counts.get(key, 0) + 1

    return [
        {"file_name": file_name, "category": doc_category, "chunk_count": count}
        for (file_name, doc_category), count in sorted(counts.items())
    ]
