"""Database engine + session factory.

Uses SQLAlchemy so the same models run on SQLite (local, zero-config) or
Postgres/Supabase (set DATABASE_URL). SQLite needs `check_same_thread=False`
because FastAPI serves requests across threads.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

def _normalize_url(url: str) -> str:
    """Accept the connection string Supabase/Postgres hands you verbatim.

    SQLAlchemy needs the `postgresql+psycopg2://` driver prefix; Supabase gives
    `postgresql://` (or the legacy `postgres://`). Normalize both.
    """
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    return url


_db_url = _normalize_url(settings.database_url)
_is_sqlite = _db_url.startswith("sqlite")
_connect_args: dict = {}
_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}

if _is_sqlite:
    _connect_args["check_same_thread"] = False
else:
    # Postgres / Supabase: require SSL, recycle pooled connections (the pooler
    # closes idle ones), and keep a modest pool sized for a demo backend.
    if "sslmode=" not in _db_url:
        _connect_args["sslmode"] = "require"
    _engine_kwargs.update(pool_size=5, max_overflow=5, pool_recycle=300)

engine = create_engine(_db_url, connect_args=_connect_args, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Idempotent; safe to call on startup."""
    from app.db import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
