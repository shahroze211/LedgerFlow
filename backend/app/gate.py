"""The gate (P1) — confidence-gated autonomy.

A record is ``auto_approved`` **iff** *every* required field clears the confidence
threshold **and** *every* deterministic validation passes. Anything else is
``needs_review``. There is no third path, and the thresholds come from config,
never magic numbers in code.

This function is intentionally tiny and pure: given fields, confidences and
validation results it returns a decision. That makes it trivially unit-testable,
which is exactly what you want guarding real money.
"""

from __future__ import annotations

from .config import get_settings
from .models import Status
from .models.schemas import GateDecision, ValidationCheck


def decide(
    field_confidence: dict[str, float],
    validations: list[ValidationCheck],
) -> GateDecision:
    settings = get_settings()
    threshold = settings.confidence_threshold

    # 1. Confidence gate: every *required* field must clear the threshold.
    low_conf = [
        name
        for name in settings.required_fields
        if field_confidence.get(name, 0.0) < threshold
    ]

    # 2. Validation gate: every error-severity check must pass.
    failed = [c for c in validations if not c.passed and c.severity == "error"]
    failed_fields = sorted({f for c in failed for f in c.fields})

    if not low_conf and not failed:
        return GateDecision(
            status=Status.auto_approved,
            reason="All required fields cleared the confidence threshold and all validations passed.",
        )

    reasons: list[str] = []
    if low_conf:
        reasons.append(
            f"low confidence (<{threshold:.2f}) on: {', '.join(low_conf)}"
        )
    if failed:
        reasons.append(
            "failed validation: " + "; ".join(c.message for c in failed)
        )
    return GateDecision(
        status=Status.needs_review,
        reason=" | ".join(reasons),
        failed_fields=failed_fields,
        low_confidence_fields=low_conf,
    )
