"""Seed a demo batch: upload every eval fixture to a running LedgerFlow API.

Use this for a clean end-to-end demo: start the stack, run this, watch the
dashboard fill and the review queue populate with exactly the messy cases.

    python scripts/seed_demo.py                 # -> http://localhost:8000
    LEDGERFLOW_API_URL=http://host:8000 python scripts/seed_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

API = os.getenv("LEDGERFLOW_API_URL", "http://localhost:8000")
FIXTURES = Path(__file__).resolve().parents[1] / "eval" / "fixtures"


def main() -> int:
    files = sorted(FIXTURES.glob("*.txt"))
    if not files:
        print("no fixtures found — run `python eval/generate_fixtures.py` first", file=sys.stderr)
        return 1

    auto = review = dup = 0
    with httpx.Client(base_url=API, timeout=30) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as exc:
            print(f"API not reachable at {API}: {exc}", file=sys.stderr)
            return 1

        for path in files:
            res = client.post(
                "/ingest/upload",
                files={"file": (path.name, path.read_bytes(), "text/plain")},
            ).json()
            status = res["status"]
            if res["duplicate"]:
                dup += 1
            elif status in ("auto_approved", "synced"):
                auto += 1
            elif status == "needs_review":
                review += 1
            print(f"  {path.name:<22} -> {status}{' (dup)' if res['duplicate'] else ''}")

    print(f"\nseeded {len(files)} fixtures: {auto} auto-approved, {review} needs-review, {dup} duplicates")
    print(f"open the console at http://localhost:3000  ·  Grafana at http://localhost:3001")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
