"""Celery task executor for distributed plan execution.

Handles the full Planner→Reviewer→Worker→Solver cycle as a
background task, with progress updates via Redis pub/sub.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from celery import Celery

from rewoo.config import Settings

logger = logging.getLogger(__name__)


def _get_celery_app() -> Celery:
    """Create or get the Celery application."""
    settings = Settings()

    app = Celery(
        "rewoo",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_concurrency=settings.celery_concurrency,
        task_soft_time_limit=settings.celery_task_timeout,
        task_time_limit=settings.celery_task_timeout + 60,
        result_expires=3600,
        broker_connection_retry_on_startup=True,
    )

    return app


celery_app = _get_celery_app()


@celery_app.task(bind=True, name="rewoo.execute_plan", max_retries=2, default_retry_delay=10)
def execute_plan_task(
    self: Any,
    execution_id: str,
    plan_id: str,
    user_id: str,
    approval_mode: str | None = None,
) -> dict:
    """Execute an approved plan as a background task.

    This is the main entry point for distributed execution.
    Runs the full Planner→Reviewer→Worker→Solver cycle.

    Args:
        self: Celery task instance.
        execution_id: ID of the execution record.
        plan_id: ID of the plan to execute.
        user_id: ID of the user who owns the plan.
        approval_mode: Override approval mode.

    Returns:
        Dict with execution results.
    """
    try:
        result = asyncio.run(_execute_plan_async(execution_id, plan_id, user_id, approval_mode))
        return result
    except Exception as e:
        logger.error(f"Execution task failed: {e}")
        # Update execution status
        asyncio.run(_update_execution_status(execution_id, "failed", error_message=str(e)))
        raise self.retry(exc=e, countdown=10)


async def _execute_plan_async(
    execution_id: str,
    plan_id: str,
    user_id: str,
    approval_mode: str | None,
) -> dict:
    """Async implementation of plan execution."""
    from rewoo.agent.loop import Agent
    from rewoo.cache.redis import CacheManager
    from rewoo.config import Settings
    from rewoo.db.models import Execution, ExecutionPlan
    from rewoo.db.session import get_db_session

    settings = Settings()
    if approval_mode:
        settings.approval_mode = approval_mode

    cache = CacheManager()

    # Update execution status to running
    async with get_db_session() as session:
        execution = await Execution.get_by_id(session, execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        await execution.update_status(session, "running")
        await cache.publish(f"execution:{execution_id}", json.dumps({
            "status": "running",
            "message": "Execution started",
        }))

    # Load plan from database
    async with get_db_session() as session:
        plan_model = await ExecutionPlan.get_by_id(session, plan_id)
        if not plan_model:
            raise ValueError(f"Plan {plan_id} not found")

    # Reconstruct the core ExecutionPlan
    from rewoo.core.types import ExecutionPlan as CorePlan, PlanStep, RiskLevel, StepStatus

    steps = []
    for s in plan_model.steps_data:
        step = PlanStep(
            index=s["index"],
            description=s["description"],
            tool=s["tool"],
            tool_args=s["tool_args"],
            risk_level=RiskLevel(s.get("risk_level", "MEDIUM")),
            risk_reason=s.get("risk_reason"),
            depends_on=s.get("depends_on", []),
            status=StepStatus(s.get("status", "approved")),
            reversible=s.get("reversible", True),
        )
        steps.append(step)

    core_plan = CorePlan(
        id=str(plan_model.id),
        task=plan_model.task,
        steps=steps,
        total_tokens=plan_model.total_tokens,
    )

    # Run the agent
    agent = Agent(settings=settings)

    # Stream progress via Redis pub/sub
    try:
        result = await agent.run(core_plan.task)

        # Update execution with results
        async with get_db_session() as session:
            execution = await Execution.get_by_id(session, execution_id)
            step_results_json = [
                {
                    "step_id": r.step_id,
                    "step_index": r.step_index,
                    "status": r.status.value,
                    "output": (r.output or "")[:5000],
                    "error": r.error,
                    "duration_seconds": r.duration_seconds,
                }
                for r in result.step_results
            ]

            await execution.update_status(
                session,
                "completed",
                answer=result.answer,
                step_results=step_results_json,
                total_tokens=result.total_tokens,
                total_duration_seconds=result.total_duration_seconds,
            )

        await cache.publish(f"execution:{execution_id}", json.dumps({
            "status": "completed",
            "answer": result.answer[:500] if result.answer else None,
            "total_tokens": result.total_tokens,
        }))

        return {
            "execution_id": execution_id,
            "status": "completed",
            "answer": result.answer,
            "total_tokens": result.total_tokens,
        }

    except Exception as e:
        logger.error(f"Execution {execution_id} failed: {e}")

        async with get_db_session() as session:
            execution = await Execution.get_by_id(session, execution_id)
            await execution.update_status(session, "failed", error_message=str(e))

        await cache.publish(f"execution:{execution_id}", json.dumps({
            "status": "failed",
            "error": str(e),
        }))

        raise


async def _update_execution_status(
    execution_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update execution status (used by retry handler)."""
    try:
        from rewoo.db.models import Execution
        from rewoo.db.session import get_db_session

        async with get_db_session() as session:
            execution = await Execution.get_by_id(session, execution_id)
            if execution:
                await execution.update_status(session, status, error_message=error_message)
    except Exception as e:
        logger.error(f"Failed to update execution status: {e}")
