"""Ingest endpoints (M1): upload a file or ingest a server-side path."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..ingest import ingest_bytes
from ..models import Status
from ..models.schemas import IngestResponse
from ..queue import get_queue

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/upload", response_model=IngestResponse)
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)) -> IngestResponse:
    data = await file.read()
    outcome = ingest_bytes(
        db, data, filename=file.filename, media_type=file.content_type
    )
    db.commit()

    if not outcome.duplicate:
        # enqueue *after* commit so the worker can read the row (P3: dedup already done)
        get_queue().enqueue(outcome.invoice.id)
        db.refresh(outcome.invoice)

    return IngestResponse(
        invoice_id=outcome.invoice.id,
        status=Status(outcome.invoice.status),
        duplicate=outcome.duplicate,
    )
