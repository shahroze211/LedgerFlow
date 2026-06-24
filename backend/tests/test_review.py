"""M5 backend: the review approve flow (edit -> re-validate -> sync)."""

from __future__ import annotations

from app.db import SessionLocal
from app.models import DownstreamRecord, Invoice, Status

from .conftest import TAMPERED_INVOICE

# an invoice the stub will read with a garbled label -> low confidence -> needs_review
SCANNED_INVOICE = """\
INVOICE
Vendor: Globex Corporation
lnvo1ce Number: INV-7777
Invoice Date: 2026-04-01
Currency: EUR

Description            Qty    Unit Price    Amount
Cloud Plan              1       120.00      120.00

Subtotal: 120.00
Tax: 24.00
Total: 144.00
"""


def _upload(client, text, name):
    return client.post("/ingest/upload", files={"file": (name, text.encode(), "text/plain")}).json()


def test_approve_blocked_until_math_is_fixed(client):
    """A reviewer cannot approve a record whose arithmetic still fails (P2/P5)."""
    res = _upload(client, TAMPERED_INVOICE, "tampered.txt")
    invoice_id = res["invoice_id"]

    # approve without fixing the total -> 422, still not synced
    bad = client.post(f"/review/{invoice_id}/approve", json={"reviewer": "alice"})
    assert bad.status_code == 422

    db = SessionLocal()
    assert db.get(DownstreamRecord, invoice_id) is None
    db.close()

    # fix the total (55.00) and approve -> approved + synced
    good = client.post(
        f"/review/{invoice_id}/approve",
        json={"reviewer": "alice", "edits": {"total": 55.00}},
    )
    assert good.status_code == 200
    body = good.json()
    assert body["status"] == Status.synced.value
    assert body["approved_by"] == "alice"

    db = SessionLocal()
    rec = db.get(DownstreamRecord, invoice_id)
    db.close()
    assert rec is not None and rec.write_count == 1


def test_low_confidence_scan_routes_to_review(client):
    """A garbled label parses with low confidence -> needs_review (P1)."""
    res = _upload(client, SCANNED_INVOICE, "scan.txt")
    db = SessionLocal()
    inv = db.get(Invoice, res["invoice_id"])
    db.refresh(inv)
    status, conf = inv.status, dict(inv.field_confidence or {})
    db.close()
    assert status == Status.needs_review.value
    # invoice_number was the garbled field -> below threshold
    assert conf.get("invoice_number", 1.0) < 0.85
