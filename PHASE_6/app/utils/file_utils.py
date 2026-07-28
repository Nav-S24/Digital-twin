"""
file_utils.py
=============
Filesystem-facing helpers: finding PDFs on disk and inferring a document's
category from its folder location under `data/`. Kept separate from
`app.services.document_service` (which does the actual PDF *parsing*) so
"where are the files" stays independent from "what's inside them".
"""

from __future__ import annotations

from pathlib import Path


def discover_pdfs(data_dir: Path) -> list[Path]:
    """Recursively find every PDF under data_dir, at any subfolder depth."""
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    pdf_paths = sorted(set(list(data_dir.rglob("*.pdf")) + list(data_dir.rglob("*.PDF"))))
    return pdf_paths


def infer_category(pdf_path: Path, data_dir: Path) -> str:
    """First-level subfolder becomes the document category (manuals, obd_docs, ...)."""
    try:
        relative = pdf_path.relative_to(data_dir)
    except ValueError:
        return "uncategorized"
    parts = relative.parts
    return parts[0] if len(parts) > 1 else "uncategorized"
