"""
routes/health.py — Liveness and readiness probe endpoints.

GET /health  — liveness probe.
  Always returns 200 as long as the Python process is alive.
  Does NOT check DB or Redis. Kubernetes uses this to detect a dead process
  and restart the container. If we checked dependencies here, a transient DB
  blip would cause unnecessary pod restarts.

GET /ready   — readiness probe.
  Returns 200 only when both PostgreSQL and Redis are reachable.
  Returns 503 with a structured JSON body indicating which dependency failed.
  Kubernetes uses this to gate traffic — an unready pod is removed from the
  Service endpoints without being restarted.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import cache, database
from app.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["ops"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe — is the process alive?",
)
async def health() -> HealthResponse:
    """
    Always returns 200 {"status": "alive"} if the event loop is running.
    No dependency checks — intentional by design.
    """
    return HealthResponse(status="alive")


@router.get(
    "/ready",
    summary="Readiness probe — are all dependencies reachable?",
)
async def ready() -> JSONResponse:
    """
    Checks PostgreSQL and Redis connectivity.
    Returns 200 if both are healthy, 503 if either is not.
    The JSON body always describes the state of each dependency so operators
    can pinpoint which system is down without reading logs.
    """
    pg_ok = await database.health_check()
    redis_ok = await cache.health_check()

    body = ReadyResponse(
        status="ready" if (pg_ok and redis_ok) else "degraded",
        postgres="ok" if pg_ok else "error",
        redis="ok" if redis_ok else "error",
    )

    status_code = 200 if (pg_ok and redis_ok) else 503
    return JSONResponse(content=body.model_dump(), status_code=status_code)
