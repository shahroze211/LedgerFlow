"""Job consumer: runs the pipeline with retries + dead-letter (P4).

A transient failure (LLM timeout, parse error) retries with exponential backoff.
After ``max_attempts`` the invoice is moved to ``dead_letter`` and surfaced — never
silently dropped. On success, an ``auto_approved`` invoice is synced immediately;
a ``needs_review`` one waits for a human.

The same ``run_job`` is the RQ task in the Redis path and is called inline in the
in-process path, so behaviour is identical either way.
"""

from __future__ import annotations

import time

from .audit import transition
from .config import get_settings
from .db import session_scope
from .models import Invoice, Status
from .observability import metrics
from .pipeline import process_invoice, sync_invoice


def run_job(invoice_id: str) -> str:
    """Process one invoice to a terminal-for-now state. Returns the final status."""
    settings = get_settings()
    last_error: str | None = None

    for attempt in range(1, settings.max_attempts + 1):
        with session_scope() as db:
            invoice = db.get(Invoice, invoice_id)
            if invoice is None:
                return "missing"
            status = Status(invoice.status)
            if status not in (Status.queued, Status.extracting):
                # already processed (e.g. duplicate enqueue) — nothing to do.
                return status.value

            invoice.attempts = attempt
            try:
                result_status = process_invoice(db, invoice)
            except Exception as exc:  # noqa: BLE001 — we translate to retry/dead-letter
                last_error = str(exc)
                invoice.error = last_error
                if attempt >= settings.max_attempts:
                    transition(
                        db, invoice, Status.dead_letter,
                        detail={"error": last_error, "attempts": attempt},
                    )
                    metrics.dead_letter_total.inc()
                    return Status.dead_letter.value
                # requeue for another attempt
                transition(
                    db, invoice, Status.queued,
                    detail={"error": last_error, "attempt": attempt, "will_retry": True},
                )
            else:
                invoice.error = None
                if result_status == Status.auto_approved:
                    sync_invoice(db, invoice)
                return Status(invoice.status).value

        # backoff happens outside the session so we don't hold a transaction open
        delay = settings.retry_backoff_base * (2 ** (attempt - 1))
        time.sleep(delay)

    return Status.dead_letter.value
