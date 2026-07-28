"""
retriever.py
============
Query-side retrieval for the Vehicle Knowledge Base (RAG).

Loads the persisted ChromaDB collection (via app.services.vector_store) and
runs top-k retrieval, either plain similarity search or Maximal Marginal
Relevance (MMR) for diversity-aware retrieval. Applies a similarity-score
threshold so low-relevance chunks never reach the caller. Retrieval-only —
no LLM call happens in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.config import settings
from app.services.vector_store import list_indexed_documents, load_vector_store
from app.utils import get_logger, timed

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    """A single retrieval result: chunk text, its metadata, and a similarity score."""
    text: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0  # cosine DISTANCE — lower means more similar

    def to_dict(self) -> dict:
        return {"text": self.text, "metadata": self.metadata, "score": self.score}


@timed("Retrieval")
def retrieve(
    query: str,
    top_k: Optional[int] = None,
    category: Optional[str] = None,
    search_type: Optional[str] = None,
    similarity_threshold: Optional[float] = None,
) -> list[RetrievedChunk]:
    """
    Run top-k retrieval against the persisted vector store.

    Args:
        query: natural-language question or search string.
        top_k: number of chunks to return (defaults to settings.top_k).
        category: optional metadata filter (e.g. "manuals", "obd_docs").
        search_type: "similarity" (default) or "mmr" for diversity-aware
            retrieval — useful when top-k similarity results tend to be
            near-duplicates of each other (e.g. a manual repeating the
            same warning across pages).
        similarity_threshold: max cosine distance to accept a chunk
            (defaults to settings.similarity_threshold). Chunks scoring
            worse than this are dropped rather than returned, so a
            downstream LLM never sees clearly irrelevant context.

    Returns:
        A list of RetrievedChunk, ordered from most to least similar,
        already filtered by the threshold.
    """
    if not query or not query.strip():
        raise ValueError("Query must be a non-empty string.")

    top_k = top_k or settings.top_k
    search_type = search_type or settings.search_type
    similarity_threshold = (
        settings.similarity_threshold if similarity_threshold is None else similarity_threshold
    )
    store = load_vector_store()
    search_kwargs: dict = {"filter": {"category": category}} if category else {}

    logger.info(
        "Retrieving | query=%r | top_k=%d | search_type=%s | category=%s | threshold=%.3f",
        query, top_k, search_type, category, similarity_threshold,
    )

    if search_type == "mmr":
        # MMR balances relevance with diversity across the returned set.
        # LangChain's MMR helper doesn't return distance scores directly,
        # so we fetch documents via MMR then re-score them against the
        # query for a consistent RetrievedChunk.score across both modes.
        mmr_docs = store.max_marginal_relevance_search(
            query, k=top_k, lambda_mult=settings.mmr_lambda, **search_kwargs
        )
        scored = store.similarity_search_with_score(query, k=max(top_k * 3, top_k), **search_kwargs)
        score_lookup = {doc.page_content: score for doc, score in scored}
        raw_results = [(doc, score_lookup.get(doc.page_content, 1.0)) for doc in mmr_docs]
    else:
        raw_results = store.similarity_search_with_score(query, k=top_k, **search_kwargs)

    results = [
        RetrievedChunk(text=doc.page_content, metadata=doc.metadata, score=score)
        for doc, score in raw_results
        if score <= similarity_threshold
    ]

    dropped = len(raw_results) - len(results)
    if dropped:
        logger.info("Dropped %d chunk(s) below similarity threshold (%.3f)", dropped, similarity_threshold)

    logger.info("Retrieved %d chunk(s) after filtering", len(results))
    return results


def retrieve_by_dtc_code(dtc_code: str, top_k: Optional[int] = None) -> list[RetrievedChunk]:
    """Convenience wrapper biasing the query text toward a specific DTC code lookup."""
    query = f"Diagnostic trouble code {dtc_code.strip().upper()}"
    return retrieve(query, top_k=top_k)


__all__ = ["RetrievedChunk", "retrieve", "retrieve_by_dtc_code", "list_indexed_documents", "load_vector_store"]
