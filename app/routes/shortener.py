import logging
import os
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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

_ALPHABET = string.ascii_letters + string.digits
MAX_RETRIES = 5


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

    last_error = None

    for _ in range(MAX_RETRIES):
        short_code = _generate_code()

        url_row = Url(short_code=short_code, long_url=long_url)
        db.add(url_row)

        try:
            await db.commit()
            await db.refresh(url_row)
            break

        except IntegrityError as exc:
            await db.rollback()
            last_error = exc
            logger.warning("Collision detected for code=%s, retrying...", short_code)
            continue

        except Exception as exc:
            await db.rollback()
            logger.error("Failed to persist short URL: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to create short URL.") from exc
    else:
        raise HTTPException(
            status_code=500,
            detail="Could not generate unique short code after retries.",
        )

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

    long_url = await redis_cache.get(code)

    if long_url is not None:
        cache_hits_total.labels(result="hit").inc()
    else:
        cache_hits_total.labels(result="miss").inc()

        result = await db.execute(select(Url).where(Url.short_code == code))
        url_row: Url | None = result.scalar_one_or_none()

        if url_row is None:
            http_requests_total.labels(
                endpoint="/r/{code}", method="GET", status_code="404"
            ).inc()
            raise HTTPException(status_code=404, detail="Short code not found.")

        long_url = url_row.long_url
        await redis_cache.set(code, long_url)

        db.add(Click(url_id=url_row.id))
        await db.commit()

    redirects_total.labels(code=code).inc()

    return RedirectResponse(url=long_url, status_code=307)