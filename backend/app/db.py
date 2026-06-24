"""Database engine + session management.

Storage is a swappable seam: SQLite for the zero-dependency local demo, Postgres
in docker-compose. The ORM uses the cross-dialect ``JSON`` type so the same models
work on both (Postgres stores it as ``jsonb`` under the hood).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_connect_args = (
    {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(
    _settings.database_url,
    connect_args=_connect_args,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create tables. Idempotent; safe to call on every boot."""
    from . import models  # noqa: F401  (registers ORM classes on Base.metadata)

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for worker / scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
