"""
cache.py — Redis async client, GET/SET helpers, and health check.

Provides:
  - Singleton Redis client initialised from REDIS_URL env var
  - get() / set() / delete() wrappers used by redirect route
  - health_check() used by /ready endpoint
  - Redis failures on GET /{code} are non-fatal — the route falls back to DB
"""

import logging
import os

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# REDIS_URL: str = os.environ["REDIS_URL"] # fail fast if unset

# TTL for redirect cache entries (seconds).
# Chosen to balance freshness vs DB load. Configurable at deploy time.
CACHE_TTL: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

# Prefix all keys so the Redis keyspace is self-documenting and easy to flush
# selectively if needed.
_KEY_PREFIX = "redirect:"

# ---------------------------------------------------------------------------
# Client singleton — created once on module import, reused across requests.
# decode_responses=True so we work with str, not bytes, everywhere.
# ---------------------------------------------------------------------------

_client: aioredis.Redis = aioredis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


async def get(short_code: str) -> str | None:
    """
    Return the cached long URL for *short_code*, or None on miss / error.
    Non-fatal: Redis errors are logged and treated as cache misses.
    """
    try:
        return await _client.get(f"{_KEY_PREFIX}{short_code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis GET failed for %s: %s", short_code, exc)
        return None


async def set(short_code: str, long_url: str) -> None:
    """
    Cache *long_url* under *short_code* with the configured TTL.
    Non-fatal: failures are logged but do not interrupt the request.
    """
    try:
        await _client.set(f"{_KEY_PREFIX}{short_code}", long_url, ex=CACHE_TTL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis SET failed for %s: %s", short_code, exc)


async def delete(short_code: str) -> None:
    """Remove a cached entry — called if a short code is ever invalidated."""
    try:
        await _client.delete(f"{_KEY_PREFIX}{short_code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis DELETE failed for %s: %s", short_code, exc)


# ---------------------------------------------------------------------------
# Health check — used by /ready
# ---------------------------------------------------------------------------


async def health_check() -> bool:
    """
    Return True if Redis responds to PING, False otherwise.
    Does NOT raise — /ready handles the boolean.
    """
    try:
        return await _client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis health check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Lifecycle helpers (called from app lifespan)
# ---------------------------------------------------------------------------


async def close() -> None:
    """Gracefully close the Redis connection pool on shutdown."""
    await _client.aclose()
