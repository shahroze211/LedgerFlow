"""Deterministic validation rules (P2).

The LLM extracts; *this code verifies.* None of these checks call a model. A
failure here forces ``needs_review`` regardless of how confident the model was —
that asymmetry (cheap to flag, expensive to be wrong) is the whole design.
"""

from __future__ import annotations

from datetime import date, timedelta

from dateutil import parser as dateparser

from ..config import get_settings
from ..models.schemas import ExtractedFields, ValidationCheck
from .vendors import VendorMatch

# A pragmatic subset of ISO 4217. Extend freely; the point is "known set", not magic.
ISO_CURRENCIES: frozenset[str] = frozenset(
    {
        "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "INR", "SGD",
        "HKD", "NZD", "SEK", "NOK", "DKK", "ZAR", "AED", "MXN", "BRL", "PLN",
    }
)


def _approx(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def check_required_fields(fields: ExtractedFields) -> ValidationCheck:
    settings = get_settings()
    missing = [
        name
        for name in settings.required_fields
        if getattr(fields, name, None) in (None, "")
    ]
    return ValidationCheck(
        rule="required_fields_present",
        passed=not missing,
        message=(
            "All required fields present."
            if not missing
            else f"Missing required field(s): {', '.join(missing)}."
        ),
        fields=missing,
    )


def check_line_items_sum(fields: ExtractedFields) -> ValidationCheck:
    settings = get_settings()
    if not fields.line_items:
        return ValidationCheck(
            rule="line_items_sum_to_subtotal",
            passed=True,
            severity="warning",
            message="No line items extracted; skipping line-sum check.",
        )
    if fields.subtotal is None:
        return ValidationCheck(
            rule="line_items_sum_to_subtotal",
            passed=False,
            message="Line items present but subtotal is missing.",
            fields=["subtotal"],
        )
    line_sum = sum((li.amount or 0.0) for li in fields.line_items)
    ok = _approx(line_sum, fields.subtotal, settings.amount_tolerance)
    return ValidationCheck(
        rule="line_items_sum_to_subtotal",
        passed=ok,
        message=(
            f"Line items sum to {line_sum:.2f}, matching subtotal {fields.subtotal:.2f}."
            if ok
            else f"Line items sum to {line_sum:.2f} but subtotal is {fields.subtotal:.2f}."
        ),
        fields=[] if ok else ["subtotal"],
    )


def check_totals(fields: ExtractedFields) -> ValidationCheck:
    settings = get_settings()
    if fields.subtotal is None or fields.tax is None or fields.total is None:
        return ValidationCheck(
            rule="subtotal_plus_tax_equals_total",
            passed=False,
            message="Cannot verify totals: subtotal, tax or total is missing.",
            fields=[
                n for n in ("subtotal", "tax", "total") if getattr(fields, n) is None
            ],
        )
    expected = fields.subtotal + fields.tax
    ok = _approx(expected, fields.total, settings.amount_tolerance)
    return ValidationCheck(
        rule="subtotal_plus_tax_equals_total",
        passed=ok,
        message=(
            f"subtotal ({fields.subtotal:.2f}) + tax ({fields.tax:.2f}) = total ({fields.total:.2f})."
            if ok
            else f"subtotal + tax = {expected:.2f}, which does not equal total {fields.total:.2f}."
        ),
        fields=[] if ok else ["total"],
    )


def check_date(fields: ExtractedFields) -> ValidationCheck:
    settings = get_settings()
    if not fields.invoice_date:
        return ValidationCheck(
            rule="invoice_date_sane",
            passed=False,
            message="Invoice date is missing.",
            fields=["invoice_date"],
        )
    try:
        parsed = dateparser.parse(fields.invoice_date).date()
    except (ValueError, TypeError, OverflowError):
        return ValidationCheck(
            rule="invoice_date_sane",
            passed=False,
            message=f"Invoice date '{fields.invoice_date}' does not parse.",
            fields=["invoice_date"],
        )
    today = date.today()
    upper = today + timedelta(days=settings.date_future_days)
    if parsed.year < settings.date_min_year:
        return ValidationCheck(
            rule="invoice_date_sane",
            passed=False,
            message=f"Invoice date {parsed.isoformat()} is before {settings.date_min_year}.",
            fields=["invoice_date"],
        )
    if parsed > upper:
        return ValidationCheck(
            rule="invoice_date_sane",
            passed=False,
            message=f"Invoice date {parsed.isoformat()} is implausibly far in the future.",
            fields=["invoice_date"],
        )
    return ValidationCheck(
        rule="invoice_date_sane",
        passed=True,
        message=f"Invoice date {parsed.isoformat()} parses and is within a sane window.",
    )


def check_currency(fields: ExtractedFields) -> ValidationCheck:
    if not fields.currency:
        return ValidationCheck(
            rule="currency_is_iso",
            passed=False,
            message="Currency is missing.",
            fields=["currency"],
        )
    code = fields.currency.strip().upper()
    ok = code in ISO_CURRENCIES
    return ValidationCheck(
        rule="currency_is_iso",
        passed=ok,
        message=(
            f"Currency '{code}' is a known ISO 4217 code."
            if ok
            else f"Currency '{fields.currency}' is not a recognised ISO 4217 code."
        ),
        fields=[] if ok else ["currency"],
    )


def check_vendor(match: VendorMatch) -> ValidationCheck:
    return ValidationCheck(
        rule="vendor_known",
        passed=match.matched,
        message=(
            f"Vendor matched '{match.name}' (score {match.score:.0f})."
            if match.matched
            else (
                f"Vendor '{match.candidate}' did not match the known-vendor list "
                f"(best score {match.score:.0f})."
            )
        ),
        fields=[] if match.matched else ["vendor"],
    )


def check_amounts_non_negative(fields: ExtractedFields) -> ValidationCheck:
    bad = [
        n
        for n in ("subtotal", "tax", "total")
        if getattr(fields, n) is not None and getattr(fields, n) < 0
    ]
    return ValidationCheck(
        rule="amounts_non_negative",
        passed=not bad,
        message=(
            "All monetary amounts are non-negative."
            if not bad
            else f"Negative amount(s) found: {', '.join(bad)}."
        ),
        fields=bad,
    )


def run_validations(fields: ExtractedFields, vendor_match: VendorMatch) -> list[ValidationCheck]:
    """Run the full deterministic battery. Order is stable for reproducibility."""
    return [
        check_required_fields(fields),
        check_amounts_non_negative(fields),
        check_line_items_sum(fields),
        check_totals(fields),
        check_date(fields),
        check_currency(fields),
        check_vendor(vendor_match),
    ]
