"""Planner module — generates complete execution plans without making any tool calls.

The Planner is the first stage of the ReWOO architecture. It takes a task
description and produces a structured execution plan with all tool calls
identified, dependency relationships established, and risk levels assigned.
No tools are actually invoked during planning — this is purely a reasoning
step powered by the LLM.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from rewoo.config import Settings
from rewoo.core.types import ExecutionPlan, PlanStep, RiskLevel
from rewoo.providers.base import BaseProvider, Message
from rewoo.safety.risk_classifier import RiskClassifier

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Planner stage of a ReWOO agent system. Your job is to create a complete, structured execution plan for the given task.

Rules:
1. You must NOT execute any tools — only plan what tools should be called.
2. Break the task into discrete steps, each using exactly one tool.
3. Each step must have: a description, a tool name, tool arguments, and dependencies on prior steps.
4. Available tools:
   - shell.run: Execute a shell command. Args: {"command": "..."}
   - file.read: Read a file's contents. Args: {"path": "..."}
   - file.write: Write content to a file. Args: {"path": "...", "content": "..."}
   - file.delete: Delete a file. Args: {"path": "..."}
   - web.search: Search the web. Args: {"query": "..."}
   - web.scrape: Scrape a web page. Args: {"url": "..."}
   - synthesize: No tool call needed — used for the final reasoning step. Args: {}
5. Mark dependencies: if step B needs output from step A, step B depends on step A (by index).
6. Be specific in tool arguments. Use exact commands, paths, and queries.
7. Minimize the number of steps — combine related operations when possible.
8. If a step involves destructive operations (deleting files, running rm, etc.), note it in the description.

Respond with a JSON array of steps. Each step should be:
{
  "index": 0,
  "description": "Human-readable description",
  "tool": "tool.name",
  "tool_args": {"key": "value"},
  "depends_on": []
}

IMPORTANT: Respond ONLY with the JSON array, no other text."""

PLANNER_USER_TEMPLATE = """Task: {task}

Create a complete execution plan for this task. Respond with a JSON array of steps."""


class Planner:
    """Generates complete execution plans from task descriptions.

    The Planner uses the LLM to reason about the task and produce a
    structured list of PlanStep objects without executing any tools.
    After generating the plan, it runs the RiskClassifier to assign
    risk levels to each step.
    """

    def __init__(self, provider: BaseProvider, settings: Settings | None = None) -> None:
        self.provider = provider
        self.settings = settings
        self.risk_classifier = RiskClassifier()

    async def plan(self, task: str) -> ExecutionPlan:
        """Generate an execution plan for the given task.

        Args:
            task: The task description to plan for.

        Returns:
            An ExecutionPlan with all steps identified and risk-classified.
        """
        logger.info(f"Planning task: {task[:100]}...")

        messages = [
            Message(role="system", content=PLANNER_SYSTEM_PROMPT),
            Message(role="user", content=PLANNER_USER_TEMPLATE.format(task=task)),
        ]

        max_tokens = getattr(self.settings, "max_plan_tokens", 4096) if self.settings else 4096
        response = await self.provider.complete(
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.0,
        )

        logger.debug(f"Planner LLM response tokens: {response.total_tokens}")

        # Parse the LLM response into plan steps
        steps = self._parse_steps(response.content)

        # Classify risk levels
        steps = self.risk_classifier.classify_plan(steps)

        plan = ExecutionPlan(
            task=task,
            steps=steps,
            total_tokens=response.total_tokens,
        )

        logger.info(f"Plan created: {plan.step_count} steps, high_risk={plan.has_high_risk}")
        return plan

    def _parse_steps(self, content: str) -> list[PlanStep]:
        """Parse the LLM response into PlanStep objects.

        Handles various response formats:
        - Pure JSON array
        - JSON wrapped in markdown code blocks
        - JSON with leading/trailing text

        Args:
            content: Raw LLM response text.

        Returns:
            List of PlanStep objects parsed from the response.
        """
        # Try to extract JSON from the response
        json_str = content.strip()

        # Handle markdown code blocks
        if "```" in json_str:
            start = json_str.find("[")
            end = json_str.rfind("]") + 1
            if start != -1 and end > start:
                json_str = json_str[start:end]
        elif json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1])

        # Try direct JSON parse
        try:
            raw_steps = json.loads(json_str)
        except json.JSONDecodeError:
            # Try to find JSON array in the text
            start = content.find("[")
            end = content.rfind("]") + 1
            if start != -1 and end > start:
                try:
                    raw_steps = json.loads(content[start:end])
                except json.JSONDecodeError:
                    logger.error("Failed to parse planner response as JSON")
                    # Fallback: create a single synthesize step
                    return [
                        PlanStep(
                            index=0,
                            description=f"Process task: {content[:200]}",
                            tool="synthesize",
                            tool_args={},
                            risk_level=RiskLevel.LOW,
                        )
                    ]
            else:
                logger.error("No JSON array found in planner response")
                return [
                    PlanStep(
                        index=0,
                        description=f"Process task directly",
                        tool="synthesize",
                        tool_args={},
                        risk_level=RiskLevel.LOW,
                    )
                ]

        if not isinstance(raw_steps, list):
            logger.error("Planner response is not a JSON array")
            return [
                PlanStep(
                    index=0,
                    description="Process task directly",
                    tool="synthesize",
                    tool_args={},
                    risk_level=RiskLevel.LOW,
                )
            ]

        # Convert raw dicts to PlanStep objects
        steps: list[PlanStep] = []
        for i, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                continue
            step = PlanStep(
                index=raw.get("index", i),
                description=raw.get("description", f"Step {i}"),
                tool=raw.get("tool", "synthesize"),
                tool_args=raw.get("tool_args", {}),
                depends_on=raw.get("depends_on", []),
                risk_level=RiskLevel.MEDIUM,  # Will be overridden by classifier
            )
            steps.append(step)

        # Ensure indices are sequential
        for i, step in enumerate(steps):
            step.index = i

        if not steps:
            steps.append(
                PlanStep(
                    index=0,
                    description="Process task directly",
                    tool="synthesize",
                    tool_args={},
                    risk_level=RiskLevel.LOW,
                )
            )

        return steps
