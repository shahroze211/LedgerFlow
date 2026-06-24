"""FastAPI application factory + routes.

Routers are mounted per pipeline stage as the milestones land. M0 ships the app
skeleton, DB bootstrap and a health check.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Seed the known-vendor master list so fuzzy matching has something to hit.
    try:
        from .seed import seed_known_vendors

        seed_known_vendors()
    except Exception:  # seeding is best-effort; never block boot on it
        pass
    _load_eval_accuracy()
    yield


def _load_eval_accuracy() -> None:
    """Publish the latest eval field-accuracy as a gauge (P7), if a report exists."""
    import json
    from pathlib import Path

    from .observability.metrics import field_accuracy

    for candidate in ("../eval/last_report.json", "eval/last_report.json", "/app/eval/last_report.json"):
        path = Path(candidate)
        if path.exists():
            try:
                field_accuracy.set(json.loads(path.read_text())["overall_accuracy"])
            except Exception:
                pass
            return


app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.1.0",
    description="Invoice intake automation — confidence-gated autonomy with a human-in-the-loop queue.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "provider": settings.llm_provider,
        "queue": settings.queue_backend,
    }


# --- routers (mounted as milestones land) ---------------------------------- #
def _mount_routers() -> None:
    from .api import ingest_router, invoices_router, metrics_router, review_router

    app.include_router(ingest_router)
    app.include_router(invoices_router)
    app.include_router(review_router)
    app.include_router(metrics_router)


_mount_routers()
