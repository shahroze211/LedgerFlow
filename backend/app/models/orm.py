"""SQLAlchemy ORM models — the system of record + full audit trail (P8)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .status import Status


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Invoice(Base):
    """One row per ingested document.

    ``id`` is deterministic (derived from the content hash) so reprocessing the
    same bytes can never create a duplicate (P3).
    """

    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_ref: Mapped[str] = mapped_column(String(1024))  # file path / URL
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[Status] = mapped_column(String(32), default=Status.queued.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    # --- raw + normalized model artefacts (P8: reproducible & explainable) ---
    raw_model_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_confidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # raw text spans
    validation_results: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- normalized headline fields (mirrored out of `extracted` for querying) ---
    vendor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vendor_account_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(32), nullable=True)  # ISO date
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- gate decision + provenance ---
    gate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)  # "system" | reviewer
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    line_items: Mapped[list[LineItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="AuditLog.id"
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")


class KnownVendor(Base):
    """Master vendor list used for fuzzy matching + downstream account coding."""

    __tablename__ = "known_vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512), unique=True)
    aliases: Mapped[list | None] = mapped_column(JSON, default=list)
    account_code: Mapped[str] = mapped_column(String(64))


class AuditLog(Base):
    """Append-only log of every state transition and money-relevant action (P8)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    event: Mapped[str] = mapped_column(String(64))  # e.g. "transition", "sync", "extract"
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    invoice: Mapped[Invoice] = relationship(back_populates="audit_logs")


class DownstreamRecord(Base):
    """The mock "accounting system" table the sync stage writes to.

    Primary key is the invoice id, which is what makes the write idempotent (P3/P5):
    a second sync of the same invoice is an upsert, never a duplicate row.
    """

    __tablename__ = "downstream_records"

    invoice_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    write_count: Mapped[int] = mapped_column(Integer, default=1)  # proves idempotency
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
