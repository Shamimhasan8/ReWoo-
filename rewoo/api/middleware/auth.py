"""Authentication middleware — JWT and API key validation.

Supports multiple auth methods:
1. JWT Bearer tokens (for user sessions)
2. API keys (for programmatic access)
3. Service tokens (for inter-service communication)

Invalid tokens result in 401 responses.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from rewoo.auth.jwt import verify_token
from rewoo.auth.api_keys import verify_api_key
from rewoo.config import Settings

logger = logging.getLogger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/api/health",
    "/api/ready",
    "/api/metrics",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/v1/users/register",
    "/api/v1/users/login",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware that validates JWT tokens and API keys.

    Sets request.state.user_id, request.state.user_tier, and
    request.state.auth_method for downstream handlers.
    """

    def __init__(self, app: Any, settings: Settings | None = None, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self.settings = settings or Settings()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            request.state.user_id = None
            request.state.user_tier = "anonymous"
            request.state.auth_method = None
            return await call_next(request)

        # Skip auth if disabled
        if not self.settings.auth_enabled:
            request.state.user_id = "dev-user"
            request.state.user_tier = "enterprise"
            request.state.auth_method = "disabled"
            return await call_next(request)

        # Try authentication methods in order of priority
        auth_result = await self._authenticate(request)

        if auth_result is None:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Valid authentication required. Use Bearer token or X-API-Key header.",
                },
            )

        user_id, tier, method = auth_result
        request.state.user_id = user_id
        request.state.user_tier = tier
        request.state.auth_method = method

        response = await call_next(request)
        return response

    async def _authenticate(self, request: Request) -> tuple[str, str, str] | None:
        """Try all authentication methods.

        Returns:
            Tuple of (user_id, tier, method) if authenticated, None otherwise.
        """
        # 1. Try service token (for inter-service communication)
        service_token = request.headers.get("X-Service-Token")
        if service_token and service_token == self.settings.service_token:
            return ("service-account", "enterprise", "service_token")

        # 2. Try JWT Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = verify_token(token, self.settings)
                user_id = payload.get("sub")
                tier = payload.get("tier", "free")
                if user_id:
                    return (user_id, tier, "jwt")
            except Exception as e:
                logger.debug(f"JWT verification failed: {e}")

        # 3. Try API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            try:
                key_info = await verify_api_key(api_key, self.settings)
                if key_info:
                    return (key_info["user_id"], key_info["tier"], "api_key")
            except Exception as e:
                logger.debug(f"API key verification failed: {e}")

        return None
