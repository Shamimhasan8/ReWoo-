"""Agent state management.

Tracks the current state of an agent execution, including which stage
the agent is in, what plan is being executed, and the results collected
so far.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentStage(str, Enum):
    """Stages of the agent execution lifecycle."""

    IDLE = "idle"
    PLANNING = "planning"
    REVIEWING = "reviewing"
    EXECUTING = "executing"
    SOLVING = "solving"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentState(BaseModel):
    """Mutable state tracking the current agent execution.

    This is used for progress reporting and introspection, allowing
    external systems to monitor what the agent is doing at any point.
    """

    stage: AgentStage = AgentStage.IDLE
    task: str = ""
    plan_id: str = ""
    current_step_index: int = -1
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def start(self, task: str) -> None:
        """Mark the agent as starting a new task.

        Args:
            task: The task being started.
        """
        self.stage = AgentStage.PLANNING
        self.task = task
        self.started_at = datetime.now(timezone.utc)
        self.completed_at = None
        self.error = None
        self.completed_steps = 0
        self.failed_steps = 0
        self.current_step_index = -1
        logger.info(f"Agent state: started task '{task[:50]}'")

    def set_planning(self) -> None:
        """Mark the agent as in the planning stage."""
        self.stage = AgentStage.PLANNING
        logger.debug("Agent state: planning")

    def set_reviewing(self, plan_id: str, total_steps: int) -> None:
        """Mark the agent as in the review stage.

        Args:
            plan_id: The ID of the plan being reviewed.
            total_steps: Number of steps in the plan.
        """
        self.stage = AgentStage.REVIEWING
        self.plan_id = plan_id
        self.total_steps = total_steps
        logger.debug(f"Agent state: reviewing plan {plan_id}")

    def set_executing(self, step_index: int) -> None:
        """Mark the agent as executing a specific step.

        Args:
            step_index: Index of the step being executed.
        """
        self.stage = AgentStage.EXECUTING
        self.current_step_index = step_index
        logger.debug(f"Agent state: executing step {step_index}")

    def step_completed(self, failed: bool = False) -> None:
        """Mark a step as completed.

        Args:
            failed: Whether the step failed.
        """
        if failed:
            self.failed_steps += 1
        else:
            self.completed_steps += 1
        logger.debug(f"Agent state: step completed (failed={failed})")

    def set_solving(self) -> None:
        """Mark the agent as in the solving stage."""
        self.stage = AgentStage.SOLVING
        logger.debug("Agent state: solving")

    def set_completed(self) -> None:
        """Mark the agent as completed."""
        self.stage = AgentStage.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        logger.info("Agent state: completed")

    def set_failed(self, error: str) -> None:
        """Mark the agent as failed.

        Args:
            error: Error message describing the failure.
        """
        self.stage = AgentStage.FAILED
        self.error = error
        self.completed_at = datetime.now(timezone.utc)
        logger.error(f"Agent state: failed — {error}")

    @property
    def progress(self) -> float:
        """Execution progress as a percentage (0.0 to 1.0)."""
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps + self.failed_steps) / self.total_steps

    @property
    def duration_seconds(self) -> float:
        """Duration of the execution in seconds."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def summary(self) -> dict[str, Any]:
        """Get a summary of the current agent state.

        Returns:
            Dict with key state information.
        """
        return {
            "stage": self.stage.value,
            "task": self.task[:100],
            "plan_id": self.plan_id,
            "progress": f"{self.progress:.0%}",
            "steps": f"{self.completed_steps}/{self.total_steps}",
            "failed": self.failed_steps,
            "duration": f"{self.duration_seconds:.1f}s",
            "error": self.error,
        }
