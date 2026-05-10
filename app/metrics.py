"""
metrics.py — Prometheus metric declarations.

Single source of truth for all metric names and types.
Imported by routes and middleware; never instantiated elsewhere.
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Request-level metrics (RED method)
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests received.",
    ["endpoint", "method", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# ---------------------------------------------------------------------------
# Cache metrics
# ---------------------------------------------------------------------------

cache_hits_total = Counter(
    "cache_hits_total",
    "Total Redis cache lookups by result.",
    ["result"],  # label values: "hit" | "miss"
)

# ---------------------------------------------------------------------------
# Database metrics
# ---------------------------------------------------------------------------

db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections in the pool.",
)

# ---------------------------------------------------------------------------
# Business metrics
# ---------------------------------------------------------------------------

redirects_total = Counter(
    "redirects_total",
    "Total redirect events by short code.",
    ["code"],
)
