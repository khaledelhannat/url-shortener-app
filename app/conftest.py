"""
conftest.py — Shared pytest fixtures.

Provides:
  - async_engine / async_session: in-memory SQLite for fast, isolated tests
  - client: FastAPI TestClient with DB and Redis dependencies overridden
  - mock_redis: MagicMock for redis cache (avoids needing a live Redis server)

Design decision: tests run against SQLite (aiosqlite) rather than PostgreSQL.
This keeps tests fast and dependency-free in CI. The SQLAlchemy ORM layer
abstracts the difference. Integration tests against real PostgreSQL belong in
a separate test suite run in the CI pipeline after the image is built.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# In-memory SQLite async engine
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create a fresh in-memory SQLite engine per test function."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session bound to the test engine."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# HTTP client with dependencies overridden
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def client(async_engine):
    """
    AsyncClient wired to the FastAPI app with:
      - DB dependency replaced by the test SQLite session
      - Redis cache patched to return cache misses by default
      - database.health_check patched to return True
      - cache.health_check patched to return True
    """
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Patch Redis operations so tests don't need a running Redis
    with (
        patch("app.cache.get", new_callable=AsyncMock, return_value=None) as mock_get,
        patch("app.cache.set", new_callable=AsyncMock) as mock_set,
        patch("app.cache.health_check", new_callable=AsyncMock, return_value=True),
        patch("app.database.health_check", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            ac.mock_cache_get = mock_get  # type: ignore[attr-defined]
            ac.mock_cache_set = mock_set  # type: ignore[attr-defined]
            yield ac

    app.dependency_overrides.clear()
