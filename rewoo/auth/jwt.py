"""JWT token creation and verification.

Uses PyJWT for token management with RS256 or HS256 algorithms.
Production deployments should use RS256 with proper key management.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import jwt

logger = logging.getLogger(__name__)


def create_token(
    user_id: str,
    tier: str = "free",
    secret: str = "dev-secret-change-me",
    expires_hours: int = 24,
    algorithm: str = "HS256",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a JWT token.

    Args:
        user_id: The user's unique identifier.
        tier: The user's subscription tier.
        secret: The signing secret key.
        expires_hours: Token expiration time in hours.
        algorithm: JWT algorithm (HS256 or RS256).
        extra_claims: Additional claims to include.

    Returns:
        Encoded JWT token string.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "tier": tier,
        "iat": now,
        "exp": now + (expires_hours * 3600),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_token(
    token: str,
    settings: Any = None,
    algorithm: str = "HS256",
) -> dict[str, Any]:
    """Verify and decode a JWT token.

    Args:
        token: The JWT token to verify.
        settings: Application settings (for secret key).
        algorithm: JWT algorithm.

    Returns:
        Decoded token payload.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid.
    """
    secret = getattr(settings, "jwt_secret", "dev-secret-change-me") if settings else "dev-secret-change-me"

    payload = jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
        options={"require": ["sub", "exp", "iat"]},
    )

    return payload


def create_refresh_token(
    user_id: str,
    secret: str = "dev-secret-change-me",
    expires_days: int = 30,
) -> str:
    """Create a refresh token for token rotation.

    Args:
        user_id: The user's unique identifier.
        secret: The signing secret key.
        expires_days: Refresh token expiration in days.

    Returns:
        Encoded refresh token string.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + (expires_days * 86400),
        "type": "refresh",
    }

    return jwt.encode(payload, secret, algorithm="HS256")
