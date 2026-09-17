"""Health check utilities for Kubernetes probes.

Provides functions for checking subsystem health that are called
by the readiness endpoint.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def check_database() -> bool:
    """Check if the database is accessible.

    Returns:
        True if database is healthy.
    """
    try:
        from rewoo.db.session import get_db_session
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def check_redis() -> bool:
    """Check if Redis is accessible.

    Returns:
        True if Redis is healthy (or not required).
    """
    try:
        from rewoo.cache.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.ping()
            return True
        # Redis not configured is OK
        return True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return False


async def check_llm_provider() -> bool:
    """Check if the LLM provider API is accessible.

    Returns:
        True if the provider is reachable.
    """
    try:
        from rewoo.config import Settings
        settings = Settings()

        provider = settings.get_provider()
        if provider == "anthropic" and not settings.anthropic_api_key:
            return False
        if provider == "openai" and not settings.openai_api_key:
            return False
        if provider == "openrouter" and not settings.openrouter_api_key:
            return False

        return True
    except Exception:
        return False


async def full_health_check() -> dict[str, Any]:
    """Run all health checks and return detailed results.

    Returns:
        Dict with status of each subsystem.
    """
    db_ok = await check_database()
    redis_ok = await check_redis()
    llm_ok = await check_llm_provider()

    return {
        "database": {"status": "healthy" if db_ok else "unhealthy"},
        "redis": {"status": "healthy" if redis_ok else "degraded"},
        "llm_provider": {"status": "healthy" if llm_ok else "unhealthy"},
        "overall": "healthy" if (db_ok and redis_ok and llm_ok) else "degraded",
    }
