"""
test_shortener.py — Unit tests for the URL Shortener application layer.

Covers:
  1. POST /shorten — happy path
  2. POST /shorten — invalid URL rejected (422)
  3. GET /{code}  — cache miss path (DB lookup + cache write)
  4. GET /{code}  — cache hit path (no DB lookup)
  5. GET /{code}  — unknown code returns 404
  6. GET /stats/{code} — returns correct click count
  7. GET /health  — always returns 200
  8. GET /ready   — returns 200 when both dependencies healthy
  9. GET /ready   — returns 503 when a dependency is down
 10. GET /metrics — returns Prometheus exposition format
"""

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# POST /shorten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shorten_valid_url(client):
    """Happy path: valid URL → 201 with short_code and short_url."""
    response = await client.post("/shorten", json={"url": "https://example.com/long/path"})

    assert response.status_code == 201
    body = response.json()
    assert "short_code" in body
    assert len(body["short_code"]) == 6
    assert body["short_url"].endswith(f"/{body['short_code']}")
    assert body["long_url"] == "https://example.com/long/path"


@pytest.mark.asyncio
async def test_shorten_invalid_url_rejected(client):
    """Non-URL string must be rejected with 422 before touching the DB."""
    response = await client.post("/shorten", json={"url": "not-a-valid-url"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_shorten_missing_body_rejected(client):
    """Empty body must be rejected with 422."""
    response = await client.post("/shorten", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /{code} — redirect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redirect_cache_miss_hits_db(client):
    """
    Cache miss → DB lookup → 301 redirect.
    Verifies that cache.set() is called after the DB lookup so the next
    request will be served from cache.
    """
    # First, create a short URL
    shorten_resp = await client.post(
        "/shorten", json={"url": "https://example.com/cache-miss-test"}
    )
    assert shorten_resp.status_code == 201
    code = shorten_resp.json()["short_code"]

    # Ensure cache returns None (miss) — already the default in the fixture
    client.mock_cache_get.return_value = None

    response = await client.get(f"/{code}", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "https://example.com/cache-miss-test"
    # Cache should have been populated after the miss
    client.mock_cache_set.assert_called_once_with(code, "https://example.com/cache-miss-test")


@pytest.mark.asyncio
async def test_redirect_cache_hit_skips_db(client):
    """
    Cache hit → 301 redirect without touching the DB.
    The mock returns a URL directly so no DB row is needed.
    """
    client.mock_cache_get.return_value = "https://example.com/cached-target"

    response = await client.get("/anyhit", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "https://example.com/cached-target"
    # Cache should NOT be written again on a hit
    client.mock_cache_set.assert_not_called()


@pytest.mark.asyncio
async def test_redirect_unknown_code_returns_404(client):
    """Unknown short code → 404 with a meaningful error message."""
    client.mock_cache_get.return_value = None  # cache miss

    response = await client.get("/xxxxxx", follow_redirects=False)

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /stats/{code}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_returns_click_count(client):
    """
    Stats endpoint returns 0 clicks for a freshly created URL,
    and the correct metadata.
    """
    shorten_resp = await client.post(
        "/shorten", json={"url": "https://example.com/stats-test"}
    )
    assert shorten_resp.status_code == 201
    code = shorten_resp.json()["short_code"]

    stats_resp = await client.get(f"/stats/{code}")
    assert stats_resp.status_code == 200

    body = stats_resp.json()
    assert body["short_code"] == code
    assert body["long_url"] == "https://example.com/stats-test"
    assert body["click_count"] == 0


@pytest.mark.asyncio
async def test_stats_unknown_code_returns_404(client):
    """Stats for a non-existent code → 404."""
    response = await client.get("/stats/doesnotexist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_always_returns_200(client):
    """
    Liveness probe must return 200 regardless of DB/Redis state.
    We don't patch dependencies here because /health must NOT call them.
    """
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


# ---------------------------------------------------------------------------
# GET /ready
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ready_returns_200_when_all_healthy(client):
    """Readiness probe returns 200 when both DB and Redis are reachable."""
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["postgres"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_db_down(client):
    """Readiness probe returns 503 when PostgreSQL is unreachable."""
    with patch("app.database.health_check", new_callable=AsyncMock, return_value=False):
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["postgres"] == "error"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_redis_down(client):
    """Readiness probe returns 503 when Redis is unreachable."""
    with patch("app.cache.health_check", new_callable=AsyncMock, return_value=False):
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["postgres"] == "ok"
    assert body["redis"] == "error"


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(client):
    """
    /metrics must return text in Prometheus exposition format.
    Verify that our custom metric names are present in the output.
    """
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    body = response.text
    # All five metric families defined in metrics.py must be present
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "cache_hits_total" in body
    assert "db_connections_active" in body
    assert "redirects_total" in body
