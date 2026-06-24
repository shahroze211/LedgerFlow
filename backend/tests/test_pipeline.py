"""M1–M4 acceptance: dedup, gate routing, idempotent sync, dead-letter."""

from __future__ import annotations

import app.pipeline as pipeline_mod
from app.db import SessionLocal
from app.extract.provider import ProviderError
from app.models import DownstreamRecord, Invoice, Status

from .conftest import CLEAN_INVOICE, TAMPERED_INVOICE


def _upload(client, text: str, name: str):
    return client.post(
        "/ingest/upload",
        files={"file": (name, text.encode(), "text/plain")},
    ).json()


def _get(invoice_id: str) -> Invoice:
    db = SessionLocal()
    try:
        inv = db.get(Invoice, invoice_id)
        db.refresh(inv)
        return inv
    finally:
        db.close()


def test_clean_invoice_auto_approves_and_syncs(client):
    """M3: a clean invoice clears the gate; M4: it syncs exactly once."""
    res = _upload(client, CLEAN_INVOICE, "clean.txt")
    assert res["duplicate"] is False
    inv = _get(res["invoice_id"])
    # auto_approved -> immediately synced by the worker
    assert inv.status == Status.synced.value
    assert inv.approved_by == "system"
    assert inv.vendor_account_code == "5000-OFFICE"  # fuzzy-matched to Acme

    # downstream written exactly once
    db = SessionLocal()
    rec = db.get(DownstreamRecord, inv.id)
    db.close()
    assert rec is not None
    assert rec.write_count == 1


def test_dedup_returns_same_record(client):
    """M1 / P3: same bytes ingested twice -> one record."""
    first = _upload(client, CLEAN_INVOICE, "clean.txt")
    second = _upload(client, CLEAN_INVOICE, "clean-again.txt")
    assert second["duplicate"] is True
    assert first["invoice_id"] == second["invoice_id"]


def test_tampered_invoice_is_flagged(client):
    """M3 / P2: subtotal + tax != total forces needs_review with a readable reason."""
    res = _upload(client, TAMPERED_INVOICE, "tampered.txt")
    inv = _get(res["invoice_id"])
    assert inv.status == Status.needs_review.value
    assert "does not equal total" in inv.gate_reason
    # and it must NOT have been written downstream
    db = SessionLocal()
    assert db.get(DownstreamRecord, inv.id) is None
    db.close()


def test_idempotent_resync(client):
    """P3/P5: syncing an already-synced invoice does not create a duplicate row."""
    res = _upload(client, CLEAN_INVOICE, "clean.txt")
    invoice_id = res["invoice_id"]

    db = SessionLocal()
    inv = db.get(Invoice, invoice_id)
    # force a second downstream write directly through the sync target
    from app.sync import get_sync_target

    target = get_sync_target()
    target.write(db, inv)
    db.commit()
    rec = db.get(DownstreamRecord, invoice_id)
    write_count = rec.write_count
    db.close()

    assert write_count == 2  # two writes...
    # ...but still a single row keyed on the invoice id
    db = SessionLocal()
    rows = db.query(DownstreamRecord).filter_by(invoice_id=invoice_id).count()
    db.close()
    assert rows == 1


def test_extraction_failure_dead_letters(client, monkeypatch):
    """M4 / P4: repeated extraction failure dead-letters after max_attempts."""

    def boom(*args, **kwargs):
        raise ProviderError("simulated LLM timeout")

    monkeypatch.setattr(pipeline_mod, "run_extraction", boom)

    res = _upload(client, "Vendor: Ghost\nTotal: 1.00\n", "fail.txt")
    inv = _get(res["invoice_id"])
    assert inv.status == Status.dead_letter.value
    assert inv.attempts == 2  # LEDGERFLOW_MAX_ATTEMPTS in conftest
    assert "simulated LLM timeout" in (inv.error or "")
