"""
routes/stats.py — Analytics endpoint for a given short code.

GET /stats/{code}
  Returns click count and URL metadata.
  Uses a COUNT query against the clicks table rather than a cached value
  so the number is always accurate (no stale reads).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Click, Url
from app.schemas import StatsResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])


@router.get(
    "/stats/{code}",
    response_model=StatsResponse,
    summary="Get click analytics for a short code",
)
async def stats(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """
    Returns metadata and total click count for *code*.

    Click count is computed with a COUNT(*) aggregate on the clicks table.
    This is a read-only endpoint — no writes, no side effects.
    """
    # Fetch the URL row
    url_result = await db.execute(select(Url).where(Url.short_code == code))
    url_row: Url | None = url_result.scalar_one_or_none()

    if url_row is None:
        raise HTTPException(status_code=404, detail="Short code not found.")

    # Count clicks for this URL
    count_result = await db.execute(
        select(func.count()).where(Click.url_id == url_row.id)
    )
    click_count: int = count_result.scalar_one()

    return StatsResponse(
        short_code=url_row.short_code,
        long_url=url_row.long_url,
        created_at=url_row.created_at,
        click_count=click_count,
    )
