"""Password hashing and verification using bcrypt.

Uses the bcrypt library directly for secure password handling.
Falls back to SHA-256 + salt if bcrypt is unavailable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import bcrypt as _bcrypt

    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        The hashed password string.
    """
    if _BCRYPT_AVAILABLE:
        # bcrypt requires bytes and has a 72-byte limit
        password_bytes = password.encode("utf-8")[:72]
        salt = _bcrypt.gensalt(rounds=12)
        hashed = _bcrypt.hashpw(password_bytes, salt)
        return hashed.decode("utf-8")

    # Fallback: use SHA-256 with salt (NOT for production without bcrypt)
    import hashlib
    import os

    salt = os.urandom(16).hex()
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"sha256${salt}${hashed}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.

    Args:
        password: The plaintext password to verify.
        password_hash: The stored password hash.

    Returns:
        True if the password matches, False otherwise.
    """
    if _BCRYPT_AVAILABLE:
        try:
            password_bytes = password.encode("utf-8")[:72]
            hash_bytes = password_hash.encode("utf-8")
            return _bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception:
            return False

    # Fallback for sha256 format
    import hashlib

    if password_hash.startswith("sha256$"):
        parts = password_hash.split("$")
        if len(parts) != 3:
            return False
        _, salt, stored_hash = parts
        computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return computed == stored_hash

    return False
