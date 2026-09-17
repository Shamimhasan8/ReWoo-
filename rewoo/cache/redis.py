"""Redis connection management for caching, rate limiting, and pub/sub.

Provides a shared Redis connection pool that gracefully degrades
when Redis is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from rewoo.config import Settings

logger = logging.getLogger(__name__)

_redis: Optional[Any] = None


async def init_redis(settings: Settings | None = None) -> None:
    """Initialize the Redis connection pool.

    Args:
        settings: Application settings. Uses defaults if not provided.
    """
    global _redis

    settings = settings or Settings()

    if not settings.redis_url:
        logger.warning("REDIS_URL not set — caching and rate limiting will use fallback")
        _redis = None
        return

    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.redis_pool_size,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )

        # Test connection
        await _redis.ping()
        logger.info(f"Redis connected: {settings.redis_url.split('@')[-1] if '@' in settings.redis_url else 'local'}")

    except ImportError:
        logger.warning("redis package not installed — caching disabled")
        _redis = None
    except Exception as e:
        logger.warning(f"Redis connection failed: {e} — caching disabled")
        _redis = None


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis

    if _redis:
        await _redis.close()
        _redis = None
        logger.info("Redis connection closed")


async def get_redis() -> Optional[Any]:
    """Get the Redis client instance.

    Returns:
        Redis client or None if unavailable.
    """
    return _redis


class CacheManager:
    """High-level caching operations backed by Redis.

    Provides get/set/delete with TTL support, plus pub/sub
    for real-time execution updates.
    """

    def __init__(self, prefix: str = "rewoo") -> None:
        self.prefix = prefix

    def _key(self, key: str) -> str:
        """Add namespace prefix to key."""
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[str]:
        """Get a cached value.

        Args:
            key: Cache key (without prefix).

        Returns:
            Cached value or None.
        """
        redis = await get_redis()
        if not redis:
            return None

        try:
            return await redis.get(self._key(key))
        except Exception as e:
            logger.debug(f"Cache get error: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int = 300) -> bool:
        """Set a cached value with TTL.

        Args:
            key: Cache key (without prefix).
            value: Value to cache.
            ttl: Time-to-live in seconds (default: 5 minutes).

        Returns:
            True if successful.
        """
        redis = await get_redis()
        if not redis:
            return False

        try:
            await redis.setex(self._key(key), ttl, value)
            return True
        except Exception as e:
            logger.debug(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a cached value.

        Args:
            key: Cache key (without prefix).

        Returns:
            True if the key was deleted.
        """
        redis = await get_redis()
        if not redis:
            return False

        try:
            result = await redis.delete(self._key(key))
            return result > 0
        except Exception as e:
            logger.debug(f"Cache delete error: {e}")
            return False

    async def publish(self, channel: str, message: str) -> bool:
        """Publish a message to a Redis channel.

        Used for real-time execution progress updates via WebSocket.

        Args:
            channel: Channel name.
            message: Message to publish.

        Returns:
            True if published successfully.
        """
        redis = await get_redis()
        if not redis:
            return False

        try:
            await redis.publish(channel, message)
            return True
        except Exception as e:
            logger.debug(f"Redis publish error: {e}")
            return False
