"""Core type definitions for the ReWoo framework."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk classification levels for plan steps.

    Ordered by severity: LOW < MEDIUM < HIGH < CRITICAL.
    The integer value is used for comparison operations.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    # Numeric severity for comparison
    _severity: int

    def __new__(cls, value: str, severity: int = 0) -> RiskLevel:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj._severity = severity
        return obj

    @property
    def severity(self) -> int:
        """Numeric severity level for comparison."""
        severity_map = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        return severity_map[self]

    def __lt__(self, other: object) -> bool:
        if isinstance(other, RiskLevel):
            return self.severity < other.severity
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, RiskLevel):
            return self.severity <= other.severity
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, RiskLevel):
            return self.severity > other.severity
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, RiskLevel):
            return self.severity >= other.severity
        return NotImplemented

    @property
    def requires_approval(self) -> bool:
        """Whether this risk level requires explicit approval."""
        return self in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    @property
    def emoji(self) -> str:
        """Visual indicator for this risk level."""
        mapping = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.CRITICAL: "🔴",
        }
        return mapping[self]


class StepStatus(str, Enum):
    """Execution status of a plan step."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanStep(BaseModel):
    """A single step in an execution plan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    index: int = Field(ge=0, description="Step number (0-indexed)")
    description: str = Field(description="Human-readable description of what this step does")
    tool: str = Field(description="Tool name to invoke")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to the tool")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Assessed risk level")
    risk_reason: Optional[str] = Field(default=None, description="Why this risk level was assigned")
    depends_on: list[int] = Field(default_factory=list, description="Indices of steps this step depends on")
    status: StepStatus = Field(default=StepStatus.PENDING)
    reversible: bool = Field(default=True, description="Whether this step's effects can be undone")

    @property
    def needs_approval(self) -> bool:
        """Whether this step requires explicit user approval."""
        return self.risk_level.requires_approval


class StepResult(BaseModel):
    """Result of executing a single plan step."""

    step_id: str
    step_index: int
    status: StepStatus
    output: Optional[str] = None
    error: Optional[str] = None
    tokens_used: int = 0
    duration_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionPlan(BaseModel):
    """A complete execution plan produced by the Planner."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    task: str = Field(description="The original task description")
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_tokens: int = 0

    @property
    def has_high_risk(self) -> bool:
        """Whether any step in the plan is HIGH or CRITICAL risk."""
        return any(s.risk_level.requires_approval for s in self.steps)

    @property
    def step_count(self) -> int:
        """Number of steps in the plan."""
        return len(self.steps)

    def get_step(self, index: int) -> PlanStep:
        """Get a step by its index."""
        for step in self.steps:
            if step.index == index:
                return step
        raise IndexError(f"No step with index {index}")

    def get_ready_steps(self) -> list[PlanStep]:
        """Get steps that are PENDING or APPROVED and whose dependencies are all COMPLETED."""
        completed_indices = {s.index for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.REJECTED, StepStatus.SKIPPED)}
        ready = []
        for step in self.steps:
            if step.status not in (StepStatus.PENDING, StepStatus.APPROVED):
                continue
            if all(dep in completed_indices for dep in step.depends_on):
                ready.append(step)
        return ready


class ExecutionResult(BaseModel):
    """Final result of executing an entire plan."""

    plan_id: str
    task: str
    answer: str = Field(description="The synthesized final answer from the Solver")
    step_results: list[StepResult] = Field(default_factory=list)
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    plan: Optional[ExecutionPlan] = None


class AuditEntry(BaseModel):
    """A single entry in the immutable audit log."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = Field(description="Type of event: plan_created, step_approved, step_rejected, step_executed, execution_completed")
    plan_id: Optional[str] = None
    step_index: Optional[int] = None
    data: dict[str, Any] = Field(default_factory=dict)
