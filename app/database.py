"""
database.py — Async SQLAlchemy engine, session factory, and health utilities.

Provides:
  - Async engine configured from DATABASE_URL env var
  - Session factory used as a FastAPI dependency
  - health_check() used by /ready endpoint
  - Connection pool gauge updated on each request
"""

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.metrics import db_connections_active

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

# DATABASE_URL: str = os.environ["DATABASE_URL"]  # fail fast if unset

engine = create_async_engine(
    DATABASE_URL,
    # Pool sizing — conservative defaults safe for a single-instance workload.
    # These become meaningful when multiple replicas run against the same RDS.
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,  # validates connections before handing them out
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Base class for ORM models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncSession:  # type: ignore[return]
    """
    Yield an async DB session and close it when the request is done.
    Updates the db_connections_active gauge around the session lifetime.
    """
    async with AsyncSessionLocal() as session:
        db_connections_active.inc()
        try:
            yield session
        finally:
            db_connections_active.dec()


# ---------------------------------------------------------------------------
# Health check — used by /ready
# ---------------------------------------------------------------------------


async def health_check() -> bool:
    """
    Return True if a lightweight query succeeds, False otherwise.
    Does NOT raise — /ready must handle the boolean, not an exception.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database health check failed: %s", exc)
        return False
