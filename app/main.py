"""
main.py — FastAPI application factory.

Responsibilities:
  - Create the FastAPI app instance
  - Register startup/shutdown lifecycle via lifespan context manager
  - Attach Prometheus middleware for automatic request timing
  - Mount all route modules
  - Expose /metrics endpoint for Prometheus scraping

This file is the ONLY entry point. Everything else is imported, not executed.
"""

import logging
import os
import time

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import cache as redis_cache
from app.database import Base, engine
from app.metrics import http_request_duration_seconds, http_requests_total
from app.routes import health, shortener, stats

# ---------------------------------------------------------------------------
# Logging — stdout, JSON-friendly format for Loki ingestion in Stage 5
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "info").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup and graceful shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """
    Runs before the first request (startup) and after the last (shutdown).

    Startup:
      - Create DB tables if they don't exist (idempotent, safe for reruns).
        In production, schema migrations would be handled by Alembic as a
        pre-deployment job — this async create_all is for dev convenience.
      - Log that the application is ready.

    Shutdown:
      - Close Redis connection pool cleanly.
      - SQLAlchemy disposes the engine pool automatically on GC, but we
        log the event so operators can see clean shutdown in logs.
    """
    # -- Startup -------------------------------------------------------------
    logger.info("Starting URL Shortener application...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema verified / created.")

    logger.info("Application startup complete. Accepting traffic.")
    yield

    # -- Shutdown ------------------------------------------------------------
    logger.info("Shutting down URL Shortener application...")
    await redis_cache.close()
    await engine.dispose()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    application = FastAPI(
        title="URL Shortener",
        description=(
            "Minimal URL Shortener with analytics. "
            "This is a platform engineering workload — the application layer is "
            "intentionally thin. All operational depth lives in the platform layer."
        ),
        version="1.0.0",
        lifespan=lifespan,
        # Disable docs in production via env var — keep them on for dev convenience
        docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
        redoc_url=None,
    )

    # ── Prometheus middleware ────────────────────────────────────────────────
    # Times every request and records it in http_request_duration_seconds.
    # Attached before routes so it wraps ALL handlers including 404s.

    @application.middleware("http")
    async def prometheus_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start

        # Normalise dynamic path params so /{code} doesn't create unbounded
        # cardinality in Prometheus (one label value per unique short code
        # would exhaust memory).
        endpoint = _normalise_path(request.url.path)

        http_request_duration_seconds.labels(endpoint=endpoint).observe(duration)
        http_requests_total.labels(
            endpoint=endpoint,
            method=request.method,
            status_code=str(response.status_code),
        ).inc()

        return response

    # ── Routes ──────────────────────────────────────────────────────────────

    application.include_router(health.router)
    application.include_router(stats.router)

    # ── Prometheus scrape endpoint ───────────────────────────────────────────

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """
        Exposes all registered Prometheus metrics in exposition format.
        Scraped by Prometheus every <scrape_interval> (default 15s in Stage 5).
        """
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return application

    # shortener includes the catch-all /{code} — must be registered last
    application.include_router(shortener.router)

def _normalise_path(path: str) -> str:
    """
    Replace dynamic segments with a placeholder to limit Prometheus cardinality.

    /abc123      → /{code}
    /stats/abc123 → /stats/{code}
    /shorten     → /shorten   (unchanged)
    /health      → /health    (unchanged)
    /ready       → /ready     (unchanged)
    /metrics     → /metrics   (unchanged)
    """
    static = {"/shorten", "/health", "/ready", "/metrics", "/docs"}
    if path in static:
        return path
    parts = path.strip("/").split("/")
    if len(parts) == 1:
        return "/{code}"
    if len(parts) == 2 and parts[0] == "stats":
        return "/stats/{code}"
    return path


# ---------------------------------------------------------------------------
# ASGI entry point
# ---------------------------------------------------------------------------

app = create_app()
