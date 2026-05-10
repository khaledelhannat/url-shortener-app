"""
main.py — FastAPI application factory.

Responsibilities:
  - Create the FastAPI app instance
  - Register startup/shutdown lifecycle via lifespan context manager
  - Attach Prometheus middleware for automatic request timing
  - Mount all route modules
  - Expose /metrics endpoint for Prometheus scraping
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
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting URL Shortener application...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema verified / created.")

    logger.info("Application startup complete. Accepting traffic.")

    yield

    logger.info("Shutting down URL Shortener application...")

    await redis_cache.close()
    await engine.dispose()

    logger.info("Shutdown complete.")

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="URL Shortener",
        description=(
            "Minimal URL Shortener with analytics. "
            "Platform-oriented backend design."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
        redoc_url=None,
    )

    # -----------------------------------------------------------------------
    # Middleware
    # -----------------------------------------------------------------------

    @app.middleware("http")
    async def prometheus_middleware(request: Request, call_next):
        start = time.perf_counter()

        response: Response = await call_next(request)

        duration = time.perf_counter() - start
        endpoint = _normalise_path(request.url.path)

        http_request_duration_seconds.labels(
            endpoint=endpoint
        ).observe(duration)

        http_requests_total.labels(
            endpoint=endpoint,
            method=request.method,
            status_code=str(response.status_code),
        ).inc()

        return response

    # -----------------------------------------------------------------------
    # Routes (ORDER MATTERS)
    # -----------------------------------------------------------------------

    app.include_router(health.router)
    app.include_router(stats.router)
    app.include_router(shortener.router)  # MUST be last (catch-all /{code})

    # -----------------------------------------------------------------------
    # Metrics endpoint
    # -----------------------------------------------------------------------

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_path(path: str) -> str:
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
# ASGI entry
# ---------------------------------------------------------------------------

app = create_app()