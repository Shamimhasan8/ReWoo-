"""Worker module — executes individual plan steps in dependency order.

The Worker is the third stage of the ReWOO architecture (after Planner
and Reviewer). It executes each approved step, respecting dependency
ordering, and collects the results for the Solver.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from rewoo.config import Settings
from rewoo.core.types import ExecutionPlan, PlanStep, StepResult, StepStatus
from rewoo.tools.registry import ToolRegistry
from rewoo.tools.sandbox import SandboxedExecutor

logger = logging.getLogger(__name__)


class Worker:
    """Executes approved plan steps in dependency order.

    The Worker iterates through the plan steps, executing each APPROVED
    step whose dependencies have all completed. Steps that were REJECTED
    or SKIPPED are not executed. Destructive tools are run in a sandbox
    if sandbox mode is enabled.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        settings: Settings | None = None,
        sandbox: SandboxedExecutor | None = None,
    ) -> None:
        self.registry = tool_registry
        self.settings = settings
        self.sandbox = sandbox or SandboxedExecutor(enabled=settings.sandbox_enabled if settings else True)

    async def execute_step(self, step: PlanStep, context: dict[str, Any] | None = None) -> StepResult:
        """Execute a single plan step.

        Args:
            step: The plan step to execute.
            context: Optional context from previous step results.

        Returns:
            A StepResult with the execution outcome.
        """
        start_time = time.monotonic()
        logger.info(f"Executing step {step.index}: {step.tool} — {step.description[:80]}")

        # Check if step should be executed
        if step.status not in (StepStatus.APPROVED, StepStatus.PENDING):
            return StepResult(
                step_id=step.id,
                step_index=step.index,
                status=step.status,
                output=None,
                duration_seconds=time.monotonic() - start_time,
            )

        # Resolve any context references in tool_args
        resolved_args = self._resolve_args(step.tool_args, context or {})

        try:
            # Check if we need sandboxed execution
            if self.sandbox.enabled and step.risk_level.requires_approval:
                output = await self.sandbox.execute(
                    tool_name=step.tool,
                    tool_fn=self.registry.get(step.tool),
                    args=resolved_args,
                )
            else:
                # Direct execution
                tool_fn = self.registry.get(step.tool)
                if tool_fn is None:
                    raise ValueError(f"Tool not found: {step.tool}")

                if asyncio.iscoroutinefunction(tool_fn):
                    output = await tool_fn(**resolved_args)
                else:
                    output = await asyncio.to_thread(tool_fn, **resolved_args)

            step.status = StepStatus.COMPLETED
            duration = time.monotonic() - start_time

            result = StepResult(
                step_id=step.id,
                step_index=step.index,
                status=StepStatus.COMPLETED,
                output=str(output) if output is not None else "",
                duration_seconds=duration,
            )

            logger.info(f"Step {step.index} completed in {duration:.2f}s")

        except Exception as e:
            step.status = StepStatus.FAILED
            duration = time.monotonic() - start_time

            result = StepResult(
                step_id=step.id,
                step_index=step.index,
                status=StepStatus.FAILED,
                error=str(e),
                duration_seconds=duration,
            )

            logger.error(f"Step {step.index} failed: {e}")

        return result

    async def execute_plan(self, plan: ExecutionPlan) -> list[StepResult]:
        """Execute all approved steps in a plan in dependency order.

        Iterates through the plan, executing steps whose dependencies
        are all completed. Continues until all steps are processed
        or no more progress can be made.

        Args:
            plan: The execution plan to execute.

        Returns:
            List of StepResult objects for all executed steps.
        """
        results: list[StepResult] = []
        context: dict[str, Any] = {}

        # Build a map of step index -> result for dependency resolution
        result_map: dict[int, StepResult] = {}

        max_iterations = len(plan.steps) + 1  # Safety limit
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            ready_steps = plan.get_ready_steps()

            if not ready_steps:
                break

            for step in ready_steps:
                # Skip rejected and skipped steps
                if step.status in (StepStatus.REJECTED, StepStatus.SKIPPED):
                    result_map[step.index] = StepResult(
                        step_id=step.id,
                        step_index=step.index,
                        status=step.status,
                    )
                    results.append(result_map[step.index])
                    step.status = step.status  # Keep status as-is
                    continue

                # Execute the step
                step_context = self._build_step_context(step, result_map)
                result = await self.execute_step(step, context=step_context)

                result_map[step.index] = result
                results.append(result)

                # Add to shared context for dependency resolution
                context[f"step_{step.index}_output"] = result.output or ""

        return results

    def _resolve_args(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Resolve context references in tool arguments.

        Replaces references like {{step_0_output}} with actual values
        from the execution context.

        Args:
            args: The original tool arguments.
            context: The execution context with previous results.

        Returns:
            Resolved arguments with references replaced.
        """
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                ref_key = value[2:-2].strip()
                if ref_key in context:
                    resolved[key] = context[ref_key]
                else:
                    resolved[key] = value  # Keep as-is if not found
            else:
                resolved[key] = value
        return resolved

    def _build_step_context(self, step: PlanStep, result_map: dict[int, StepResult]) -> dict[str, Any]:
        """Build context for a step based on its dependencies' results.

        Args:
            step: The step to build context for.
            result_map: Map of step indices to their results.

        Returns:
            Context dict with outputs from dependency steps.
        """
        context: dict[str, Any] = {}
        for dep_index in step.depends_on:
            if dep_index in result_map:
                dep_result = result_map[dep_index]
                context[f"step_{dep_index}_output"] = dep_result.output or ""
        return context
