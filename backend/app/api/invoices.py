"""Invoice read endpoints + the original-document view for the review UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..extract.document import load_text
from ..models import AuditLog, Invoice, Status
from ..models.schemas import InvoiceOut, InvoiceSummary

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceSummary])
def list_invoices(
    status: Status | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
) -> list[Invoice]:
    stmt = select(Invoice).order_by(Invoice.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Invoice.status == status.value)
    return list(db.scalars(stmt))


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: str, db: Session = Depends(get_db)) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    return invoice


@router.get("/{invoice_id}/document", response_class=PlainTextResponse)
def get_document(invoice_id: str, db: Session = Depends(get_db)) -> str:
    """The original document text, rendered side-by-side in the review console."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    try:
        return load_text(invoice.source_ref)
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{invoice_id}/audit")
def get_audit(invoice_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """Full audit trail for one invoice (P8)."""
    if db.get(Invoice, invoice_id) is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    logs = db.scalars(
        select(AuditLog).where(AuditLog.invoice_id == invoice_id).order_by(AuditLog.id)
    )
    return [
        {
            "event": log.event,
            "from_status": log.from_status,
            "to_status": log.to_status,
            "actor": log.actor,
            "detail": log.detail,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
