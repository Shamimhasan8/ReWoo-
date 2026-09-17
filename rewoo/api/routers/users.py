"""User management endpoints — registration, login, API keys.

Handles user lifecycle for a multi-tenant production system.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from rewoo.auth.jwt import create_token
from rewoo.auth.passwords import hash_password, verify_password

router = APIRouter()


class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class APIKeyCreate(BaseModel):
    """API key creation request."""
    name: str = Field(min_length=1, max_length=100)
    tier: str = Field(default="free", pattern="^(free|pro|enterprise)$")


class UserResponse(BaseModel):
    """User response."""
    id: str
    email: str
    name: str
    tier: str
    created_at: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class APIKeyResponse(BaseModel):
    """API key response."""
    id: str
    name: str
    key: str
    tier: str
    created_at: str


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, request: Request) -> TokenResponse:
    """Register a new user account."""
    from rewoo.db.models import User
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        # Check if email already exists
        existing = await User.get_by_email(session, req.email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        # Create user
        user = await User.create(
            session,
            email=req.email,
            password_hash=hash_password(req.password),
            name=req.name,
            tier="free",
        )

        # Generate JWT
        settings = request.app.state.settings if hasattr(request.app.state, "settings") else None
        from rewoo.config import Settings
        settings = settings or Settings()
        token = create_token(
            user_id=str(user.id),
            tier=user.tier,
            secret=settings.jwt_secret,
            expires_hours=settings.jwt_expire_hours,
        )

        return TokenResponse(access_token=token, expires_in=settings.jwt_expire_hours * 3600)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate and get a JWT token."""
    from rewoo.db.models import User
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        user = await User.get_by_email(session, req.email)
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")

        from rewoo.config import Settings
        settings = Settings()
        token = create_token(
            user_id=str(user.id),
            tier=user.tier,
            secret=settings.jwt_secret,
            expires_hours=settings.jwt_expire_hours,
        )

        return TokenResponse(access_token=token, expires_in=settings.jwt_expire_hours * 3600)


@router.get("/me", response_model=UserResponse)
async def get_current_user(request: Request) -> UserResponse:
    """Get the current authenticated user's profile."""
    user_id = request.state.user_id
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from rewoo.db.models import User
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        user = await User.get_by_id(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            tier=user.tier,
            created_at=user.created_at.isoformat(),
        )


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(req: APIKeyCreate, request: Request) -> APIKeyResponse:
    """Create a new API key for programmatic access."""
    user_id = request.state.user_id
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from rewoo.db.models import APIKey
    from rewoo.db.session import get_db_session

    # Generate a secure API key
    key_value = f"rw_{uuid.uuid4().hex[:32]}"

    async with get_db_session() as session:
        api_key = await APIKey.create(
            session,
            user_id=user_id,
            name=req.name,
            key_hash=hash_password(key_value),  # Hash the key for storage
            key_prefix=key_value[:8],  # Store prefix for identification
            tier=req.tier,
        )

        return APIKeyResponse(
            id=str(api_key.id),
            name=api_key.name,
            key=key_value,  # Only shown once!
            tier=api_key.tier,
            created_at=api_key.created_at.isoformat(),
        )


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(request: Request) -> list[APIKeyResponse]:
    """List all API keys for the current user (key values hidden)."""
    user_id = request.state.user_id
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from rewoo.db.models import APIKey
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        keys = await APIKey.list_by_user(session, user_id)
        return [
            APIKeyResponse(
                id=str(k.id),
                name=k.name,
                key=f"{k.key_prefix}...****",  # Mask the key
                tier=k.tier,
                created_at=k.created_at.isoformat(),
            )
            for k in keys
        ]
