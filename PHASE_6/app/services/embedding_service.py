"""
embedding_service.py
=====================
Builds (and caches) the HuggingFace embedding model used at both ingestion
and query time. Both call sites MUST use the identical model, device, and
normalization settings, or query vectors and stored vectors won't live in a
comparable space — this module is the single place that decides those
settings so ingest.py and retriever.py can never drift apart.
"""

from __future__ import annotations

from typing import Optional, Union

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:  # pragma: no cover
    from langchain_community.embeddings import HuggingFaceEmbeddings  # type: ignore

from app.config import settings
from app.services.tfidf_embeddings import TfidfEmbeddings
from app.utils import get_logger

logger = get_logger(__name__)

_embedding_model: Optional[Union[HuggingFaceEmbeddings, TfidfEmbeddings]] = None


def get_embedding_model() -> Union[HuggingFaceEmbeddings, TfidfEmbeddings]:
    """Cached factory — the embedding model is expensive to load, so build it once per process."""
    global _embedding_model
    if _embedding_model is None:
        if settings.embedding_backend == "tfidf":
            logger.warning(
                "Using the offline TF-IDF embedding fallback (EMBEDDING_BACKEND=tfidf). "
                "This is lexical, not semantic, similarity — switch back to the default "
                "'huggingface' backend for production-quality retrieval once internet "
                "access to huggingface.co is available."
            )
            _embedding_model = TfidfEmbeddings(persist_dir=settings.persist_dir)
            return _embedding_model

        logger.info(
            "Loading embedding model '%s' on device '%s'",
            settings.embedding_model, settings.embedding_device,
        )
        # NOTE: `query_instruction` is NOT a valid constructor field on
        # langchain_huggingface's HuggingFaceEmbeddings (checked against
        # versions 0.0.3 through 1.2.2 - it doesn't exist there, so passing
        # it raised a pydantic ValidationError and ingestion/retrieval never
        # succeeded). Removed; BGE-style query prefixing isn't supported by
        # this wrapper version, so document and query embeddings both use
        # plain `encode_kwargs`.
        _embedding_model = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": settings.embedding_device},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embedding_model
