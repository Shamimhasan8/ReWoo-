"""Immutable audit logger for ReWoo executions.

Every plan creation, approval decision, step execution, and LLM call is
written to an append-only JSONL file. This enables full reconstruction
of what happened and why.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rewoo.core.types import AuditEntry, ExecutionPlan, ExecutionResult, PlanStep, StepResult

logger = logging.getLogger(__name__)


class AuditLogger:
    """Append-only audit logger that records all ReWoo execution events.

    The audit log is stored as JSONL (one JSON object per line) for easy
    parsing, grepping, and streaming. Each entry includes a timestamp,
    event type, and structured data about what happened.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the audit logger.

        Args:
            path: Path to the JSONL audit log file. Defaults to
                  ~/.rewoo/audit.jsonl.
        """
        self.path = path or Path.home() / ".rewoo" / "audit.jsonl"
        self._ensure_path()

    def _ensure_path(self) -> None:
        """Create the audit log directory if it doesn't exist."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write_entry(self, entry: AuditEntry) -> None:
        """Write a single entry to the audit log.

        Args:
            entry: The audit entry to write.
        """
        try:
            line = entry.model_dump_json() + "\n"
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
            logger.debug(f"Audit entry written: {entry.event_type}")
        except Exception as e:
            logger.error(f"Failed to write audit entry: {e}")

    def log_plan_created(self, plan: ExecutionPlan) -> None:
        """Log that a new execution plan was created.

        Args:
            plan: The execution plan that was created.
        """
        entry = AuditEntry(
            event_type="plan_created",
            plan_id=plan.id,
            data={
                "task": plan.task,
                "step_count": plan.step_count,
                "steps": [
                    {
                        "index": s.index,
                        "tool": s.tool,
                        "description": s.description,
                        "risk_level": s.risk_level.value,
                    }
                    for s in plan.steps
                ],
                "has_high_risk": plan.has_high_risk,
            },
        )
        self._write_entry(entry)

    def log_step_approved(self, plan_id: str, step: PlanStep) -> None:
        """Log that a step was approved for execution.

        Args:
            plan_id: ID of the parent plan.
            step: The step that was approved.
        """
        entry = AuditEntry(
            event_type="step_approved",
            plan_id=plan_id,
            step_index=step.index,
            data={
                "tool": step.tool,
                "description": step.description,
                "risk_level": step.risk_level.value,
            },
        )
        self._write_entry(entry)

    def log_step_rejected(self, plan_id: str, step: PlanStep, reason: str = "") -> None:
        """Log that a step was rejected.

        Args:
            plan_id: ID of the parent plan.
            step: The step that was rejected.
            reason: Why the step was rejected.
        """
        entry = AuditEntry(
            event_type="step_rejected",
            plan_id=plan_id,
            step_index=step.index,
            data={
                "tool": step.tool,
                "description": step.description,
                "risk_level": step.risk_level.value,
                "reason": reason,
            },
        )
        self._write_entry(entry)

    def log_step_executed(self, plan_id: str, result: StepResult) -> None:
        """Log that a step was executed.

        Args:
            plan_id: ID of the parent plan.
            result: The result of the step execution.
        """
        entry = AuditEntry(
            event_type="step_executed",
            plan_id=plan_id,
            step_index=result.step_index,
            data={
                "status": result.status.value,
                "output_preview": (result.output[:500] if result.output else None),
                "error": result.error,
                "tokens_used": result.tokens_used,
                "duration_seconds": result.duration_seconds,
            },
        )
        self._write_entry(entry)

    def log_execution_completed(self, result: ExecutionResult) -> None:
        """Log that an entire execution was completed.

        Args:
            result: The final execution result.
        """
        entry = AuditEntry(
            event_type="execution_completed",
            plan_id=result.plan_id,
            data={
                "task": result.task,
                "answer_preview": result.answer[:500] if result.answer else None,
                "total_tokens": result.total_tokens,
                "total_duration_seconds": result.total_duration_seconds,
                "step_count": len(result.step_results),
                "steps_completed": sum(
                    1 for r in result.step_results if r.status.value == "completed"
                ),
                "steps_failed": sum(
                    1 for r in result.step_results if r.status.value == "failed"
                ),
            },
        )
        self._write_entry(entry)

    def log_custom(self, event_type: str, data: dict[str, Any], plan_id: str | None = None) -> None:
        """Log a custom event.

        Args:
            event_type: Custom event type identifier.
            data: Arbitrary structured data for the event.
            plan_id: Optional plan ID to associate.
        """
        entry = AuditEntry(
            event_type=event_type,
            plan_id=plan_id,
            data=data,
        )
        self._write_entry(entry)

    def read_entries(self, limit: int = 50, plan_id: str | None = None) -> list[AuditEntry]:
        """Read recent audit log entries.

        Args:
            limit: Maximum number of entries to return.
            plan_id: Optional filter by plan ID.

        Returns:
            List of audit entries, most recent last.
        """
        entries: list[AuditEntry] = []
        if not self.path.exists():
            return entries

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = AuditEntry(**data)
                        if plan_id is None or entry.plan_id == plan_id:
                            entries.append(entry)
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Failed to read audit log: {e}")

        return entries[-limit:]
