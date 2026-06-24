"""Generate the eval fixture set + ground-truth labels (spec §8).

~30 invoices spanning easy -> nasty, generated deterministically so the rendered
text and the labels can never drift apart. Categories deliberately exercise the
gate:

- clean / foreign-currency / near-duplicate -> should AUTO-APPROVE;
- missing-field   -> required field absent  -> needs_review (and the correct
                     extraction is `null`, proving "don't hallucinate");
- tampered-total  -> reads fine, but fails deterministic arithmetic (P2);
- unknown-vendor  -> fuzzy match misses the master list;
- scanned/garbled -> a noisy label parses with low confidence (P1).

We never use real third-party financial data — vendor names are fictional and
amounts are synthetic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
LABELS_PATH = Path(__file__).parent / "labels.jsonl"

# (vendor string as printed, currency)
_VENDORS = [
    ("Acme Corporation", "USD"),
    ("Globex Corporation", "USD"),
    ("Initech LLC", "USD"),
    ("Umbrella Industries", "EUR"),
    ("Stark Industries", "USD"),
    ("Wayne Enterprises", "GBP"),
    ("Soylent Foods Ltd", "EUR"),
    ("Hooli Inc", "USD"),
    ("Vandelay Imports", "USD"),
    ("Cyberdyne Systems", "JPY"),
]

_ITEMS = [
    ("Professional services", 1, 1200.00),
    ("Cloud subscription", 3, 90.00),
    ("Hardware unit", 2, 240.00),
    ("Lab consumables", 5, 35.00),
    ("Consulting hours", 8, 150.00),
    ("Catering package", 1, 480.00),
    ("Logistics fee", 4, 65.00),
    ("Office supplies", 10, 12.50),
]


@dataclass
class Fixture:
    name: str
    category: str
    vendor: str | None
    invoice_number: str | None
    invoice_date: str | None
    currency: str | None
    line_items: list[tuple[str, int, float]]
    subtotal: float | None
    tax: float | None
    total: float | None
    expected_status: str  # auto_approved | needs_review
    # overrides for the *printed* document when it must diverge from the truth
    printed_total: float | None = None
    drop_fields: list[str] = field(default_factory=list)  # fields absent from the doc
    garble_label: str | None = None  # field whose label is OCR-noised

    def labels(self) -> dict:
        """Ground truth = what a human keying this document would record."""
        # For a genuinely missing field, the correct extraction is null.
        def truth(name, value):
            return None if name in self.drop_fields else value

        return {
            "file": f"{self.name}.txt",
            "category": self.category,
            "expected_status": self.expected_status,
            "fields": {
                "vendor": truth("vendor", self.vendor),
                "invoice_number": truth("invoice_number", self.invoice_number),
                "invoice_date": truth("invoice_date", self.invoice_date),
                "currency": truth("currency", self.currency),
                "subtotal": truth("subtotal", self.subtotal),
                "tax": truth("tax", self.tax),
                # the printed total is the truth for *extraction* even when tampered
                "total": truth("total", self.printed_total if self.printed_total is not None else self.total),
            },
        }


def _garble(label: str) -> str:
    return label.replace("i", "1").replace("o", "0").replace("In", "ln")


def render(fx: Fixture) -> str:
    lines = ["INVOICE", ""]

    def emit(field_name: str, label: str, value):
        if field_name in fx.drop_fields or value is None:
            return
        if fx.garble_label == field_name:
            label = _garble(label)
        lines.append(f"{label}: {value}")

    emit("vendor", "Vendor", fx.vendor)
    emit("invoice_number", "Invoice Number", fx.invoice_number)
    emit("invoice_date", "Invoice Date", fx.invoice_date)
    emit("currency", "Currency", fx.currency)
    lines.append("")
    lines.append(f"{'Description':<26}{'Qty':>5}{'Unit Price':>14}{'Amount':>12}")
    for desc, qty, unit in fx.line_items:
        amount = round(qty * unit, 2)
        lines.append(f"{desc:<26}{qty:>5}{unit:>14.2f}{amount:>12.2f}")
    lines.append("")
    if fx.subtotal is not None:
        lines.append(f"Subtotal: {fx.subtotal:.2f}")
    if fx.tax is not None:
        lines.append(f"Tax: {fx.tax:.2f}")
    printed_total = fx.printed_total if fx.printed_total is not None else fx.total
    if printed_total is not None:
        lines.append(f"Total: {printed_total:.2f}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _mk(idx: int, category: str, expected: str, **kwargs) -> Fixture:
    vendor, currency = _VENDORS[idx % len(_VENDORS)]
    items = [_ITEMS[idx % len(_ITEMS)], _ITEMS[(idx + 3) % len(_ITEMS)]]
    subtotal = round(sum(q * u for _, q, u in items), 2)
    tax = round(subtotal * 0.10, 2)
    total = round(subtotal + tax, 2)
    base = dict(
        name=f"{category}_{idx:02d}",
        category=category,
        vendor=vendor,
        invoice_number=f"INV-{1000 + idx}",
        # dates in the recent past so the "not implausibly future" validator is happy
        invoice_date=f"2025-{(idx % 12) + 1:02d}-{(idx % 27) + 1:02d}",
        currency=currency,
        line_items=items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        expected_status=expected,
    )
    base.update(kwargs)
    return Fixture(**base)


def build_fixtures() -> list[Fixture]:
    fixtures: list[Fixture] = []

    # 22 clean (incl. foreign currency, picked up from the vendor table) -> auto
    for i in range(22):
        fixtures.append(_mk(i, "clean", "auto_approved"))

    # 2 near-duplicates: same vendor, different invoice number -> auto
    for i in (22, 23):
        fx = _mk(0, "near_dup", "auto_approved")
        fx.name = f"near_dup_{i:02d}"
        fx.invoice_number = f"INV-{2000 + i}"
        fixtures.append(fx)

    # 2 missing required field (invoice_date) -> needs_review; truth = null
    for i in (24, 25):
        fixtures.append(_mk(i, "missing_field", "needs_review", drop_fields=["invoice_date"]))

    # 2 tampered total (printed total wrong) -> needs_review via arithmetic (P2)
    for i in (26, 27):
        fx = _mk(i, "tampered", "needs_review")
        fx.printed_total = round(fx.total + 40.00, 2)
        fixtures.append(fx)

    # 1 unknown vendor -> fuzzy match misses -> needs_review
    fx = _mk(28, "unknown_vendor", "needs_review")
    fx.vendor = "Zzyzx Trading Co"
    fixtures.append(fx)

    # 1 scanned / garbled label (low confidence) -> needs_review (P1)
    fixtures.append(_mk(29, "scanned", "needs_review", garble_label="invoice_number"))

    return fixtures


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = build_fixtures()
    with LABELS_PATH.open("w", encoding="utf-8") as labels_file:
        for fx in fixtures:
            (FIXTURES_DIR / f"{fx.name}.txt").write_text(render(fx), encoding="utf-8")
            labels_file.write(json.dumps(fx.labels()) + "\n")
    print(f"generated {len(fixtures)} fixtures into {FIXTURES_DIR}")
    print(f"wrote labels to {LABELS_PATH}")


if __name__ == "__main__":
    main()
