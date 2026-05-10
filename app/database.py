"""
database.py — Async SQLAlchemy engine, session factory, and health utilities.

Provides:
  - Async engine configured from DATABASE_URL env var
  - Session factory used as a FastAPI dependency
  - health_check() used by /ready endpoint
  - Connection pool gauge updated on each request
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL
from app.metrics import db_connections_active

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

engine = create_async_engine(
    DATABASE_URL,

    # Pool sizing — conservative defaults safe for a single-instance workload.
    # These become meaningful when multiple replicas run against the same DB.
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,
    echo=False,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# Base class for ORM models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db():
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

    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False