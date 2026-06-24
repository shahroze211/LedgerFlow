"""Pydantic schemas — the typed contract between the LLM, the API and the UI.

The extraction provider is forced to return ``ExtractionResult``; anything that
does not parse into this shape is a hard failure, not a "best effort" guess.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .status import Status

# --------------------------------------------------------------------------- #
# Extraction contract (what the model must return)
# --------------------------------------------------------------------------- #


class LineItemExtract(BaseModel):
    description: str | None = None
    qty: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    confidence: float = 0.0


class ExtractedFields(BaseModel):
    """Normalized invoice header. Missing values are ``None`` — never guessed."""

    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO 8601 (YYYY-MM-DD)
    currency: str | None = None  # ISO 4217
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    line_items: list[LineItemExtract] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Full provider output: fields + per-field confidence + source spans (P8)."""

    fields: ExtractedFields
    # confidence per header field, 0.0–1.0. Keys mirror ExtractedFields.
    field_confidence: dict[str, float] = Field(default_factory=dict)
    # the raw text span each field was grounded in, for the audit trail + UI highlight.
    field_sources: dict[str, str] = Field(default_factory=dict)
    # provider's own self-check note (extract -> self-check -> emit).
    self_check: str | None = None


# --------------------------------------------------------------------------- #
# Validation + gate
# --------------------------------------------------------------------------- #


class ValidationCheck(BaseModel):
    rule: str
    passed: bool
    severity: str = "error"  # error | warning
    message: str
    fields: list[str] = Field(default_factory=list)  # fields this check implicates


class GateDecision(BaseModel):
    status: Status  # auto_approved | needs_review
    reason: str
    failed_fields: list[str] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# API I/O
# --------------------------------------------------------------------------- #


class LineItemOut(BaseModel):
    description: str | None
    qty: float | None
    unit_price: float | None
    amount: float | None
    confidence: float | None


class InvoiceOut(BaseModel):
    id: str
    content_hash: str
    source_ref: str
    original_filename: str | None = None
    status: Status
    attempts: int

    vendor: str | None = None
    vendor_account_code: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None

    field_confidence: dict[str, float] | None = None
    field_sources: dict[str, str] | None = None
    validation_results: list[ValidationCheck] | None = None
    gate_reason: str | None = None
    approved_by: str | None = None
    error: str | None = None

    line_items: list[LineItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InvoiceSummary(BaseModel):
    id: str
    status: Status
    vendor: str | None = None
    invoice_number: str | None = None
    total: float | None = None
    currency: str | None = None
    gate_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FieldEdit(BaseModel):
    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None


class ApproveRequest(BaseModel):
    """Reviewer submits corrected fields, then approves (re-validate -> sync)."""

    edits: FieldEdit | None = None
    reviewer: str = "reviewer"


class IngestResponse(BaseModel):
    invoice_id: str
    status: Status
    duplicate: bool  # True when this content hash was already ingested (P3)
