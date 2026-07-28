"""
test_ingestion.py
==================
Unit tests for the document ingestion pipeline (app.services.document_service
and app.utils.file_utils). These tests use synthetic LangChain `Document`
objects and empty placeholder files on disk, so they never need a real PDF,
a downloaded embedding model, or network access.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.documents import Document

from app.services.document_service import deduplicate_chunks, split_documents
from app.utils import content_hash, discover_pdfs, infer_category, looks_like_scanned_page


# --- file_utils -----------------------------------------------------------------

def test_discover_pdfs_finds_nested_files(tmp_path: Path):
    (tmp_path / "manuals").mkdir()
    (tmp_path / "obd_docs").mkdir()
    (tmp_path / "manuals" / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "obd_docs" / "b.PDF").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.txt").write_text("not a pdf")

    found = discover_pdfs(tmp_path)

    assert len(found) == 2
    assert all(p.suffix.lower() == ".pdf" for p in found)


def test_discover_pdfs_missing_dir_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        discover_pdfs(tmp_path / "does_not_exist")


def test_infer_category_uses_first_subfolder(tmp_path: Path):
    pdf_path = tmp_path / "manuals" / "tata_harrier.pdf"
    assert infer_category(pdf_path, tmp_path) == "manuals"


def test_infer_category_file_directly_in_data_dir(tmp_path: Path):
    pdf_path = tmp_path / "loose.pdf"
    assert infer_category(pdf_path, tmp_path) == "uncategorized"


# --- helpers -----------------------------------------------------------------

def test_content_hash_is_stable_and_whitespace_insensitive():
    a = content_hash("Replace   the brake pads.")
    b = content_hash("Replace the brake pads.")
    assert a == b


def test_content_hash_differs_for_different_text():
    assert content_hash("front brakes") != content_hash("rear brakes")


def test_looks_like_scanned_page_flags_near_empty_text():
    assert looks_like_scanned_page("") is True
    assert looks_like_scanned_page("  \n ") is True
    assert looks_like_scanned_page("A" * 30) is False


# --- chunking -----------------------------------------------------------------

def _make_page(text: str, **metadata) -> Document:
    return Document(page_content=text, metadata=metadata)


def test_split_documents_assigns_chunk_id_and_hash():
    pages = [
        _make_page("Torque spec for brake caliper bolts is 35 Nm. " * 20, file_name="brake_service.pdf", page=12),
    ]
    chunks = split_documents(pages, chunk_size=100, chunk_overlap=20)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.metadata["chunk_id"].startswith("brake_service.pdf::p12::c")
        assert len(chunk.metadata["content_hash"]) == 64  # sha256 hex digest


def test_deduplicate_chunks_drops_existing_and_in_run_duplicates():
    chunks = [
        _make_page("Torque spec is 35 Nm.", content_hash="hash_a"),
        _make_page("Torque spec is 35 Nm.", content_hash="hash_a"),  # duplicate within this run
        _make_page("Replace the air filter every 10,000 km.", content_hash="hash_b"),
    ]
    existing_hashes = {"hash_b"}  # already indexed from a previous run

    result = deduplicate_chunks(chunks, existing_hashes)

    assert len(result) == 1
    assert result[0].metadata["content_hash"] == "hash_a"
