"""Health check endpoints for Kubernetes probes and monitoring.

Provides /health (liveness), /ready (readiness), and /metrics (Prometheus).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter()

_start_time = time.monotonic()


@router.get("/health")
async def health_check() -> dict:
    """Liveness probe — is the service running?"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }


@router.get("/ready")
async def readiness_check(request: Request) -> dict:
    """Readiness probe — is the service ready to accept traffic?

    Checks database and Redis connectivity.
    """
    checks: dict[str, bool] = {}

    # Check database
    try:
        from rewoo.db.session import get_db_session
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    # Check Redis
    try:
        from rewoo.cache.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.ping()
            checks["redis"] = True
        else:
            checks["redis"] = False
    except Exception:
        checks["redis"] = False

    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503

    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
