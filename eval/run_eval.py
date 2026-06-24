"""Eval harness + CI gate (spec §8 / P6).

Runs the real extraction provider over the labelled fixtures and reports:
  - per-field and overall extraction accuracy,
  - the gate's auto-approval rate at the configured threshold,
  - whether the gate's routing matches the expected status per fixture.

Exits non-zero if overall accuracy < floor, so CI fails on a regression. This is
the MLOps-instinct-applied-to-LLMs differentiator: the model's quality is a
*build-breaking* contract, not a vibe.

Usage:
    python eval/run_eval.py                 # uses LEDGERFLOW_LLM_PROVIDER (default stub)
    python eval/run_eval.py --floor 0.90
    python eval/run_eval.py --simulate-regression   # demonstrates a red CI run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Use an isolated eval DB so we never touch a real one; allow override.
_EVAL_DB = Path(tempfile.gettempdir()) / "ledgerflow_eval.db"
os.environ.setdefault("LEDGERFLOW_DATABASE_URL", f"sqlite:///{_EVAL_DB.as_posix()}")
os.environ.setdefault("LEDGERFLOW_QUEUE_BACKEND", "inprocess")

# make `app` importable whether run from repo root or eval/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.extract import run_extraction  # noqa: E402
from app.gate import decide  # noqa: E402
from app.models import Status  # noqa: E402
from app.models.schemas import ExtractedFields  # noqa: E402
from app.seed import seed_known_vendors  # noqa: E402
from app.validate import match_vendor, run_validations  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
LABELS_PATH = Path(__file__).parent / "labels.jsonl"
REPORT_PATH = Path(__file__).parent / "last_report.json"

HEADLINE = ("vendor", "invoice_number", "invoice_date", "currency", "subtotal", "tax", "total")
NUMERIC = {"subtotal", "tax", "total"}


def _norm(field: str, value) -> object | None:
    if value is None:
        return None
    if field in NUMERIC:
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None
    return str(value).strip().lower()


def _field_correct(field: str, expected, got) -> bool:
    e, g = _norm(field, expected), _norm(field, got)
    if field in NUMERIC and e is not None and g is not None:
        return abs(e - g) <= 0.01
    return e == g


def evaluate(simulate_regression: bool = False) -> dict:
    init_db()
    seed_known_vendors()
    settings = get_settings()
    threshold = settings.confidence_threshold

    labels = [json.loads(line) for line in LABELS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    per_field_total = {f: 0 for f in HEADLINE}
    per_field_correct = {f: 0 for f in HEADLINE}

    auto_approved = 0
    gate_correct = 0
    rows = []

    db = SessionLocal()
    try:
        for label in labels:
            path = FIXTURES_DIR / label["file"]
            result = run_extraction(str(path))
            fields = result.fields

            if simulate_regression:
                # simulate a prompt/model regression: drop two numeric fields.
                fields.subtotal = None
                fields.total = None
                result.field_confidence.pop("subtotal", None)
                result.field_confidence.pop("total", None)

            # --- extraction accuracy ---
            row_correct = 0
            for f in HEADLINE:
                per_field_total[f] += 1
                if _field_correct(f, label["fields"][f], getattr(fields, f)):
                    per_field_correct[f] += 1
                    row_correct += 1

            # --- gate routing (uses the real validators + gate) ---
            vendor_match = match_vendor(db, fields.vendor)
            checks = run_validations(ExtractedFields.model_validate(fields.model_dump()), vendor_match)
            decision = decide(result.field_confidence, checks)
            predicted = decision.status
            if predicted == Status.auto_approved:
                auto_approved += 1
            if predicted.value == label["expected_status"]:
                gate_correct += 1

            rows.append(
                {
                    "file": label["file"],
                    "category": label["category"],
                    "fields_correct": row_correct,
                    "predicted_status": predicted.value,
                    "expected_status": label["expected_status"],
                    "gate_ok": predicted.value == label["expected_status"],
                }
            )
    finally:
        db.close()

    total_fields = sum(per_field_total.values())
    correct_fields = sum(per_field_correct.values())
    overall = correct_fields / total_fields if total_fields else 0.0

    return {
        "provider": settings.llm_provider,
        "threshold": threshold,
        "n_fixtures": len(labels),
        "overall_accuracy": round(overall, 4),
        "per_field_accuracy": {
            f: round(per_field_correct[f] / per_field_total[f], 4) for f in HEADLINE
        },
        "auto_approval_rate": round(auto_approved / len(labels), 4) if labels else 0.0,
        "gate_routing_accuracy": round(gate_correct / len(labels), 4) if labels else 0.0,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LedgerFlow eval gate")
    parser.add_argument("--floor", type=float, default=float(os.getenv("LEDGERFLOW_EVAL_FLOOR", "0.90")))
    parser.add_argument("--simulate-regression", action="store_true")
    args = parser.parse_args()

    report = evaluate(simulate_regression=args.simulate_regression)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nLedgerFlow eval — provider={report['provider']} threshold={report['threshold']}")
    print(f"  fixtures:              {report['n_fixtures']}")
    print(f"  overall accuracy:      {report['overall_accuracy']:.1%}")
    print(f"  auto-approval rate:    {report['auto_approval_rate']:.1%}")
    print(f"  gate routing accuracy: {report['gate_routing_accuracy']:.1%}")
    print("  per-field accuracy:")
    for field_name, acc in report["per_field_accuracy"].items():
        print(f"    {field_name:<16} {acc:.1%}")

    floor = args.floor
    passed = report["overall_accuracy"] >= floor
    print(f"\n  floor: {floor:.1%} -> {'PASS' if passed else 'FAIL'}")
    if not passed:
        print("  EVAL GATE FAILED: extraction accuracy dropped below the floor.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
