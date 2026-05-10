"""
schemas.py — Pydantic request/response models.

Validates inputs at the API boundary so invalid data never reaches the DB.
All models use model_config = ConfigDict(from_attributes=True) so they can
be constructed from ORM objects without manual field mapping.
"""

import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# POST /shorten
# ---------------------------------------------------------------------------


class ShortenRequest(BaseModel):
    """Input for the URL shortening endpoint."""

    url: AnyHttpUrl = Field(
        ...,
        description="The long URL to shorten. Must be a valid HTTP/HTTPS URL.",
        examples=["https://example.com/very/long/path?with=query&params=too"],
    )


class ShortenResponse(BaseModel):
    """Response body returned after a URL is successfully shortened."""

    model_config = ConfigDict(from_attributes=True)

    short_code: str = Field(..., description="The generated short code (6 characters).")
    short_url: str = Field(..., description="The fully-qualified short URL ready to share.")
    long_url: str = Field(..., description="The original long URL that was shortened.")
    created_at: datetime.datetime = Field(..., description="UTC timestamp of creation.")


# ---------------------------------------------------------------------------
# GET /stats/{code}
# ---------------------------------------------------------------------------


class StatsResponse(BaseModel):
    """Analytics response for a given short code."""

    model_config = ConfigDict(from_attributes=True)

    short_code: str
    long_url: str
    created_at: datetime.datetime
    click_count: int = Field(..., description="Total number of redirects recorded.")


# ---------------------------------------------------------------------------
# GET /health and GET /ready
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response body for the liveness probe."""

    status: str  # always "alive"


class ReadyResponse(BaseModel):
    """
    Response body for the readiness probe.

    On success (200): {"status": "ready", "postgres": "ok", "redis": "ok"}
    On failure (503): {"status": "degraded", "postgres": "ok"|"error",
                       "redis": "ok"|"error"}
    """

    status: str
    postgres: str  # "ok" | "error"
    redis: str     # "ok" | "error"
