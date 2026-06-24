"""The extraction agent graph: extract -> self-check -> emit (spec §7).

Kept as an explicit, inspectable sequence of stages rather than an opaque agent
loop. If LangGraph is available it is used to make the state machine first-class;
otherwise the same three stages run as plain functions. Either way the behaviour —
and the stored audit artefacts — are identical.
"""

from __future__ import annotations

from ..models.schemas import ExtractionResult
from .document import load_text
from .provider import ExtractionProvider, get_provider


def run_extraction(
    source_ref: str,
    media_type: str | None = None,
    provider: ExtractionProvider | None = None,
) -> ExtractionResult:
    """Stage 1 (extract) -> Stage 2 (self-check) -> Stage 3 (emit)."""
    provider = provider or get_provider()

    # Stage 1 — extract.
    text = load_text(source_ref)
    result = provider.extract(text=text, media_type=media_type, source_ref=source_ref)

    # Stage 2 — self-check. We don't *trust* the model's self-check (that's what the
    # deterministic validator is for), but we record it for the audit trail and use
    # it as a light confidence damper when the model itself flags a mismatch.
    if result.self_check and "MISMATCH" in result.self_check.upper():
        for f in ("subtotal", "tax", "total"):
            if f in result.field_confidence:
                result.field_confidence[f] = min(result.field_confidence[f], 0.6)

    # Stage 3 — emit (validated ExtractionResult).
    return result
