"""Downstream sync interface (P5).

Another swappable seam: today it writes to an in-process "accounting system"
table; tomorrow it's a customer's real ERP or a Google Sheet. The contract is the
same and, critically, idempotent on the invoice id.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from ..models import Invoice


class SyncResult:
    def __init__(self, invoice_id: str, created: bool, write_count: int):
        self.invoice_id = invoice_id
        self.created = created  # True on first write, False on idempotent repeat
        self.write_count = write_count


class SyncTarget(Protocol):
    name: str

    def write(self, db: Session, invoice: Invoice) -> SyncResult:
        """Write the invoice downstream. Must be idempotent on ``invoice.id``."""
        ...


def build_payload(invoice: Invoice) -> dict:
    """The canonical record shape we hand to the accounting system."""
    return {
        "invoice_id": invoice.id,
        "vendor": invoice.vendor,
        "vendor_account_code": invoice.vendor_account_code,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "currency": invoice.currency,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "approved_by": invoice.approved_by,
        "line_items": [
            {
                "description": li.description,
                "qty": li.qty,
                "unit_price": li.unit_price,
                "amount": li.amount,
            }
            for li in invoice.line_items
        ],
    }
