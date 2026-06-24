"""Content hashing -> deterministic invoice id (P3).

The id is derived from the bytes, so the same document always maps to the same id.
That is what makes both dedup (ingest) and downstream writes (sync) idempotent.
"""

from __future__ import annotations

import hashlib


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def invoice_id_from_hash(digest: str) -> str:
    # short, stable, human-readable-ish id; collision space is 16 hex chars of sha256.
    return f"inv_{digest[:16]}"
