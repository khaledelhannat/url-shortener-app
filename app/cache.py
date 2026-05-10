"""
cache.py — Redis async client, GET/SET helpers, and health check.

Provides:
  - Singleton Redis client initialised from REDIS_URL env var
  - get() / set() / delete() wrappers used by redirect route
  - health_check() used by /ready endpoint
  - Redis failures on GET /{code} are non-fatal — fallback to DB
"""

import logging

from app.config import REDIS_URL, CACHE_TTL

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

if not REDIS_URL:
    raise ValueError("REDIS_URL is not set")

_KEY_PREFIX = "redirect:"

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: aioredis.Redis = aioredis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get(short_code: str) -> str | None:
    try:
        return await _client.get(f"{_KEY_PREFIX}{short_code}")
    except Exception as exc:
        logger.warning("Redis GET failed for %s: %s", short_code, exc)
        return None


async def set(short_code: str, long_url: str) -> None:
    try:
        await _client.set(
            f"{_KEY_PREFIX}{short_code}",
            long_url,
            ex=CACHE_TTL,
        )
    except Exception as exc:
        logger.warning("Redis SET failed for %s: %s", short_code, exc)


async def delete(short_code: str) -> None:
    try:
        await _client.delete(f"{_KEY_PREFIX}{short_code}")
    except Exception as exc:
        logger.warning("Redis DELETE failed for %s: %s", short_code, exc)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def health_check() -> bool:
    try:
        return await _client.ping()
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def close() -> None:
    await _client.aclose()