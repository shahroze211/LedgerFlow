"""Mock accounting-system writer — idempotent on invoice id (P3/P5).

The primary key of ``downstream_records`` is the invoice id, so a second sync of
the same invoice is an UPSERT, not a new row. ``write_count`` is incremented on
repeats purely so a test/demo can *prove* the second write didn't duplicate.

If ``LEDGERFLOW_SYNC_API_URL`` is set, it also POSTs the payload to that endpoint
(a real "mock REST API"); the idempotency guarantee still lives in our keying.
"""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DownstreamRecord, Invoice
from .base import SyncResult, build_payload


class MockApiSyncTarget:
    name = "mock_api"

    def write(self, db: Session, invoice: Invoice) -> SyncResult:
        payload = build_payload(invoice)
        settings = get_settings()

        existing = db.get(DownstreamRecord, invoice.id)
        if existing is None:
            record = DownstreamRecord(invoice_id=invoice.id, payload=payload, write_count=1)
            db.add(record)
            created = True
            write_count = 1
        else:
            # idempotent repeat: refresh payload, bump the proof counter, no new row.
            existing.payload = payload
            existing.write_count += 1
            created = False
            write_count = existing.write_count

        # Optional: mirror to an external mock REST endpoint, keyed idempotently.
        if settings.sync_api_url:
            try:
                httpx.put(
                    f"{settings.sync_api_url.rstrip('/')}/records/{invoice.id}",
                    json=payload,
                    timeout=5.0,
                )
            except httpx.HTTPError:
                # The local system of record is authoritative; external mirror is best-effort.
                pass

        return SyncResult(invoice.id, created=created, write_count=write_count)


def get_sync_target() -> MockApiSyncTarget:
    settings = get_settings()
    if settings.sync_target == "mock_api":
        return MockApiSyncTarget()
    raise ValueError(f"unknown sync target: {settings.sync_target}")
