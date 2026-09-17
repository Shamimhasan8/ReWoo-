"""Solver module — synthesizes all step results into a final answer.

The Solver is the fourth and final stage of the ReWOO architecture.
It takes all the step results collected by the Worker and makes a
single LLM call to produce the final, coherent answer.
"""

from __future__ import annotations

import logging
from typing import Any

from rewoo.config import Settings
from rewoo.core.types import ExecutionPlan, ExecutionResult, StepResult
from rewoo.providers.base import BaseProvider, Message

logger = logging.getLogger(__name__)

SOLVER_SYSTEM_PROMPT = """You are the Solver stage of a ReWOO agent system. Your job is to synthesize the results of multiple executed steps into a single, coherent final answer.

Rules:
1. Review all step results carefully.
2. Synthesize the information into a clear, comprehensive answer.
3. If any steps failed, acknowledge the failures and explain what was still accomplished.
4. Cite specific step results when making claims.
5. Be concise but thorough — the user needs actionable information.
6. If the original task cannot be fully completed due to failures, explain what was achieved and what is missing.

Respond with the final answer directly, without any formatting prefixes."""

SOLVER_USER_TEMPLATE = """Original task: {task}

Step results:
{step_results}

Based on these results, provide the final answer to the original task."""


class Solver:
    """Synthesizes step results into a final answer using a single LLM call.

    The Solver receives all step results from the Worker and produces
    the final answer. This is a single LLM call (not a multi-turn
    conversation), which is the key efficiency gain of the ReWOO
    architecture over reactive agent loops.
    """

    def __init__(self, provider: BaseProvider, settings: Settings | None = None) -> None:
        self.provider = provider
        self.settings = settings

    async def solve(
        self,
        task: str,
        plan: ExecutionPlan,
        step_results: list[StepResult],
    ) -> ExecutionResult:
        """Synthesize step results into a final answer.

        Args:
            task: The original task description.
            plan: The execution plan that was executed.
            step_results: Results from executing the plan steps.

        Returns:
            An ExecutionResult with the final synthesized answer.
        """
        logger.info(f"Solving with {len(step_results)} step results")

        # Format step results for the LLM
        results_text = self._format_results(step_results)

        messages = [
            Message(role="system", content=SOLVER_SYSTEM_PROMPT),
            Message(
                role="user",
                content=SOLVER_USER_TEMPLATE.format(task=task, step_results=results_text),
            ),
        ]

        max_tokens = getattr(self.settings, "max_solve_tokens", 4096) if self.settings else 4096
        response = await self.provider.complete(
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.0,
        )

        total_tokens = plan.total_tokens + response.total_tokens
        total_duration = sum(r.duration_seconds for r in step_results)

        result = ExecutionResult(
            plan_id=plan.id,
            task=task,
            answer=response.content,
            step_results=step_results,
            total_tokens=total_tokens,
            total_duration_seconds=total_duration,
            plan=plan,
        )

        logger.info(f"Solver complete: {response.total_tokens} tokens, {total_duration:.2f}s total")
        return result

    def _format_results(self, results: list[StepResult]) -> str:
        """Format step results into a readable string for the LLM.

        Args:
            results: List of step results to format.

        Returns:
            Formatted string with all step results.
        """
        parts: list[str] = []
        for r in results:
            status_icon = "✓" if r.status.value == "completed" else "✗"
            part = f"{status_icon} Step {r.step_index} ({r.status.value}):\n"
            if r.output:
                part += f"  Output: {r.output[:2000]}\n"
            if r.error:
                part += f"  Error: {r.error[:500]}\n"
            parts.append(part)

        return "\n".join(parts)
