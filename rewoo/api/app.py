"""FastAPI application factory with production middleware stack.

Creates the main FastAPI application with:
- CORS middleware
- Rate limiting
- Request tracing
- Authentication
- Error handling
- Prometheus metrics
- Health checks
- OpenAPI documentation
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from rewoo.api.middleware.auth import AuthMiddleware
from rewoo.api.middleware.rate_limit import RateLimitMiddleware
from rewoo.api.middleware.request_id import RequestIDMiddleware
from rewoo.api.routers import executions, health, plans, skills, users
from rewoo.config import Settings
from rewoo.monitoring.logging import setup_logging
from rewoo.monitoring.metrics import setup_metrics

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler — startup and shutdown events."""
    settings = Settings()
    setup_logging(log_level=settings.log_level, json_logs=settings.json_logs)
    logger.info("ReWoo API starting up")

    # Initialize database
    from rewoo.db.session import init_db
    await init_db(settings)
    logger.info("Database initialized")

    # Initialize Redis
    from rewoo.cache.redis import init_redis
    await init_redis(settings)
    logger.info("Redis initialized")

    # Setup metrics
    setup_metrics(app)
    logger.info("Metrics initialized")

    # Setup OpenTelemetry tracing
    if settings.otel_enabled:
        from rewoo.monitoring.tracing import setup_tracing
        setup_tracing("rewoo-api", settings.otel_endpoint, settings.otel_headers)
        logger.info("OpenTelemetry tracing initialized")

    yield

    # Shutdown
    if settings.otel_enabled:
        from rewoo.monitoring.tracing import shutdown_tracing
        shutdown_tracing()
        logger.info("OpenTelemetry tracing shut down")

    from rewoo.cache.redis import close_redis
    await close_redis()
    logger.info("Redis connection closed")

    from rewoo.db.session import close_db
    await close_db()
    logger.info("Database connection closed")

    logger.info("ReWoo API shut down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Fully configured FastAPI application instance.
    """
    settings = Settings()

    app = FastAPI(
        title="ReWoo API",
        description="Production API for the ReWoo AI agent framework — plan-first, safe execution.",
        version="0.1.0",
        docs_url="/api/docs" if settings.enable_docs else None,
        redoc_url="/api/redoc" if settings.enable_docs else None,
        openapi_url="/api/openapi.json" if settings.enable_docs else None,
        lifespan=lifespan,
    )

    # Middleware stack (order matters — outermost first)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(AuthMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Routers
    app.include_router(health.router, prefix="/api", tags=["Health"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
    app.include_router(plans.router, prefix="/api/v1/plans", tags=["Plans"])
    app.include_router(executions.router, prefix="/api/v1/executions", tags=["Executions"])
    app.include_router(skills.router, prefix="/api/v1/skills", tags=["Skills"])

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred. Please try again later.",
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    return app


app = create_app()
