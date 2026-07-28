"""
test_load_pdf_metadata.py
===========================
Regression test for a bug in load_pdf(): when
guess_section_title() can't find a heading-like line on a page (the
common case for a page that starts directly with body text - most pages
in a real document), it returns None. That None was written straight
into chunk.metadata["section_title"], but ChromaDB's metadata validator
only accepts str/int/float/bool - a raw None crashed ingestion on every
such page. This wasn't caught by the existing mocked-service tests
because those tests never build a real Chroma collection from a real
PDF; it only surfaced once real content was added to the knowledge base.
"""

from __future__ import annotations

from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab", reason="reportlab needed to build a throwaway test PDF")

from reportlab.pdfgen import canvas  # noqa: E402

from app.services.document_service import load_pdf  # noqa: E402


def _make_pdf_with_body_only_first_line(path: Path) -> None:
    """A page whose first line is a long, period-terminated sentence -
    guess_section_title() can't treat that as a heading, so it returns
    None for this page."""
    c = canvas.Canvas(str(path))
    c.drawString(72, 750, "This page intentionally starts with a full sentence, not a heading.")
    c.drawString(72, 730, "It continues with more body text on a second line for good measure.")
    c.showPage()
    c.save()


def test_section_title_is_never_none_in_metadata(tmp_path: Path):
    data_dir = tmp_path / "data"
    (data_dir / "manuals").mkdir(parents=True)
    pdf_path = data_dir / "manuals" / "body_only.pdf"
    _make_pdf_with_body_only_first_line(pdf_path)

    pages = load_pdf(pdf_path, data_dir)

    assert len(pages) == 1
    # The bug: this was None, which ChromaDB's metadata validator rejects
    # outright (str/int/float/bool only). Must be a string (possibly empty).
    assert isinstance(pages[0].metadata["section_title"], str)


def test_all_metadata_values_are_chroma_compatible_types(tmp_path: Path):
    """Every metadata value produced for a chunk must be a type ChromaDB's
    validator accepts - None is explicitly not one of them."""
    data_dir = tmp_path / "data"
    (data_dir / "manuals").mkdir(parents=True)
    pdf_path = data_dir / "manuals" / "body_only.pdf"
    _make_pdf_with_body_only_first_line(pdf_path)

    pages = load_pdf(pdf_path, data_dir)

    allowed_types = (str, int, float, bool)
    for page in pages:
        for key, value in page.metadata.items():
            assert isinstance(value, allowed_types), (
                f"metadata['{key}'] = {value!r} ({type(value).__name__}) "
                f"is not a ChromaDB-compatible type"
            )
