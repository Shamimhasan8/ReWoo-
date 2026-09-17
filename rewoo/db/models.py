"""SQLAlchemy ORM models for ReWoo.

All models use UUID primary keys for distributed systems compatibility
and include proper indexing for production query patterns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import select, update, delete, func


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    tier = Column(String(20), nullable=False, default="free")  # free, pro, enterprise
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    api_keys = relationship("APIKey", back_populates="user", lazy="selectin")
    plans = relationship("ExecutionPlan", back_populates="user", lazy="selectin")

    @classmethod
    async def get_by_email(cls, session: AsyncSession, email: str) -> Optional["User"]:
        result = await session.execute(select(cls).where(cls.email == email))
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_id(cls, session: AsyncSession, user_id: str) -> Optional["User"]:
        result = await session.execute(select(cls).where(cls.id == uuid.UUID(user_id)))
        return result.scalar_one_or_none()

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> "User":
        user = cls(**kwargs)
        session.add(user)
        await session.flush()
        return user


class APIKey(Base):
    """API key model for programmatic access."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(16), nullable=False, index=True)
    tier = Column(String(20), nullable=False, default="free")
    is_active = Column(Boolean, default=True, nullable=False)
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_prefix_active", "key_prefix", "is_active"),
    )

    @classmethod
    async def list_by_user(cls, session: AsyncSession, user_id: str) -> list["APIKey"]:
        result = await session.execute(
            select(cls)
            .where(cls.user_id == uuid.UUID(user_id), cls.is_active == True)
            .order_by(cls.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> "APIKey":
        if "user_id" in kwargs and isinstance(kwargs["user_id"], str):
            kwargs["user_id"] = uuid.UUID(kwargs["user_id"])
        api_key = cls(**kwargs)
        session.add(api_key)
        await session.flush()
        return api_key


class ExecutionPlan(Base):
    """Execution plan model — stores generated plans before execution."""

    __tablename__ = "execution_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task = Column(Text, nullable=False)
    steps_data = Column(JSON, nullable=False, default=list)  # Full step data as JSON
    has_high_risk = Column(Boolean, default=False, nullable=False)
    status = Column(String(30), nullable=False, default="pending_approval", index=True)  # pending_approval, approved, executing, completed, failed
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="plans")
    executions = relationship("Execution", back_populates="plan", lazy="selectin")

    __table_args__ = (
        Index("ix_plans_user_status", "user_id", "status"),
    )

    @classmethod
    async def get_by_id(cls, session: AsyncSession, plan_id: str, user_id: str | None = None) -> Optional["ExecutionPlan"]:
        query = select(cls).where(cls.id == uuid.UUID(plan_id))
        if user_id:
            query = query.where(cls.user_id == uuid.UUID(user_id))
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def list_by_user(cls, session: AsyncSession, user_id: str, limit: int = 20, offset: int = 0) -> list["ExecutionPlan"]:
        result = await session.execute(
            select(cls)
            .where(cls.user_id == uuid.UUID(user_id))
            .order_by(cls.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @classmethod
    async def create_from_plan(cls, session: AsyncSession, plan: Any, user_id: str | None = None) -> "ExecutionPlan":
        """Create from a core ExecutionPlan object."""
        steps_json = [
            {
                "index": s.index,
                "description": s.description,
                "tool": s.tool,
                "tool_args": s.tool_args,
                "risk_level": s.risk_level.value,
                "risk_reason": s.risk_reason,
                "depends_on": s.depends_on,
                "status": s.status.value,
                "reversible": s.reversible,
            }
            for s in plan.steps
        ]

        db_plan = cls(
            user_id=uuid.UUID(user_id) if user_id else uuid.uuid4(),
            task=plan.task,
            steps_data=steps_json,
            has_high_risk=plan.has_high_risk,
            total_tokens=plan.total_tokens,
        )
        session.add(db_plan)
        await session.flush()
        return db_plan

    async def apply_approvals(self, session: AsyncSession, approvals: dict[int, str]) -> None:
        """Apply approval decisions to plan steps."""
        steps = self.steps_data or []
        for step in steps:
            idx = step.get("index", 0)
            if idx in approvals:
                step["status"] = approvals[idx]

        self.status = "approved"
        await session.flush()


class Execution(Base):
    """Execution model — tracks running and completed plan executions."""

    __tablename__ = "executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("execution_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="queued", index=True)  # queued, running, completed, failed, cancelled
    answer = Column(Text, nullable=True)
    step_results_data = Column(JSON, nullable=True, default=list)
    total_tokens = Column(Integer, default=0)
    total_duration_seconds = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    plan = relationship("ExecutionPlan", back_populates="executions")

    __table_args__ = (
        Index("ix_executions_user_status", "user_id", "status"),
        Index("ix_executions_plan", "plan_id"),
    )

    @classmethod
    async def get_by_id(cls, session: AsyncSession, execution_id: str, user_id: str | None = None) -> Optional["Execution"]:
        query = select(cls).where(cls.id == uuid.UUID(execution_id))
        if user_id:
            query = query.where(cls.user_id == uuid.UUID(user_id))
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> "Execution":
        for key in ("plan_id", "user_id"):
            if key in kwargs and isinstance(kwargs[key], str):
                kwargs[key] = uuid.UUID(kwargs[key])
        execution = cls(**kwargs)
        session.add(execution)
        await session.flush()
        return execution

    @classmethod
    async def list_by_user(cls, session: AsyncSession, user_id: str, limit: int = 20, offset: int = 0) -> tuple[list["Execution"], int]:
        # Get total count
        count_result = await session.execute(
            select(func.count()).select_from(cls).where(cls.user_id == uuid.UUID(user_id))
        )
        total = count_result.scalar() or 0

        result = await session.execute(
            select(cls)
            .where(cls.user_id == uuid.UUID(user_id))
            .order_by(cls.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def update_status(
        self,
        session: AsyncSession,
        status: str,
        answer: str | None = None,
        step_results: list | None = None,
        total_tokens: int | None = None,
        total_duration: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update execution status and results."""
        self.status = status
        if answer is not None:
            self.answer = answer
        if step_results is not None:
            self.step_results_data = step_results
        if total_tokens is not None:
            self.total_tokens = total_tokens
        if total_duration is not None:
            self.total_duration_seconds = total_duration
        if error_message is not None:
            self.error_message = error_message
        if status in ("completed", "failed", "cancelled"):
            self.completed_at = _utcnow()
        await session.flush()


class Skill(Base):
    """Learned skill model."""

    __tablename__ = "skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    task_pattern = Column(String(500), nullable=False)
    plan_template = Column(JSON, nullable=False, default=list)
    use_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_skills_user", "user_id"),
    )

    @classmethod
    async def list_by_user(cls, session: AsyncSession, user_id: str, limit: int = 20, offset: int = 0) -> list["Skill"]:
        result = await session.execute(
            select(cls)
            .where(cls.user_id == uuid.UUID(user_id))
            .order_by(cls.use_count.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @classmethod
    async def delete_by_id(cls, session: AsyncSession, skill_id: str, user_id: str) -> bool:
        result = await session.execute(
            delete(cls).where(cls.id == uuid.UUID(skill_id), cls.user_id == uuid.UUID(user_id))
        )
        return result.rowcount > 0


class AuditLog(Base):
    """Immutable audit log — every execution event is recorded here.

    This is the database-backed version of the audit log for
    production deployments. It replaces the JSONL file approach.
    """

    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    plan_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    execution_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    step_index = Column(Integer, nullable=True)
    data = Column(JSON, nullable=True, default=dict)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_audit_event_time", "event_type", "timestamp"),
        Index("ix_audit_user_time", "user_id", "timestamp"),
    )

    @classmethod
    async def log(cls, session: AsyncSession, event_type: str, **kwargs: Any) -> "AuditLog":
        """Create an audit log entry."""
        for key in ("user_id", "plan_id", "execution_id"):
            if key in kwargs and isinstance(kwargs[key], str):
                kwargs[key] = uuid.UUID(kwargs[key])
        entry = cls(event_type=event_type, **kwargs)
        session.add(entry)
        await session.flush()
        return entry
