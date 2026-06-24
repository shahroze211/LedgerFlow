"""Pipeline orchestration: extract -> validate -> gate -> (sync).

This is where the swappable pieces are composed into the actual decision about a
piece of money. It is deliberately linear and heavily logged: given the same
inputs it produces the same record, and every step it took is in the audit trail.
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .audit import record_event, transition
from .config import get_settings
from .extract import run_extraction
from .gate import decide
from .models import SYNCABLE, Invoice, LineItem, Status
from .models.schemas import ExtractedFields, ExtractionResult, ValidationCheck
from .observability import metrics
from .sync import get_sync_target
from .validate import match_vendor, run_validations

HEADLINE_FIELDS = ("vendor", "invoice_number", "invoice_date", "currency", "subtotal", "tax", "total")


def _apply_extraction(db: Session, invoice: Invoice, result: ExtractionResult) -> None:
    """Persist raw + normalized extraction artefacts (P8: full audit trail)."""
    fields = result.fields
    invoice.raw_model_output = result.model_dump()
    invoice.extracted = fields.model_dump()
    invoice.field_confidence = dict(result.field_confidence)
    invoice.field_sources = dict(result.field_sources)

    for name in HEADLINE_FIELDS:
        setattr(invoice, name, getattr(fields, name))

    # rebuild line items
    invoice.line_items.clear()
    db.flush()
    for li in fields.line_items:
        invoice.line_items.append(
            LineItem(
                description=li.description,
                qty=li.qty,
                unit_price=li.unit_price,
                amount=li.amount,
                confidence=li.confidence,
            )
        )


def _validate_and_gate(db: Session, invoice: Invoice) -> list[ValidationCheck]:
    """Run vendor match + deterministic validations, store results. Returns checks."""
    fields = ExtractedFields.model_validate(invoice.extracted or {})
    vendor_match = match_vendor(db, fields.vendor)
    if vendor_match.matched:
        invoice.vendor_account_code = vendor_match.account_code

    checks = run_validations(fields, vendor_match)
    invoice.validation_results = [c.model_dump() for c in checks]
    return checks


def process_invoice(db: Session, invoice: Invoice) -> Status:
    """Run extract -> validate -> gate for one invoice. Raises on extraction failure."""
    settings = get_settings()
    started = time.perf_counter()

    transition(db, invoice, Status.extracting)
    db.flush()

    # --- extract --------------------------------------------------------- #
    try:
        result = run_extraction(invoice.source_ref, invoice.media_type)
    except Exception:
        metrics.extraction_errors_total.inc()
        raise  # worker decides retry vs dead-letter (P4)

    _apply_extraction(db, invoice, result)
    record_event(
        db, invoice, "extract", detail={"self_check": result.self_check, "provider": settings.llm_provider}
    )

    # --- validate -------------------------------------------------------- #
    checks = _validate_and_gate(db, invoice)

    # --- gate ------------------------------------------------------------ #
    decision = decide(invoice.field_confidence or {}, checks)
    invoice.gate_reason = decision.reason
    if decision.status == Status.auto_approved:
        invoice.approved_by = "system"

    transition(
        db,
        invoice,
        decision.status,
        detail={
            "reason": decision.reason,
            "low_confidence_fields": decision.low_confidence_fields,
            "failed_fields": decision.failed_fields,
        },
    )

    # --- metrics --------------------------------------------------------- #
    elapsed = time.perf_counter() - started
    metrics.processing_latency_seconds.observe(elapsed)
    metrics.invoices_processed_total.labels(outcome=decision.status.value).inc()
    metrics.rolling.record(
        auto_approved=decision.status == Status.auto_approved,
        had_low_confidence=bool(decision.low_confidence_fields),
    )
    return decision.status


def revalidate(db: Session, invoice: Invoice) -> list[ValidationCheck]:
    """Re-run validation against the *current* (possibly human-edited) fields.

    Used by the review console after a reviewer corrects a field. Confidence on
    human-edited fields is treated as certain (1.0) — a person looked at it.
    """
    # mirror headline fields back into `extracted` so validation sees the edits
    extracted = dict(invoice.extracted or {})
    for name in HEADLINE_FIELDS:
        extracted[name] = getattr(invoice, name)
    invoice.extracted = extracted
    return _validate_and_gate(db, invoice)


def sync_invoice(db: Session, invoice: Invoice, actor: str = "system") -> None:
    """Write an approved/auto-approved invoice downstream, idempotently (P5)."""
    status = Status(invoice.status)
    if status not in SYNCABLE:
        raise ValueError(f"refusing to sync invoice in status {status.value}; not gated.")

    target = get_sync_target()
    res = target.write(db, invoice)
    record_event(
        db,
        invoice,
        "sync",
        actor=actor,
        detail={"target": target.name, "created": res.created, "write_count": res.write_count},
    )
    metrics.invoices_synced_total.labels(created=str(res.created).lower()).inc()
    transition(db, invoice, Status.synced, actor=actor)
