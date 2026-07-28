"""
ingest.py
=========
Document ingestion pipeline for the Vehicle Knowledge Base (RAG).

Recursively loads every PDF under settings.data_dir (data/manuals,
data/obd_docs, data/service_guides, data/maintenance_guides, or any other
subfolder), extracts per-page metadata (source path, category, page number,
best-effort section title), flags likely-scanned pages, splits into
overlapping chunks, deduplicates against both the current run and the
existing persisted collection, embeds in batches, and persists to ChromaDB.

This module is orchestration only — the actual PDF parsing/chunking lives
in app.services.document_service, and the actual ChromaDB access lives in
app.services.vector_store.

Usage:
    python -m app.ingest
    python -m app.ingest --data-dir data --persist-dir vectordb/chroma_db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.document_service import (
    deduplicate_chunks,
    discover_and_load_pdfs,
    split_documents,
)
from app.services.vector_store import fetch_existing_hashes, store_chunks_in_batches
from app.utils import get_logger, timed

logger = get_logger(__name__)


@timed("Ingestion run")
def run_ingestion(data_dir: Path, persist_dir: Path, collection_name: str, chunk_size: int, chunk_overlap: int) -> None:
    logger.info("Starting ingestion | data_dir='%s' | persist_dir='%s'", data_dir, persist_dir)

    pdf_paths, documents = discover_and_load_pdfs(data_dir)
    if not pdf_paths:
        logger.warning("No PDF files found under '%s'. Nothing to ingest.", data_dir)
        return
    if not documents:
        logger.warning("All PDF files failed to load. Nothing to ingest.")
        return

    chunks = split_documents(documents, chunk_size, chunk_overlap)

    existing_hashes = fetch_existing_hashes(persist_dir, collection_name)
    chunks = deduplicate_chunks(chunks, existing_hashes)

    if not chunks:
        logger.info("No new chunks to add — collection is already up to date.")
        return

    store_chunks_in_batches(chunks, persist_dir, collection_name)
    logger.info(
        "Ingestion complete: %d PDF(s) -> %d page(s) -> %d new chunk(s) added",
        len(pdf_paths), len(documents), len(chunks),
    )


# --- CLI -----------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest PDFs into the Vehicle Knowledge Base vector store.")
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    parser.add_argument("--persist-dir", type=Path, default=settings.persist_dir)
    parser.add_argument("--collection-name", type=str, default=settings.collection_name)
    parser.add_argument("--chunk-size", type=int, default=settings.chunk_size)
    parser.add_argument("--chunk-overlap", type=int, default=settings.chunk_overlap)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        run_ingestion(
            data_dir=args.data_dir,
            persist_dir=args.persist_dir,
            collection_name=args.collection_name,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
    except Exception:
        logger.exception("Ingestion run failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
