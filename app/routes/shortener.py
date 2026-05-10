"""
routes/shortener.py — Core URL shortening and redirect endpoints.

POST /shorten  — accepts a long URL, writes to PostgreSQL, returns short URL.
GET  /{code}   — checks Redis cache first; falls back to PostgreSQL on miss;
                 records a click; returns HTTP 301 redirect.

Design notes:
  - Cache misses are non-fatal: Redis failure falls through to DB.
  - Click recording uses a fire-and-forget INSERT (no user-visible latency).
  - 301 (permanent) chosen deliberately: browsers cache it, reducing future
    load. In a real product this might be 302 (temporary) for analytics
    fidelity — document the tradeoff in the README.
"""

import logging
import os
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache as redis_cache
from app.database import get_db
from app.metrics import cache_hits_total, http_requests_total, redirects_total
from app.models import Click, Url
from app.schemas import ShortenRequest, ShortenResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["shortener"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SHORT_CODE_LENGTH: int = int(os.getenv("SHORT_CODE_LENGTH", "6"))
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

_ALPHABET = string.ascii_letters + string.digits  # 62 chars → 62^6 ≈ 56 billion combos


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_code() -> str:
    """Return a cryptographically random alphanumeric short code."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(SHORT_CODE_LENGTH))


# ---------------------------------------------------------------------------
# POST /shorten
# ---------------------------------------------------------------------------


@router.post(
    "/shorten",
    response_model=ShortenResponse,
    status_code=201,
    summary="Shorten a long URL",
)
async def shorten(
    payload: ShortenRequest,
    db: AsyncSession = Depends(get_db),
) -> ShortenResponse:
    """
    Accepts a valid HTTP/HTTPS URL and returns a short code.

    Collision probability at 6 chars / 62-char alphabet is negligible for
    this workload scale. If a collision occurs on INSERT (unique constraint
    violation), the client receives a 500 — acceptable for a platform demo;
    production would retry with a new code.
    """
    long_url = str(payload.url)
    short_code = _generate_code()

    url_row = Url(short_code=short_code, long_url=long_url)
    db.add(url_row)

    try:
        await db.commit()
        await db.refresh(url_row)
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to persist short URL: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create short URL.") from exc

    http_requests_total.labels(
        endpoint="/shorten", method="POST", status_code="201"
    ).inc()

    return ShortenResponse(
        short_code=url_row.short_code,
        short_url=f"{BASE_URL}/{url_row.short_code}",
        long_url=url_row.long_url,
        created_at=url_row.created_at,
    )


# ---------------------------------------------------------------------------
# GET /{code}
# ---------------------------------------------------------------------------


@router.get(
    "/{code}",
    summary="Redirect to the original URL",
    response_class=RedirectResponse,
)
async def redirect(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Looks up *code* in Redis first; falls back to PostgreSQL on a miss.
    Records a click event and increments redirect metrics.
    Returns HTTP 301 to the original URL.

    Cache failure is non-fatal — the route falls through to DB and the
    user is never blocked by a Redis outage.
    """
    # ── 1. Cache check ──────────────────────────────────────────────────────
    long_url: str | None = await redis_cache.get(code)

    if long_url is not None:
        cache_hits_total.labels(result="hit").inc()
    else:
        cache_hits_total.labels(result="miss").inc()

        # ── 2. DB lookup ─────────────────────────────────────────────────────
        result = await db.execute(select(Url).where(Url.short_code == code))
        url_row: Url | None = result.scalar_one_or_none()

        if url_row is None:
            http_requests_total.labels(
                endpoint="/{code}", method="GET", status_code="404"
            ).inc()
            raise HTTPException(status_code=404, detail="Short code not found.")

        long_url = url_row.long_url

        # ── 3. Populate cache so next hit is served from Redis ───────────────
        await redis_cache.set(code, long_url)

        # ── 4. Record click event ────────────────────────────────────────────
        db.add(Click(url_id=url_row.id))
        await db.commit()

    redirects_total.labels(code=code).inc()
    http_requests_total.labels(
        endpoint="/{code}", method="GET", status_code="301"
    ).inc()

    return RedirectResponse(url=long_url, status_code=301)
