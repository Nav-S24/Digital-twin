"""
document_service.py
====================
Turns raw PDFs on disk into deduplicated, metadata-rich chunks ready for
embedding. Three stages, each independently testable:

    load_all_pdfs()      - PDF -> per-page Document objects + metadata
    split_documents()    - pages -> overlapping chunks + content_hash
    deduplicate_chunks() - drops chunks already indexed or repeated in-run
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

try:
    from langchain_community.document_loaders import PyPDFLoader
except ImportError:  # pragma: no cover
    from langchain.document_loaders import PyPDFLoader  # type: ignore

from app.utils import (
    content_hash,
    discover_pdfs,
    get_logger,
    guess_section_title,
    infer_category,
    looks_like_scanned_page,
)

logger = get_logger(__name__)


# --- Loading -----------------------------------------------------------------

def load_pdf(pdf_path: Path, data_dir: Path) -> list[Document]:
    """
    Load a single PDF, attach metadata, and flag pages that look scanned
    (near-zero extracted text) so a human can route them through OCR.
    Returns [] on any failure rather than raising, so one bad file cannot
    abort the whole ingestion run.
    """
    try:
        pages = PyPDFLoader(str(pdf_path)).load()
    except Exception as exc:  # noqa: BLE001 - any bad PDF must be skippable
        logger.warning("Failed to load '%s': %s", pdf_path, exc)
        return []

    category = infer_category(pdf_path, data_dir)
    scanned_page_count = 0

    for page in pages:
        is_scanned = looks_like_scanned_page(page.page_content)
        scanned_page_count += int(is_scanned)
        page.metadata.update(
            {
                "source_path": str(pdf_path),
                "file_name": pdf_path.name,
                "category": category,
                "page": page.metadata.get("page", 0) + 1,  # 1-indexed
                # guess_section_title() returns None when no heading-like
                # line is found (e.g. a page that starts directly with body
                # text). ChromaDB's metadata validator only accepts
                # str/int/float/bool, so a raw None here crashed ingestion
                # on every such page - coerce to "" instead.
                "section_title": guess_section_title(page.page_content) or "",
                "possibly_scanned": is_scanned,
            }
        )

    if scanned_page_count:
        logger.warning(
            "'%s' has %d/%d page(s) with little to no extractable text — "
            "likely scanned images. Recommend running these pages through OCR "
            "(e.g. Tesseract/pypdf's OCR extras) before re-ingesting for full coverage.",
            pdf_path.name, scanned_page_count, len(pages),
        )

    logger.info("Loaded '%s' (%d page(s), category='%s')", pdf_path.name, len(pages), category)
    return pages


def load_all_pdfs(pdf_paths: Iterable[Path], data_dir: Path) -> list[Document]:
    all_documents: list[Document] = []
    for pdf_path in pdf_paths:
        all_documents.extend(load_pdf(pdf_path, data_dir))
    logger.info("Loaded %d total page(s) across all PDFs", len(all_documents))
    return all_documents


def discover_and_load_pdfs(data_dir: Path) -> tuple[list[Path], list[Document]]:
    """Convenience wrapper: find every PDF under data_dir, then load them all."""
    pdf_paths = discover_pdfs(data_dir)
    logger.info("Discovered %d PDF file(s) under '%s'", len(pdf_paths), data_dir)
    documents = load_all_pdfs(pdf_paths, data_dir)
    return pdf_paths, documents


# --- Chunking -----------------------------------------------------------------

def split_documents(documents: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    """Split page-level documents into overlapping chunks, preserving all page metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    for i, chunk in enumerate(chunks):
        source = chunk.metadata.get("file_name", "unknown")
        page = chunk.metadata.get("page", "?")
        chunk.metadata["chunk_id"] = f"{source}::p{page}::c{i}"
        chunk.metadata["content_hash"] = content_hash(chunk.page_content)

    logger.info(
        "Split %d page(s) into %d chunk(s) (chunk_size=%d, overlap=%d)",
        len(documents), len(chunks), chunk_size, chunk_overlap,
    )
    return chunks


# --- Deduplication -----------------------------------------------------------------

def deduplicate_chunks(chunks: list[Document], existing_hashes: set[str]) -> list[Document]:
    """
    Drop chunks whose content_hash already exists in the persisted
    collection (protects against double-insertion when ingestion is
    re-run on the same or overlapping document set) or that repeat
    within the current run (e.g. a boilerplate footer on every page).
    """
    seen_this_run: set[str] = set()
    deduped: list[Document] = []
    skipped = 0

    for chunk in chunks:
        h = chunk.metadata["content_hash"]
        if h in existing_hashes or h in seen_this_run:
            skipped += 1
            continue
        seen_this_run.add(h)
        deduped.append(chunk)

    if skipped:
        logger.info("Skipped %d duplicate chunk(s) (already indexed or repeated within this run)", skipped)
    return deduped
