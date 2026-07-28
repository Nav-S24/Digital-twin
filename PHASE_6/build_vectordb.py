"""
build_vectordb.py
==================
Standalone entry point that builds (or incrementally updates) the ChromaDB
vector store from every PDF under `data/`.

This is a thin wrapper around `app.ingest.main` — it exists so the
project has an obvious, top-level "just run this" script, without
duplicating any ingestion logic.

Usage:
    python build_vectordb.py
    python build_vectordb.py --data-dir data --persist-dir vectordb/chroma_db
    python build_vectordb.py --chunk-size 800 --chunk-overlap 150
"""

from __future__ import annotations

from app.ingest import main

if __name__ == "__main__":
    main()
