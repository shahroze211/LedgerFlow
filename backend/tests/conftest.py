"""Test harness: isolated SQLite db, stub provider, in-process queue, fast retries."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

# --- configure the app for tests BEFORE importing any app module ----------- #
_TMP = tempfile.mkdtemp(prefix="ledgerflow_test_")
os.environ.update(
    LEDGERFLOW_DATABASE_URL=f"sqlite:///{_TMP}/test.db",
    LEDGERFLOW_STORAGE_DIR=f"{_TMP}/uploads",
    LEDGERFLOW_LLM_PROVIDER="stub",
    LEDGERFLOW_QUEUE_BACKEND="inprocess",
    LEDGERFLOW_MAX_ATTEMPTS="2",
    LEDGERFLOW_RETRY_BACKOFF_BASE="0",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_known_vendors  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _bootstrap() -> Iterator[None]:
    init_db()
    seed_known_vendors()
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- invoice fixtures (rendered invoice text the stub parses) -------------- #

CLEAN_INVOICE = """\
INVOICE
Vendor: Acme Corporation
Invoice Number: INV-1001
Invoice Date: 2026-03-14
Currency: USD

Description            Qty    Unit Price    Amount
Widget A                2        10.00       20.00
Widget B                1        30.00       30.00

Subtotal: 50.00
Tax: 5.00
Total: 55.00
"""

# total deliberately broken: subtotal + tax = 55, but total says 99 (P2 must catch).
TAMPERED_INVOICE = """\
INVOICE
Vendor: Acme Corporation
Invoice Number: INV-1002
Invoice Date: 2026-03-15
Currency: USD

Description            Qty    Unit Price    Amount
Widget A                2        10.00       20.00
Widget B                1        30.00       30.00

Subtotal: 50.00
Tax: 5.00
Total: 99.00
"""
