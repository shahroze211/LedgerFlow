"""Central configuration.

Every tunable that affects *money-relevant behaviour* lives here, not as a magic
number buried in code (spec P1 / §7 "Gate"). Override anything via environment
variables prefixed ``LEDGERFLOW_`` or a ``.env`` file.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEDGERFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ storage
    # SQLite by default so the whole thing runs with zero external services.
    # Point this at postgres in docker-compose: postgresql+psycopg2://...
    database_url: str = "sqlite:///./ledgerflow.db"

    # ------------------------------------------------------------------- queue
    # "inprocess" runs jobs synchronously in the API process (great for the
    # local demo and tests). "redis" uses RQ + Redis (docker-compose path).
    queue_backend: str = "inprocess"  # inprocess | redis
    redis_url: str = "redis://localhost:6379/0"

    # ---------------------------------------------------------------- provider
    llm_provider: str = "stub"  # stub | openai | gemini
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    # ------------------------------------------------------- gate / thresholds
    # P1: confidence-gated autonomy. No record auto-approves if any required
    # field is below this, OR if any deterministic validation fails (P2).
    confidence_threshold: float = 0.85
    required_fields: tuple[str, ...] = (
        "vendor",
        "invoice_number",
        "invoice_date",
        "currency",
        "subtotal",
        "tax",
        "total",
    )

    # ----------------------------------------------------- validation tuning
    amount_tolerance: float = 0.02  # absolute currency tolerance for arithmetic
    vendor_match_threshold: int = 85  # rapidfuzz score 0-100; below => flag
    date_min_year: int = 1990
    date_future_days: int = 30  # invoice dated > now+this many days is suspicious

    # ------------------------------------------------------ retries / dead-letter
    # P4: transient failures retry with backoff; after max_attempts -> dead_letter.
    max_attempts: int = 3
    retry_backoff_base: float = 0.5  # seconds; delay = base * 2**(attempt-1)

    # ----------------------------------------------------------------- sync
    # P5: only gated records sync downstream, idempotent on invoice id.
    # "mock_api" writes to an in-process idempotent store (the "accounting system").
    sync_target: str = "mock_api"  # mock_api
    sync_api_url: str | None = None  # if set, POST to a real mock REST endpoint

    # ----------------------------------------------------------------- ingest
    watch_dir: str = "./invoices"  # folder-watch ingestion source
    storage_dir: str = "./data/uploads"  # where uploaded bytes are persisted

    # --------------------------------------------------------------- metadata
    app_name: str = "LedgerFlow"
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)


@lru_cache
def get_settings() -> Settings:
    return Settings()
