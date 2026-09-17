"""CLI gateway — command-line interface for ReWoo.

Provides the primary user interface via the terminal, using Rich
for formatted output and interactive prompts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rewoo.core.types import ExecutionPlan, ExecutionResult, RiskLevel
from rewoo.gateway.base import BaseGateway

logger = logging.getLogger(__name__)


class CLIGateway(BaseGateway):
    """Command-line interface gateway using Rich for formatted output.

    Handles displaying plans, results, and progress to the terminal.
    Works in conjunction with the CLI approval gate for interactive
    approval of high-risk steps.
    """

    def __init__(self) -> None:
        self.console = Console()

    async def receive_task(self) -> str:
        """Receive a task from the user via command-line argument.

        This is a placeholder — actual task input comes from the
        CLI command arguments, not interactive input.

        Returns:
            Empty string (task comes from CLI args).
        """
        return ""

    async def display_plan(self, plan: Any) -> None:
        """Display an execution plan using a Rich table.

        Args:
            plan: The ExecutionPlan to display.
        """
        if not isinstance(plan, ExecutionPlan):
            self.console.print("[yellow]Invalid plan object[/yellow]")
            return

        table = Table(title=f"📋 Execution Plan ({plan.step_count} steps)")
        table.add_column("Step", style="bold", width=6)
        table.add_column("Risk", width=10)
        table.add_column("Tool", style="cyan", width=14)
        table.add_column("Description", width=50)
        table.add_column("Reversible", width=10)

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
                "Yes" if step.reversible else "No",
            )

        self.console.print()
        self.console.print(table)

        if plan.has_high_risk:
            self.console.print(
                "\n[bold yellow]⚠️ This plan contains HIGH/CRITICAL risk steps that require approval.[/bold yellow]"
            )
        else:
            self.console.print(
                "\n[green]All steps are LOW risk. Proceeding automatically.[/green]"
            )

    async def display_result(self, result: ExecutionResult) -> None:
        """Display the final execution result.

        Args:
            result: The execution result to display.
        """
        self.console.print()
        self.console.print(
            Panel(
                result.answer,
                title="✅ Result",
                border_style="green",
            )
        )

        # Summary statistics
        completed = sum(1 for r in result.step_results if r.status.value == "completed")
        failed = sum(1 for r in result.step_results if r.status.value == "failed")
        total_steps = len(result.step_results)

        self.console.print(
            f"\n[dim]Steps: {completed}/{total_steps} completed, {failed} failed | "
            f"Tokens: {result.total_tokens} | "
            f"Duration: {result.total_duration_seconds:.1f}s[/dim]"
        )

    async def display_error(self, error: str) -> None:
        """Display an error message.

        Args:
            error: The error message to display.
        """
        self.console.print(
            Panel(
                error,
                title="❌ Error",
                border_style="red",
            )
        )

    def display_welcome(self) -> None:
        """Display a welcome banner."""
        self.console.print(
            Panel(
                "[bold]ReWoo[/bold] — Reason first. Execute safely. Learn always.\n"
                "[dim]A low-risk, plan-first AI agent framework[/dim]",
                border_style="blue",
            )
        )

    def display_progress(self, step_index: int, total: int, status: str) -> None:
        """Display a progress update during execution.

        Args:
            step_index: Current step index.
            total: Total number of steps.
            status: Status of the current step.
        """
        icon = "✓" if status == "completed" else "✗" if status == "failed" else "→"
        style = "green" if status == "completed" else "red" if status == "failed" else "blue"
        self.console.print(f"[{style}]{icon} Step {step_index} {status}[/{style}]")
