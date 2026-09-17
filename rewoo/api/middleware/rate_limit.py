"""Rate limiting middleware using Redis sliding window.

Prevents abuse by limiting requests per user/IP. Configurable
per-endpoint and per-tier (free/pro/enterprise).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from rewoo.config import Settings

logger = logging.getLogger(__name__)

# Rate limit tiers: (requests_per_minute, burst)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "anonymous": (20, 30),
    "free": (60, 100),
    "pro": (300, 500),
    "enterprise": (3000, 5000),
}

# Exempt paths (health checks, metrics)
EXEMPT_PATHS = {"/api/health", "/api/ready", "/api/metrics", "/api/docs", "/api/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter backed by Redis.

    Falls back to in-memory tracking if Redis is unavailable.
    """

    def __init__(self, app: Any, settings: Settings | None = None, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self.settings = settings or Settings()
        self._local_counts: dict[str, list[float]] = {}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip rate limiting for exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Determine the client identifier
        client_id = self._get_client_id(request)
        tier = getattr(request.state, "user_tier", "anonymous")

        # Get rate limits for this tier
        rpm, burst = RATE_LIMITS.get(tier, RATE_LIMITS["anonymous"])

        # Check rate limit
        allowed = await self._check_rate_limit(client_id, rpm, burst)

        if not allowed:
            logger.warning(f"Rate limit exceeded for {client_id} (tier={tier})")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Maximum {rpm} requests per minute for {tier} tier.",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(rpm)
        response.headers["X-RateLimit-Tier"] = tier

        return response

    def _get_client_id(self, request: Request) -> str:
        """Get a unique identifier for the client."""
        # Prefer authenticated user ID
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"

        # Fall back to API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key[:8]}"

        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        return f"ip:{request.client.host if request.client else 'unknown'}"

    async def _check_rate_limit(self, client_id: str, rpm: int, burst: int) -> bool:
        """Check rate limit using Redis sliding window.

        Falls back to in-memory if Redis is unavailable.
        """
        try:
            from rewoo.cache.redis import get_redis

            redis = await get_redis()
            if redis:
                return await self._redis_check(redis, client_id, rpm, burst)
        except Exception:
            logger.debug("Redis unavailable, using in-memory rate limiting")

        return self._local_check(client_id, rpm, burst)

    async def _redis_check(self, redis: Any, client_id: str, rpm: int, burst: int) -> bool:
        """Redis-based sliding window rate check."""
        import json

        key = f"ratelimit:{client_id}"
        now = time.time()
        window = 60.0  # 1 minute window

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, int(window) + 1)
        results = await pipe.execute()

        current_count = results[1]
        return current_count < burst

    def _local_check(self, client_id: str, rpm: int, burst: int) -> bool:
        """In-memory rate limit check (fallback)."""
        now = time.time()
        window = 60.0

        if client_id not in self._local_counts:
            self._local_counts[client_id] = []

        # Remove expired entries
        self._local_counts[client_id] = [
            t for t in self._local_counts[client_id] if now - t < window
        ]

        if len(self._local_counts[client_id]) >= burst:
            return False

        self._local_counts[client_id].append(now)
        return True
