"""Prometheus scrape endpoint + a JSON stats summary for the dashboard header."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import DownstreamRecord, Invoice, Status

router = APIRouter(tags=["observability"])


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    """Lightweight live counts for the review-console header (read from the DB)."""
    rows = db.execute(
        select(Invoice.status, func.count()).group_by(Invoice.status)
    ).all()
    by_status = {status: count for status, count in rows}

    total = sum(by_status.values())
    auto = by_status.get(Status.auto_approved.value, 0) + by_status.get(Status.synced.value, 0)
    needs = by_status.get(Status.needs_review.value, 0)
    processed = total - by_status.get(Status.queued.value, 0) - by_status.get(
        Status.extracting.value, 0
    )

    downstream = db.scalar(select(func.count()).select_from(DownstreamRecord)) or 0
    duplicate_writes = db.scalar(
        select(func.coalesce(func.sum(DownstreamRecord.write_count - 1), 0))
    ) or 0

    return {
        "total": total,
        "by_status": by_status,
        "auto_approval_rate": (auto / processed) if processed else 0.0,
        "needs_review": needs,
        "downstream_records": downstream,
        "duplicate_writes_prevented": int(duplicate_writes),  # proof of idempotency (P3)
        "confidence_threshold": get_settings().confidence_threshold,
    }
