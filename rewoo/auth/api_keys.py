"""API key verification for programmatic access.

API keys are stored as bcrypt hashes. Verification looks up the
key by prefix, then verifies the full key against the stored hash.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def verify_api_key(api_key: str, settings: Any = None) -> dict[str, str] | None:
    """Verify an API key and return the associated user info.

    API keys have the format: rw_<32 hex chars>

    Args:
        api_key: The API key to verify.
        settings: Application settings.

    Returns:
        Dict with user_id and tier if valid, None otherwise.
    """
    if not api_key or not api_key.startswith("rw_"):
        return None

    prefix = api_key[:8]

    try:
        from rewoo.db.models import APIKey
        from rewoo.db.session import get_db_session
        from rewoo.auth.passwords import verify_password

        async with get_db_session() as session:
            # Look up by prefix (indexed)
            from sqlalchemy import select
            result = await session.execute(
                select(APIKey).where(
                    APIKey.key_prefix == prefix,
                    APIKey.is_active == True,
                )
            )
            key_record = result.scalar_one_or_none()

            if not key_record:
                logger.debug(f"API key not found: prefix={prefix}")
                return None

            # Verify full key against stored hash
            if not verify_password(api_key, key_record.key_hash):
                logger.debug(f"API key hash mismatch: prefix={prefix}")
                return None

            # Update last_used
            from datetime import datetime, timezone
            key_record.last_used = datetime.now(timezone.utc)

            return {
                "user_id": str(key_record.user_id),
                "tier": key_record.tier,
            }

    except Exception as e:
        logger.error(f"API key verification error: {e}")
        return None
