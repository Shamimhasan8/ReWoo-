"""Database session management with async SQLAlchemy.

Provides session factory, connection pooling, and lifecycle management
for production PostgreSQL deployments.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, QueuePool

from rewoo.config import Settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def _get_engine_config(settings: Settings) -> dict:
    """Get SQLAlchemy engine configuration for production."""
    config = {
        "echo": settings.db_echo,
        "pool_pre_ping": True,  # Verify connections before use
        "pool_recycle": 3600,  # Recycle connections after 1 hour
    }

    if settings.db_pool_size > 0:
        config.update({
            "poolclass": QueuePool,
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": 30,
        })
    else:
        config["poolclass"] = NullPool

    return config


async def init_db(settings: Settings | None = None) -> None:
    """Initialize the database engine and session factory.

    Args:
        settings: Application settings. Uses defaults if not provided.
    """
    global _engine, _session_factory

    settings = settings or Settings()

    _engine = create_async_engine(
        settings.database_url,
        **_get_engine_config(settings),
    )

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    logger.info(f"Database engine created: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'local'}")


async def close_db() -> None:
    """Close the database engine and all connections."""
    global _engine, _session_factory

    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine disposed")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(...)

    Yields:
        AsyncSession instance.
    """
    if not _session_factory:
        await init_db()

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.

    Yields:
        AsyncSession instance with auto-commit/rollback.
    """
    if not _session_factory:
        await init_db()

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
