"""
app.utils
=========
Shared, dependency-light helpers used across the application. Split into
three focused modules:

    logger.py       - central logging setup + timing decorator
    helpers.py       - small pure-function helpers (hashing, text heuristics)
    file_utils.py    - filesystem helpers (PDF discovery, category inference)

Everything is re-exported here so existing call sites can keep doing
`from app.utils import get_logger, timed, content_hash, ...` without caring
which submodule actually defines it.
"""

from app.utils.file_utils import discover_pdfs, infer_category
from app.utils.helpers import content_hash, guess_section_title, looks_like_scanned_page
from app.utils.logger import get_logger, timed

__all__ = [
    "get_logger",
    "timed",
    "content_hash",
    "guess_section_title",
    "looks_like_scanned_page",
    "discover_pdfs",
    "infer_category",
]
