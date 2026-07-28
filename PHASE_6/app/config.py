"""
config.py
=========
Single source of truth for every configurable value in the RAG pipeline.

All settings can be overridden via environment variables (or a `.env` file
in the project root). Nothing downstream (ingest.py, retriever.py,
rag_pipeline.py, api.py, or anything under app/services) should hardcode a
path, model name, or threshold — everything reads from `settings`, imported
from this module.

Environment variables (all optional, sensible defaults provided):
    GOOGLE_API_KEY          - required only when actually calling Gemini
    DATA_DIR                - root folder to scan for PDFs
    PERSIST_DIR             - ChromaDB persistence folder (alias: CHROMA_DB)
    COLLECTION_NAME         - Chroma collection name
    EMBEDDING_MODEL         - HuggingFace embedding model id
    EMBEDDING_DEVICE        - "cpu" or "cuda"
    CHUNK_SIZE              - characters per chunk
    CHUNK_OVERLAP           - character overlap between chunks
    TOP_K                   - default retrieval count
    SIMILARITY_THRESHOLD    - max cosine distance to accept a chunk (lower = stricter)
    SEARCH_TYPE             - "similarity" or "mmr"
    LLM_MODEL               - Gemini model name
    LLM_TEMPERATURE         - generation temperature
    LLM_TIMEOUT_SECONDS     - per-call timeout
    LLM_MAX_RETRIES         - retry attempts on transient failure
    LOG_LEVEL                - Python logging level name
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from pydantic import AliasChoices, Field
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _HAS_PYDANTIC_SETTINGS = True
except ImportError:  # pragma: no cover - fallback if pydantic-settings isn't installed
    from pydantic import BaseModel as BaseSettings  # type: ignore
    from pydantic import Field  # type: ignore
    AliasChoices = None  # type: ignore
    _HAS_PYDANTIC_SETTINGS = False


class Settings(BaseSettings):
    """Application-wide configuration, loaded from environment variables / .env."""

    # --- Paths -------------------------------------------------------------
    data_dir: Path = Path("data")
    # Accepts either PERSIST_DIR (original name) or CHROMA_DB (the name used
    # in .env.example) — keeps both env var conventions working at once.
    persist_dir: Path = (
        Field(
            default=Path("vectordb/chroma_db"),
            validation_alias=AliasChoices("PERSIST_DIR", "CHROMA_DB"),
        )
        if _HAS_PYDANTIC_SETTINGS
        else Path("vectordb/chroma_db")
    )
    collection_name: str = "vehicle_knowledge_base"

    # --- Embedding -----------------------------------------------------------
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_device: str = "cpu"
    # "huggingface" (default, semantic embeddings, requires one-time model
    # download from huggingface.co) or "tfidf" (fully offline fallback -
    # lexical rather than semantic similarity, no external download; useful
    # in network-restricted environments/CI where huggingface.co isn't
    # reachable). See app/services/tfidf_embeddings.py.
    #
    # NOTE: TF-IDF's cosine-distance geometry is not calibrated the same
    # way as the semantic backend's. Short keyword queries ("engine
    # overheating temperature") typically score ~0.6-0.7 distance against
    # a relevant chunk, but full natural-language questions ("What should
    # I do if my engine is overheating?") dilute the query vector with
    # stopwords and commonly score ~0.9+ against the very same chunk. The
    # default SIMILARITY_THRESHOLD of 0.8 below is tuned for the semantic
    # backend and will silently drop every result for natural-language
    # questions under "tfidf" - raise SIMILARITY_THRESHOLD to ~1.0-1.2 via
    # env var when EMBEDDING_BACKEND=tfidf.
    embedding_backend: str = "huggingface"

    # --- Chunking -----------------------------------------------------------
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # --- Retrieval -----------------------------------------------------------
    top_k: int = 5
    similarity_threshold: float = 0.8  # cosine DISTANCE ceiling; higher = more permissive
    search_type: str = "similarity"     # "similarity" or "mmr"
    mmr_lambda: float = 0.5             # relevance/diversity trade-off for MMR

    # --- Generation (Gemini) -----------------------------------------------------------
    google_api_key: str = ""
    llm_model: str = "gemini-1.5-flash"
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 20
    llm_max_retries: int = 3

    # --- Prompts -----------------------------------------------------------
    prompts_dir: Path = Path(__file__).parent / "prompts"

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"

    if _HAS_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def _load_settings() -> Settings:
    """
    Build the Settings object. Falls back to plain os.environ reads if
    pydantic-settings isn't installed, so this module never hard-fails
    just because an optional dependency is missing.
    """
    if _HAS_PYDANTIC_SETTINGS:
        return Settings()

    # Minimal manual fallback (pydantic-settings not installed).
    defaults = Settings()
    for field_name in defaults.model_fields:  # type: ignore[attr-defined]
        env_names = [field_name.upper()]
        if field_name == "persist_dir":
            env_names.append("CHROMA_DB")  # support the .env.example naming too
        env_val = next((os.environ[n] for n in env_names if n in os.environ), None)
        if env_val is not None:
            current = getattr(defaults, field_name)
            cast_type = type(current)
            try:
                setattr(defaults, field_name, cast_type(env_val))
            except (TypeError, ValueError):
                pass
    return defaults


settings = _load_settings()
