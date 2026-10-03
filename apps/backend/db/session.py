"""Engine, session factory and the FastAPI session dependency.

The engine is created lazily on first use so that importing a module never
opens a database connection, and tests can point ``DATABASE_URL`` at a
throwaway database via :func:`reset_engine`.
"""

from __future__ import annotations

import logging
from typing import Iterator, Optional

from config.settings import get_settings
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        # FastAPI runs sync dependencies in a threadpool.
        return {"check_same_thread": False}
    return {}


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        if url.startswith("sqlite:///./"):
            # Make sure the containing directory exists for file-backed SQLite.
            from pathlib import Path

            Path(url.replace("sqlite:///./", "")).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            url,
            echo=settings.database_echo,
            future=True,
            connect_args=_connect_args(url),
            pool_pre_ping=not url.startswith("sqlite"),
        )
        logger.info("Database engine created (%s)", url.split("://", 1)[0])
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def reset_engine(engine: Optional[Engine] = None) -> None:
    """Drop the cached engine, optionally installing a replacement.

    Used by tests to bind the app to a throwaway database.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = engine
    _session_factory = None


def init_db() -> None:
    """Create any missing tables.

    Convenience for development and tests. Production uses Alembic migrations.
    """
    from db import models, models_audit  # noqa: F401  (register tables on Base.metadata)

    Base.metadata.create_all(bind=get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
