"""Prometheus metrics for production monitoring.

Tracks request rates, execution durations, token usage,
and system health metrics.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Metrics collection (uses prometheus_client if available)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    from prometheus_client import CollectorRegistry

    _registry = CollectorRegistry()

    # Request metrics
    REQUEST_COUNT = Counter(
        "rewoo_requests_total",
        "Total number of API requests",
        ["method", "endpoint", "status_code"],
        registry=_registry,
    )

    REQUEST_DURATION = Histogram(
        "rewoo_request_duration_seconds",
        "Request duration in seconds",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=_registry,
    )

    # Execution metrics
    EXECUTION_COUNT = Counter(
        "rewoo_executions_total",
        "Total number of plan executions",
        ["status"],
        registry=_registry,
    )

    EXECUTION_DURATION = Histogram(
        "rewoo_execution_duration_seconds",
        "Plan execution duration in seconds",
        buckets=[1, 5, 10, 30, 60, 120, 300, 600],
        registry=_registry,
    )

    TOKEN_USAGE = Counter(
        "rewoo_tokens_total",
        "Total LLM tokens used",
        ["model", "type"],  # type: input, output
        registry=_registry,
    )

    ACTIVE_EXECUTIONS = Gauge(
        "rewoo_active_executions",
        "Number of currently running executions",
        registry=_registry,
    )

    # Database metrics
    DB_CONNECTION_POOL_SIZE = Gauge(
        "rewoo_db_pool_size",
        "Database connection pool size",
        registry=_registry,
    )

    DB_QUERY_DURATION = Histogram(
        "rewoo_db_query_duration_seconds",
        "Database query duration",
        ["operation"],
        buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
        registry=_registry,
    )

    # Redis metrics
    REDIS_OPERATIONS = Counter(
        "rewoo_redis_operations_total",
        "Total Redis operations",
        ["operation", "status"],
        registry=_registry,
    )

    HAS_PROMETHEUS = True

except ImportError:
    HAS_PROMETHEUS = False
    _registry = None
    # Stub objects for when prometheus_client is not installed
    class _Stub:
        def labels(self, *a, **kw): return self
        def inc(self, *a, **kw): pass
        def dec(self, *a, **kw): pass
        def observe(self, *a, **kw): pass
        def set(self, *a, **kw): pass

    REQUEST_COUNT = _Stub()
    REQUEST_DURATION = _Stub()
    EXECUTION_COUNT = _Stub()
    EXECUTION_DURATION = _Stub()
    TOKEN_USAGE = _Stub()
    ACTIVE_EXECUTIONS = _Stub()
    DB_CONNECTION_POOL_SIZE = _Stub()
    DB_QUERY_DURATION = _Stub()
    REDIS_OPERATIONS = _Stub()


def setup_metrics(app: Any) -> None:
    """Setup Prometheus metrics endpoint on the FastAPI app.

    Args:
        app: FastAPI application instance.
    """
    if not HAS_PROMETHEUS:
        logger.info("prometheus_client not installed — metrics endpoint disabled")
        return

    from fastapi import Response

    @app.get("/api/metrics")
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_latest(_registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus metrics endpoint enabled at /api/metrics")
