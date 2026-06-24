"""Ingest service: hash -> dedup -> persist bytes -> create record -> enqueue (M1)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from ..audit import record_event
from ..config import get_settings
from ..models import Invoice, Status
from ..observability import metrics
from .hashing import content_hash, invoice_id_from_hash


class IngestOutcome:
    def __init__(self, invoice: Invoice, duplicate: bool):
        self.invoice = invoice
        self.duplicate = duplicate


def ingest_bytes(
    db: Session,
    data: bytes,
    *,
    filename: str | None = None,
    media_type: str | None = None,
    source_ref: str | None = None,
) -> IngestOutcome:
    """Idempotent ingest. Re-ingesting identical bytes returns the existing record (P3)."""
    digest = content_hash(data)
    invoice_id = invoice_id_from_hash(digest)

    existing = db.get(Invoice, invoice_id)
    if existing is not None:
        metrics.invoices_ingested_total.labels(duplicate="true").inc()
        return IngestOutcome(existing, duplicate=True)

    # persist the bytes so the extractor has a stable source_ref to read
    settings = get_settings()
    if source_ref is None:
        storage = Path(settings.storage_dir)
        storage.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix if filename else ".txt"
        stored = storage / f"{invoice_id}{suffix}"
        stored.write_bytes(data)
        source_ref = str(stored)

    invoice = Invoice(
        id=invoice_id,
        content_hash=digest,
        source_ref=source_ref,
        original_filename=filename,
        media_type=media_type,
        status=Status.queued.value,
    )
    db.add(invoice)
    db.flush()
    record_event(
        db, invoice, "ingest", to_status=Status.queued.value, detail={"filename": filename}
    )
    metrics.invoices_ingested_total.labels(duplicate="false").inc()
    return IngestOutcome(invoice, duplicate=False)


def ingest_path(db: Session, path: str) -> IngestOutcome:
    """Ingest a file already on disk (folder-watch path). source_ref points at it."""
    p = Path(path)
    data = p.read_bytes()
    return ingest_bytes(
        db,
        data,
        filename=p.name,
        media_type=None,
        source_ref=str(p.resolve()),
    )
