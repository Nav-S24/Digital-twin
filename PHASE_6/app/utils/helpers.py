"""
helpers.py
==========
Small, pure-function helpers with no I/O and no LangChain dependency —
safe to import from anywhere without risk of circular imports.
"""

from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    """
    Stable hash of chunk text, used to detect and skip duplicate chunks —
    both within a single ingestion run (e.g. a boilerplate legal footer
    repeated on every page) and across repeated runs of ingest.py on the
    same document set.
    """
    normalized = " ".join(text.split()).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def looks_like_scanned_page(text: str, min_chars: int = 20) -> bool:
    """
    Heuristic scanned-PDF / image-only-page detector: if PyPDFLoader
    extracts (almost) no text from a page, it's very likely a scanned
    image with no OCR layer rather than a genuinely blank page. This
    doesn't perform OCR itself — it only flags the page so ingestion can
    log a clear, actionable warning recommending an OCR pre-processing step.
    """
    return len(text.strip()) < min_chars


def guess_section_title(page_text: str, max_len: int = 80) -> str | None:
    """
    Lightweight heuristic for a "section title" when no structured
    document outline is available: takes the first non-empty line of a
    page if it looks like a heading (short, no trailing period, not
    mostly numeric). Returns None when no reasonable guess exists —
    callers should treat this as best-effort metadata, not ground truth.
    """
    for line in page_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if len(candidate) > max_len:
            return None
        if candidate.endswith("."):
            return None
        alpha_chars = sum(c.isalpha() for c in candidate)
        if alpha_chars < max(3, len(candidate) // 3):
            return None
        return candidate
    return None
