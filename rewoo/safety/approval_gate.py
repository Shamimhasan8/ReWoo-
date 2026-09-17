"""Approval gate for plan execution.

Provides human-in-the-loop approval for high-risk steps and automated
approval for low-risk steps based on the configured approval mode.
"""

from __future__ import annotations

import logging
from typing import Protocol

from rewoo.config import Settings
from rewoo.core.types import ExecutionPlan, PlanStep, RiskLevel, StepStatus

logger = logging.getLogger(__name__)


class ApprovalGate(Protocol):
    """Protocol for approval gate implementations."""

    def review_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Review and potentially modify a plan before execution.

        Args:
            plan: The execution plan to review.

        Returns:
            The (possibly modified) execution plan with approval statuses set.
        """
        ...


class CLIGate:
    """Interactive CLI approval gate.

    Displays the execution plan and prompts the user to approve, reject,
    or modify individual steps. Steps classified as HIGH or CRITICAL
    always require explicit approval.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def review_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Review a plan via CLI interaction.

        For each step, if it requires approval (HIGH/CRITICAL), prompt
        the user. Otherwise, auto-approve based on the approval mode.
        """
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()

        # Display the plan
        table = Table(title=f"📋 Execution Plan ({plan.step_count} steps)")
        table.add_column("Step", style="bold", width=6)
        table.add_column("Risk", width=10)
        table.add_column("Tool", width=14)
        table.add_column("Description", width=50)
        table.add_column("Status", width=10)

        for step in plan.steps:
            risk_style = {
                RiskLevel.LOW: "green",
                RiskLevel.MEDIUM: "yellow",
                RiskLevel.HIGH: "red",
                RiskLevel.CRITICAL: "bold red",
            }.get(step.risk_level, "white")

            table.add_row(
                str(step.index),
                f"[{risk_style}]{step.risk_level.value}[/{risk_style}]",
                step.tool,
                step.description,
                step.status.value,
            )

        console.print(table)

        # Process each step
        for step in plan.steps:
            if step.status != StepStatus.PENDING:
                continue

            if not step.needs_approval:
                # Auto-approve low/medium risk steps
                step.status = StepStatus.APPROVED
                continue

            # High/critical risk — require explicit approval
            console.print()
            risk_style = "bold red" if step.risk_level == RiskLevel.CRITICAL else "red"
            console.print(
                Panel(
                    f"[{risk_style}]⚠️ Step {step.index} requires approval[/{risk_style}]\n"
                    f"Tool: {step.tool}\n"
                    f"Args: {step.tool_args}\n"
                    f"Risk: {step.risk_level.value} — {step.risk_reason or 'No reason provided'}\n"
                    f"Reversible: {'Yes' if step.reversible else 'No'}",
                    title=f"Step {step.index}: {step.description}",
                )
            )

            while True:
                response = console.input("[bold]Approve? [y/N/edit/skip]: [/bold]").strip().lower()
                if response in ("y", "yes"):
                    step.status = StepStatus.APPROVED
                    console.print(f"[green]✓ Step {step.index} approved[/green]")
                    break
                elif response in ("n", "no", ""):
                    step.status = StepStatus.REJECTED
                    console.print(f"[red]✗ Step {step.index} rejected[/red]")
                    break
                elif response == "skip":
                    step.status = StepStatus.SKIPPED
                    console.print(f"[yellow]⊘ Step {step.index} skipped[/yellow]")
                    break
                elif response == "edit":
                    new_desc = console.input(f"  New description (Enter to keep): ").strip()
                    if new_desc:
                        step.description = new_desc
                    new_args = console.input(f"  New args JSON (Enter to keep): ").strip()
                    if new_args:
                        import json
                        try:
                            step.tool_args = json.loads(new_args)
                        except json.JSONDecodeError:
                            console.print("[red]Invalid JSON, keeping original args[/red]")
                    step.status = StepStatus.APPROVED
                    console.print(f"[green]✓ Step {step.index} approved (edited)[/green]")
                    break
                else:
                    console.print("[dim]Please enter y, n, skip, or edit[/dim]")

        return plan


class AutoGate:
    """Automated approval gate.

    Automatically approves LOW and MEDIUM risk steps. Holds HIGH and
    CRITICAL steps for review based on the configured approval mode.
    In 'auto' mode, even HIGH steps are approved automatically with
    a warning. In 'none' mode, all steps are approved.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def review_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Review a plan automatically based on risk levels and settings.

        Approval logic:
        - 'none' mode: All steps approved regardless of risk.
        - 'auto' mode: LOW/MEDIUM auto-approved, HIGH/CRITICAL held
          but approved with warning.
        - 'cli' mode: Falls through to CLIGate for interactive review.
        """
        mode = self.settings.approval_mode if self.settings else "auto"

        if mode == "none":
            for step in plan.steps:
                if step.status == StepStatus.PENDING:
                    step.status = StepStatus.APPROVED
            logger.info("All steps auto-approved (approval_mode=none)")
            return plan

        if mode == "cli":
            # Delegate to CLI gate for interactive review
            gate = CLIGate(settings=self.settings)
            return gate.review_plan(plan)

        # Auto mode: approve LOW/MEDIUM, approve HIGH/CRITICAL with warning
        for step in plan.steps:
            if step.status != StepStatus.PENDING:
                continue

            if not step.needs_approval:
                step.status = StepStatus.APPROVED
                logger.info(f"Step {step.index} auto-approved (risk={step.risk_level.value})")
            else:
                # In auto mode, still approve but log a warning
                step.status = StepStatus.APPROVED
                logger.warning(
                    f"Step {step.index} auto-approved despite {step.risk_level.value} risk: "
                    f"{step.description}"
                )

        return plan


def create_approval_gate(settings: Settings) -> ApprovalGate:
    """Factory function to create the appropriate approval gate.

    Args:
        settings: ReWoo settings containing approval mode configuration.

    Returns:
        An ApprovalGate instance appropriate for the configured mode.
    """
    if settings.approval_mode == "cli":
        return CLIGate(settings=settings)
    return AutoGate(settings=settings)
