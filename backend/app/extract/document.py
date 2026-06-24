"""Turn a stored document reference into text the extractor can read.

Kept deliberately small and dependency-light: plain text and common image/pdf
paths. Real vision models would receive the bytes; the stub and text-first
providers receive extracted text.
"""

from __future__ import annotations

from pathlib import Path


def load_text(source_ref: str) -> str:
    """Best-effort text extraction from a file path.

    - ``.txt`` / ``.md`` / ``.csv`` : read directly.
    - ``.pdf`` : use ``pypdf`` if installed, else raise a clear error.
    - anything else : try utf-8 decode, fall back to latin-1.
    """
    path = Path(source_ref)
    if not path.exists():
        raise FileNotFoundError(f"document not found: {source_ref}")

    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".text", ""}:
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # optional dependency
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PDF ingestion requires `pypdf` (pip install pypdf), or feed a real "
                "vision provider instead of extracting text."
            ) from exc
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    # Unknown binary type: try to decode anyway (handles many "text-ish" files).
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")
