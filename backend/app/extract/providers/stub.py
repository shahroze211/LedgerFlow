"""Deterministic stub provider — an offline stand-in for a real vision/LLM model.

It parses our rendered invoice text format with *fuzzy label matching*, so the
demo runs with zero API keys while still exercising every downstream guardrail:

- clean invoices parse with high confidence -> auto-approve;
- garbled/"scanned" labels match weakly -> low confidence -> needs_review (P1);
- missing fields stay null with zero confidence -> needs_review;
- tampered totals parse fine but fail deterministic arithmetic -> needs_review (P2).

Confidence is a real function of how cleanly each label/value parsed — not a hidden
directive — so the eval harness measures genuine parse accuracy. Swap in the OpenAI
or Gemini provider and the same `ExtractionResult` contract is filled by a real model.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from ...models.schemas import ExtractedFields, ExtractionResult, LineItemExtract

# label synonyms per header field; the parser fuzzy-matches the left side of "label: value".
_LABELS: dict[str, list[str]] = {
    "vendor": ["vendor", "supplier", "from", "bill from", "sold by", "seller"],
    "invoice_number": ["invoice number", "invoice no", "invoice #", "inv no", "inv #", "bill no"],
    "invoice_date": ["invoice date", "date", "issued", "dated", "date of issue"],
    "currency": ["currency", "ccy"],
    "subtotal": ["subtotal", "sub total", "net amount", "net"],
    "tax": ["tax", "vat", "gst", "sales tax"],
    "total": ["total", "amount due", "balance due", "grand total", "total due"],
}

_SYMBOL_CCY = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}

_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")


def _parse_amount(value: str) -> float | None:
    m = _NUM_RE.search(value.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _best_label(left: str) -> tuple[str | None, float]:
    """Return (field_name, score 0-100) for the best-matching label synonym."""
    left_norm = left.strip().lower().rstrip(":").strip()
    best_field, best_score = None, 0.0
    for field, synonyms in _LABELS.items():
        for syn in synonyms:
            score = fuzz.ratio(left_norm, syn)
            # prefer exact-ish containment for short labels like "tax"
            if syn == left_norm:
                score = 100.0
            if score > best_score:
                best_field, best_score = field, score
    return best_field, best_score


def _confidence_from_score(score: float) -> float:
    """Map a 0-100 label-match score to a 0-1 confidence with a realistic curve."""
    if score >= 98:
        return 0.98
    if score >= 90:
        return 0.93
    if score >= 80:
        return 0.82  # just under a typical 0.85 threshold -> flagged
    if score >= 70:
        return 0.70
    return 0.45


class StubProvider:
    name = "stub"

    def extract(
        self, *, text: str, media_type: str | None, source_ref: str
    ) -> ExtractionResult:
        fields = ExtractedFields()
        confidence: dict[str, float] = {}
        sources: dict[str, str] = {}

        lines = [ln.rstrip() for ln in text.splitlines()]

        # --- header fields via "label: value" lines -------------------------
        for raw in lines:
            if ":" not in raw:
                continue
            left, _, right = raw.partition(":")
            value = right.strip()
            if not value:
                continue
            field, score = _best_label(left)
            if field is None or score < 60:
                continue
            # don't overwrite a stronger earlier match
            if field in confidence and confidence[field] >= _confidence_from_score(score):
                continue

            conf = _confidence_from_score(score)
            sources[field] = raw.strip()
            if field in {"subtotal", "tax", "total"}:
                amt = _parse_amount(value)
                setattr(fields, field, amt)
                confidence[field] = conf if amt is not None else 0.3
                # infer currency from a symbol if we haven't found one
                if fields.currency is None:
                    for sym, ccy in _SYMBOL_CCY.items():
                        if sym in value:
                            fields.currency = ccy
                            confidence.setdefault("currency", 0.80)
                            sources.setdefault("currency", raw.strip())
            elif field == "currency":
                fields.currency = value.strip().upper()[:3]
                confidence[field] = conf
            else:
                setattr(fields, field, value)
                confidence[field] = conf

        # --- line items -----------------------------------------------------
        fields.line_items = self._parse_line_items(lines)

        # --- self-check (extract -> self-check -> emit) ---------------------
        self_check = self._self_check(fields)

        return ExtractionResult(
            fields=fields,
            field_confidence=confidence,
            field_sources=sources,
            self_check=self_check,
        )

    @staticmethod
    def _parse_line_items(lines: list[str]) -> list[LineItemExtract]:
        items: list[LineItemExtract] = []
        in_table = False
        for raw in lines:
            low = raw.lower()
            if re.search(r"\b(description|item)\b", low) and re.search(r"\b(amount|qty|price)\b", low):
                in_table = True
                continue
            if in_table:
                if not raw.strip() or re.match(r"\s*(sub\s*total|tax|total|net)", low):
                    in_table = False
                    continue
                nums = _NUM_RE.findall(raw)
                if len(nums) >= 3:
                    desc = _NUM_RE.split(raw)[0].strip()
                    qty = _parse_amount(nums[-3])
                    unit = _parse_amount(nums[-2])
                    amount = _parse_amount(nums[-1])
                    items.append(
                        LineItemExtract(
                            description=desc or None,
                            qty=qty,
                            unit_price=unit,
                            amount=amount,
                            confidence=0.9,
                        )
                    )
        return items

    @staticmethod
    def _self_check(fields: ExtractedFields) -> str:
        notes = []
        if fields.subtotal is not None and fields.tax is not None and fields.total is not None:
            expected = round(fields.subtotal + fields.tax, 2)
            notes.append(
                f"subtotal+tax={expected} vs total={fields.total} "
                f"({'match' if abs(expected - fields.total) <= 0.02 else 'MISMATCH'})"
            )
        if fields.line_items and fields.subtotal is not None:
            s = round(sum((li.amount or 0) for li in fields.line_items), 2)
            notes.append(
                f"line_sum={s} vs subtotal={fields.subtotal} "
                f"({'match' if abs(s - fields.subtotal) <= 0.02 else 'MISMATCH'})"
            )
        return "; ".join(notes) or "insufficient numeric fields to self-check."
