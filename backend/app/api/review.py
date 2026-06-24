"""Review console backend (M5).

The reviewer queue, the approve flow (edit -> re-validate -> sync), and operator
actions on dead-lettered jobs. The approve flow deliberately still enforces the
deterministic validations (P2/P5): a human can override *confidence*, but not the
arithmetic. If totals don't add up, approval is refused with a readable reason.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_event, transition
from ..db import get_db
from ..models import Invoice, Status
from ..models.schemas import ApproveRequest, InvoiceOut, InvoiceSummary
from ..pipeline import HEADLINE_FIELDS, revalidate, sync_invoice
from ..queue import get_queue

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue", response_model=list[InvoiceSummary])
def review_queue(db: Session = Depends(get_db)) -> list[Invoice]:
    stmt = (
        select(Invoice)
        .where(Invoice.status == Status.needs_review.value)
        .order_by(Invoice.created_at.asc())
    )
    return list(db.scalars(stmt))


@router.post("/{invoice_id}/approve", response_model=InvoiceOut)
def approve(invoice_id: str, body: ApproveRequest, db: Session = Depends(get_db)) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if Status(invoice.status) != Status.needs_review:
        raise HTTPException(
            status_code=409,
            detail=f"invoice is {invoice.status}, not needs_review; cannot approve.",
        )

    # 1. apply human edits; an edited field is treated as certain (a person checked it).
    edited: list[str] = []
    if body.edits is not None:
        confidence = dict(invoice.field_confidence or {})
        sources = dict(invoice.field_sources or {})
        for name in HEADLINE_FIELDS:
            value = getattr(body.edits, name, None)
            if value is not None:
                setattr(invoice, name, value)
                confidence[name] = 1.0
                sources[name] = "reviewer edit"
                edited.append(name)
        invoice.field_confidence = confidence
        invoice.field_sources = sources
    if edited:
        record_event(db, invoice, "edit", actor=body.reviewer, detail={"fields": edited})

    # 2. re-validate against the corrected fields.
    checks = revalidate(db, invoice)
    failed = [c for c in checks if not c.passed and c.severity == "error"]
    if failed:
        # human override of confidence is allowed; override of the arithmetic is not.
        invoice.gate_reason = "approval blocked: " + "; ".join(c.message for c in failed)
        db.commit()
        db.refresh(invoice)
        raise HTTPException(
            status_code=422,
            detail={
                "message": "validation still fails after edits; fix the flagged fields.",
                "failed": [c.model_dump() for c in failed],
            },
        )

    # 3. approve -> sync (P5).
    invoice.approved_by = body.reviewer
    invoice.gate_reason = "approved by reviewer after passing all validations."
    transition(db, invoice, Status.approved, actor=body.reviewer)
    sync_invoice(db, invoice, actor=body.reviewer)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/requeue", response_model=InvoiceOut)
def requeue(invoice_id: str, db: Session = Depends(get_db)) -> Invoice:
    """Operator action: send a dead-lettered invoice back through the pipeline (P4)."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if Status(invoice.status) != Status.dead_letter:
        raise HTTPException(status_code=409, detail="only dead_letter invoices can be requeued.")

    invoice.attempts = 0
    invoice.error = None
    transition(db, invoice, Status.queued, actor="operator")
    db.commit()
    get_queue().enqueue(invoice.id)
    db.refresh(invoice)
    return invoice
