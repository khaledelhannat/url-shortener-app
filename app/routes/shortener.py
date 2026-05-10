"""
routes/shortener.py — Core URL shortening and redirect endpoints.

POST /shorten  — accepts a long URL, writes to PostgreSQL, returns short URL.
GET  /r/{code} — checks Redis cache first; falls back to PostgreSQL on miss;
                 records a click; returns HTTP 301 redirect.

Design notes:
  - Cache misses are non-fatal: Redis failure falls through to DB.
  - Click recording uses a fire-and-forget INSERT (no user-visible latency).
  - 301 used for simplicity (production may prefer 302 depending on analytics strategy).
"""

import logging
import os
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

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

_ALPHABET = string.ascii_letters + string.digits

MAX_RETRIES = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_code() -> str:
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

    long_url = str(payload.url)

    for attempt in range(MAX_RETRIES):
        short_code = _generate_code()
        url_row = Url(short_code=short_code, long_url=long_url)

        db.add(url_row)

        try:
            await db.commit()
            await db.refresh(url_row)
            break  # success → exit loop

        except IntegrityError:
            await db.rollback()

            # collision → retry
            if attempt == MAX_RETRIES - 1:
                raise HTTPException(
                    status_code=500,
                    detail="Could not generate unique short code. Try again.",
                )

        except Exception as exc:
            await db.rollback()
            logger.error("Failed to persist short URL: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="Failed to create short URL.",
            ) from exc

    http_requests_total.labels(
        endpoint="/shorten", method="POST", status_code="201"
    ).inc()

    return ShortenResponse(
        short_code=url_row.short_code,
        short_url=f"{BASE_URL}/r/{url_row.short_code}",
        long_url=url_row.long_url,
        created_at=url_row.created_at,
    )


# ---------------------------------------------------------------------------
# GET /r/{code}
# ---------------------------------------------------------------------------

@router.get(
    "/r/{code}",
    summary="Redirect to the original URL",
    response_class=RedirectResponse,
)
async def redirect(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:

    # 1. Redis lookup
    long_url: str | None = await redis_cache.get(code)

    if long_url is not None:
        cache_hits_total.labels(result="hit").inc()
    else:
        cache_hits_total.labels(result="miss").inc()

        # 2. DB fallback
        result = await db.execute(select(Url).where(Url.short_code == code))
        url_row: Url | None = result.scalar_one_or_none()

        if url_row is None:
            http_requests_total.labels(
                endpoint="/r/{code}", method="GET", status_code="404"
            ).inc()
            raise HTTPException(status_code=404, detail="Short code not found.")

        long_url = url_row.long_url

        # 3. Cache population (best effort)
        await redis_cache.set(code, long_url)

        # 4. click tracking
        db.add(Click(url_id=url_row.id))
        await db.commit()

    redirects_total.labels(code=code).inc()
    http_requests_total.labels(
        endpoint="/r/{code}", method="GET", status_code="301"
    ).inc()

    return RedirectResponse(url=long_url, status_code=301)