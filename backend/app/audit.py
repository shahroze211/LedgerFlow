"""Audit + state-transition helpers (P8).

All status changes go through :func:`transition` so that (a) the state machine is
enforced in exactly one place and (b) every change lands in the append-only audit
log. Nothing flips an invoice's status by assigning ``invoice.status`` directly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog, Invoice, Status, assert_transition


def record_event(
    db: Session,
    invoice: Invoice,
    event: str,
    *,
    actor: str = "system",
    from_status: str | None = None,
    to_status: str | None = None,
    detail: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        invoice_id=invoice.id,
        event=event,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        detail=detail,
    )
    db.add(log)
    return log


def transition(
    db: Session,
    invoice: Invoice,
    target: Status,
    *,
    actor: str = "system",
    detail: dict | None = None,
) -> None:
    """Move ``invoice`` to ``target``, enforcing the state machine and logging it.

    Raises :class:`InvalidTransition` if the move is illegal — which is the point:
    a money-relevant record can never reach an inconsistent state silently.
    """
    current = Status(invoice.status)
    assert_transition(current, target)
    invoice.status = target.value
    record_event(
        db,
        invoice,
        "transition",
        actor=actor,
        from_status=current.value,
        to_status=target.value,
        detail=detail,
    )
