"""M3 unit tests for the gate in isolation (P1)."""

from app.gate import decide
from app.models import Status
from app.models.schemas import ValidationCheck

_ALL_FIELDS = {
    "vendor": 0.99, "invoice_number": 0.99, "invoice_date": 0.99,
    "currency": 0.99, "subtotal": 0.99, "tax": 0.99, "total": 0.99,
}
_PASS = [ValidationCheck(rule="r", passed=True, message="ok")]


def test_auto_approve_when_confident_and_valid():
    d = decide(_ALL_FIELDS, _PASS)
    assert d.status == Status.auto_approved


def test_low_confidence_forces_review():
    conf = dict(_ALL_FIELDS, total=0.4)
    d = decide(conf, _PASS)
    assert d.status == Status.needs_review
    assert "total" in d.low_confidence_fields


def test_failed_validation_forces_review_even_when_confident():
    failed = [ValidationCheck(rule="totals", passed=False, message="bad math", fields=["total"])]
    d = decide(_ALL_FIELDS, failed)
    assert d.status == Status.needs_review
    assert "total" in d.failed_fields
