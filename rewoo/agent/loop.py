"""Main agent loop — orchestrates the Planner→Reviewer→Worker→Solver cycle.

The Agent class is the primary entry point for ReWoo. It ties together
all four stages of the ReWOO architecture and manages the complete
execution lifecycle.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from rewoo.config import Settings
from rewoo.core.planner import Planner
from rewoo.core.reviewer import Reviewer
from rewoo.core.solver import Solver
from rewoo.core.types import ExecutionPlan, ExecutionResult
from rewoo.core.worker import Worker
from rewoo.providers.anthropic import AnthropicProvider
from rewoo.providers.base import BaseProvider
from rewoo.providers.openai import OpenAIProvider
from rewoo.safety.audit import AuditLogger
from rewoo.tools.registry import ToolRegistry, create_default_registry
from rewoo.tools.sandbox import SandboxedExecutor

logger = logging.getLogger(__name__)


def _create_provider(settings: Settings) -> BaseProvider:
    """Create the appropriate LLM provider based on settings.

    Args:
        settings: ReWoo settings with model and API key configuration.

    Returns:
        A configured BaseProvider instance.
    """
    provider_name = settings.get_provider()
    model_name = settings.get_model_name()

    if provider_name == "openai":
        return OpenAIProvider(
            model=model_name,
            api_key=settings.openai_api_key,
        )
    elif provider_name == "openrouter":
        return OpenAIProvider(
            model=model_name,
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
    else:  # anthropic (default)
        return AnthropicProvider(
            model=model_name,
            api_key=settings.anthropic_api_key,
        )


class Agent:
    """ReWoo agent — orchestrates the full plan-review-execute-solve cycle.

    The Agent is the primary interface for running tasks with ReWoo.
    It manages the lifecycle of task execution:

    1. Planner generates a complete execution plan
    2. Reviewer presents the plan and collects approvals
    3. Worker executes approved steps in dependency order
    4. Solver synthesizes all results into a final answer

    All events are logged to the immutable audit trail.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        provider: BaseProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        """Initialize the ReWoo agent.

        Args:
            settings: ReWoo settings. Uses defaults if not provided.
            provider: LLM provider. Created from settings if not provided.
            tool_registry: Tool registry. Uses built-in tools if not provided.
            audit_logger: Audit logger. Created from settings if not provided.
        """
        self.settings = settings or Settings()
        self.settings.ensure_dirs()

        self.provider = provider or _create_provider(self.settings)
        self.registry = tool_registry or create_default_registry()
        self.audit = audit_logger or AuditLogger(path=self.settings.audit_path)

        # Initialize pipeline stages
        self.planner = Planner(provider=self.provider, settings=self.settings)
        self.reviewer = Reviewer(settings=self.settings, audit_logger=self.audit)
        self.solver = Solver(provider=self.provider, settings=self.settings)
        self.worker = Worker(
            tool_registry=self.registry,
            settings=self.settings,
            sandbox=SandboxedExecutor(enabled=self.settings.sandbox_enabled),
        )

    async def run(self, task: str) -> ExecutionResult:
        """Run a task through the full plan-review-execute-solve cycle.

        This is the primary method for executing tasks with ReWoo.

        Args:
            task: The task description to execute.

        Returns:
            An ExecutionResult with the final answer and all metadata.
        """
        start_time = time.monotonic()
        logger.info(f"Agent.run: {task[:100]}")

        try:
            # Stage 1: Plan
            logger.info("Stage 1: Planning")
            plan = await self.planner.plan(task)

            # Stage 2: Review
            logger.info("Stage 2: Reviewing plan")
            reviewed_plan = self.reviewer.review(plan)

            # Stage 3: Execute
            logger.info("Stage 3: Executing approved steps")
            step_results = await self.worker.execute_plan(reviewed_plan)

            # Stage 4: Solve
            logger.info("Stage 4: Synthesizing final answer")
            result = await self.solver.solve(task, reviewed_plan, step_results)

            # Log completion
            self.audit.log_execution_completed(result)

            total_time = time.monotonic() - start_time
            logger.info(
                f"Agent.run complete: {result.total_tokens} tokens, "
                f"{total_time:.2f}s, {len(step_results)} steps"
            )

            return result

        except Exception as e:
            logger.error(f"Agent.run failed: {e}")
            # Return a minimal result on failure
            return ExecutionResult(
                plan_id="error",
                task=task,
                answer=f"Execution failed: {e}",
                total_duration_seconds=time.monotonic() - start_time,
            )

    async def plan(self, task: str) -> ExecutionPlan:
        """Generate an execution plan without executing it.

        Useful for previewing what the agent would do before committing
        to execution.

        Args:
            task: The task description to plan for.

        Returns:
            An ExecutionPlan with all steps identified and risk-classified.
        """
        logger.info(f"Agent.plan: {task[:100]}")
        return await self.planner.plan(task)
