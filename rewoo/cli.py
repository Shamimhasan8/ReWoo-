"""ReWoo CLI — command-line interface for the ReWoo agent framework.

Provides the `rewoo` command with subcommands for running tasks,
viewing plans, inspecting audit logs, managing skills, and
diagnosing configuration issues.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from rewoo import __version__
from rewoo.agent.loop import Agent
from rewoo.config import Settings
from rewoo.safety.audit import AuditLogger

console = Console()


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity level.

    Args:
        verbose: Whether to enable verbose (DEBUG) logging.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version=__version__, prog_name="rewoo")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
def main(verbose: bool) -> None:
    """🪢 ReWoo — Reason first. Execute safely. Learn always.

    A low-risk, plan-first AI agent framework built on the ReWOO architecture.
    """
    _setup_logging(verbose)


@main.command()
@click.argument("task")
@click.option("--model", default=None, help="Override the model (e.g., openai/gpt-4o)")
@click.option("--approval", default=None, type=click.Choice(["auto", "cli", "none"]), help="Override approval mode")
@click.option("--no-sandbox", is_flag=True, help="Disable sandboxed execution")
def run(task: str, model: Optional[str], approval: Optional[str], no_sandbox: bool) -> None:
    """Run a task through the full plan-review-execute-solve cycle.

    \b
    Example:
      rewoo run "find all Python files modified today"
      rewoo run "delete old log files" --approval cli
    """
    settings = Settings()

    # Apply CLI overrides
    if model:
        settings.model = model
    if approval:
        settings.approval_mode = approval
    if no_sandbox:
        settings.sandbox_enabled = False

    # Check for API keys
    provider = settings.get_provider()
    if provider == "anthropic" and not settings.anthropic_api_key:
        console.print("[bold red]Error: ANTHROPIC_API_KEY not set.[/bold red]")
        console.print("Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)
    elif provider == "openai" and not settings.openai_api_key:
        console.print("[bold red]Error: OPENAI_API_KEY not set.[/bold red]")
        console.print("Set it with: export OPENAI_API_KEY=sk-...")
        sys.exit(1)
    elif provider == "openrouter" and not settings.openrouter_api_key:
        console.print("[bold red]Error: OPENROUTER_API_KEY not set.[/bold red]")
        console.print("Set it with: export OPENROUTER_API_KEY=sk-...")
        sys.exit(1)

    agent = Agent(settings=settings)

    console.print(f"\n[bold]🪢 ReWoo[/bold] v{__version__}")
    console.print(f"[dim]Model: {settings.model} | Approval: {settings.approval_mode} | Sandbox: {'on' if settings.sandbox_enabled else 'off'}[/dim]")
    console.print(f"[bold]Task:[/bold] {task}\n")

    try:
        result = asyncio.run(agent.run(task))

        if result.answer:
            console.print()
            console.print(f"[bold green]Result:[/bold green] {result.answer}")
            console.print(
                f"\n[dim]Tokens: {result.total_tokens} | "
                f"Duration: {result.total_duration_seconds:.1f}s | "
                f"Steps: {len(result.step_results)}[/dim]"
            )
        else:
            console.print("[yellow]No result produced.[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        if verbose := "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@main.command()
@click.argument("task")
@click.option("--model", default=None, help="Override the model")
def plan(task: str, model: Optional[str]) -> None:
    """Show the execution plan for a task without executing it.

    \b
    Example:
      rewoo plan "find all Python files modified today"
    """
    settings = Settings()
    if model:
        settings.model = model

    # Check for API keys
    provider = settings.get_provider()
    if provider == "anthropic" and not settings.anthropic_api_key:
        console.print("[bold red]Error: ANTHROPIC_API_KEY not set.[/bold red]")
        sys.exit(1)
    elif provider in ("openai",) and not settings.openai_api_key:
        console.print("[bold red]Error: OPENAI_API_KEY not set.[/bold red]")
        sys.exit(1)
    elif provider == "openrouter" and not settings.openrouter_api_key:
        console.print("[bold red]Error: OPENROUTER_API_KEY not set.[/bold red]")
        sys.exit(1)

    agent = Agent(settings=settings)

    console.print(f"\n[bold]🪢 ReWoo[/bold] — Planning mode")
    console.print(f"[bold]Task:[/bold] {task}\n")

    try:
        execution_plan = asyncio.run(agent.plan(task))

        table = Table(title=f"📋 Execution Plan ({execution_plan.step_count} steps)")
        table.add_column("Step", style="bold", width=6)
        table.add_column("Risk", width=10)
        table.add_column("Tool", style="cyan", width=14)
        table.add_column("Description", width=50)
        table.add_column("Deps", width=10)

        for step in execution_plan.steps:
            risk_style = {
                "LOW": "green",
                "MEDIUM": "yellow",
                "HIGH": "red",
                "CRITICAL": "bold red",
            }.get(step.risk_level.value, "white")

            deps = ", ".join(str(d) for d in step.depends_on) if step.depends_on else "—"

            table.add_row(
                str(step.index),
                f"[{risk_style}]{step.risk_level.value}[/{risk_style}]",
                step.tool,
                step.description,
                deps,
            )

        console.print(table)

        if execution_plan.has_high_risk:
            console.print(
                "\n[bold yellow]⚠️ This plan contains HIGH/CRITICAL risk steps.[/bold yellow]"
            )

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.option("--limit", default=20, help="Number of entries to show")
@click.option("--plan-id", default=None, help="Filter by plan ID")
def audit(limit: int, plan_id: Optional[str]) -> None:
    """View recent audit log entries.

    \b
    Example:
      rewoo audit --limit 10
      rewoo audit --plan-id abc123
    """
    settings = Settings()
    audit_logger = AuditLogger(path=settings.audit_path)

    entries = audit_logger.read_entries(limit=limit, plan_id=plan_id)

    if not entries:
        console.print("[dim]No audit entries found.[/dim]")
        return

    table = Table(title="Audit Log")
    table.add_column("Time", width=19)
    table.add_column("Event", style="cyan", width=22)
    table.add_column("Plan ID", width=12)
    table.add_column("Step", width=5)
    table.add_column("Details", width=60)

    for entry in entries[-limit:]:
        details = str(entry.data)[:60] if entry.data else ""
        table.add_row(
            entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            entry.event_type,
            entry.plan_id or "—",
            str(entry.step_index) if entry.step_index is not None else "—",
            details,
        )

    console.print(table)


@main.command()
def skills() -> None:
    """List learned skills.

    Shows all skills that have been learned from previous successful
    executions, including usage statistics.
    """
    from rewoo.agent.memory import Memory

    settings = Settings()
    memory = Memory(skills_dir=settings.skills_dir)

    all_skills = memory.list_skills()

    if not all_skills:
        console.print("[dim]No learned skills yet. Skills are created from successful executions.[/dim]")
        return

    table = Table(title="Learned Skills")
    table.add_column("ID", style="bold", width=20)
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Description", width=40)
    table.add_column("Uses", width=6)
    table.add_column("Success", width=8)
    table.add_column("Last Used", width=19)

    for skill in all_skills:
        table.add_row(
            skill.id,
            skill.name,
            skill.description[:40],
            str(skill.use_count),
            f"{skill.success_count}/{skill.use_count}",
            skill.last_used.strftime("%Y-%m-%d %H:%M:%S") if skill.last_used else "Never",
        )

    console.print(table)


@main.command()
def config() -> None:
    """Show current configuration.

    Displays the active ReWoo settings including model, approval mode,
    sandbox status, and API key availability (keys are masked).
    """
    settings = Settings()

    table = Table(title="ReWoo Configuration")
    table.add_column("Setting", style="bold", width=25)
    table.add_column("Value", width=50)

    # Mask API keys
    def mask_key(key: str | None) -> str:
        if not key:
            return "[red]not set[/red]"
        if len(key) <= 8:
            return "****"
        return key[:4] + "..." + key[-4:]

    table.add_row("Model", settings.model)
    table.add_row("Provider", settings.get_provider())
    table.add_row("Anthropic API Key", mask_key(settings.anthropic_api_key))
    table.add_row("OpenAI API Key", mask_key(settings.openai_api_key))
    table.add_row("OpenRouter API Key", mask_key(settings.openrouter_api_key))
    table.add_row("Approval Mode", settings.approval_mode)
    table.add_row("Sandbox Enabled", str(settings.sandbox_enabled))
    table.add_row("Audit Path", str(settings.audit_path))
    table.add_row("Max Plan Steps", str(settings.max_plan_steps))
    table.add_row("Timeout (seconds)", str(settings.timeout_seconds))

    console.print(table)


@main.command()
def doctor() -> None:
    """Diagnose configuration issues.

    Checks that all required dependencies are available, API keys
    are set, and the environment is properly configured.
    """
    settings = Settings()
    issues: list[str] = []

    console.print("[bold]🩺 ReWoo Doctor — Diagnosing configuration...[/bold]\n")

    # Check Python version
    import sys
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        console.print(f"[green]✓[/green] Python {py_version}")
    else:
        console.print(f"[red]✗[/red] Python {py_version} (requires 3.11+)")
        issues.append("Python version too old")

    # Check API keys
    provider = settings.get_provider()
    if provider == "anthropic":
        if settings.anthropic_api_key:
            console.print("[green]✓[/green] Anthropic API key set")
        else:
            console.print("[red]✗[/red] Anthropic API key not set (ANTHROPIC_API_KEY)")
            issues.append("Anthropic API key missing")
    elif provider == "openai":
        if settings.openai_api_key:
            console.print("[green]✓[/green] OpenAI API key set")
        else:
            console.print("[red]✗[/red] OpenAI API key not set (OPENAI_API_KEY)")
            issues.append("OpenAI API key missing")
    elif provider == "openrouter":
        if settings.openrouter_api_key:
            console.print("[green]✓[/green] OpenRouter API key set")
        else:
            console.print("[red]✗[/red] OpenRouter API key not set (OPENROUTER_API_KEY)")
            issues.append("OpenRouter API key missing")

    # Check dependencies
    deps = [
        ("pydantic", "pydantic"),
        ("pydantic_settings", "pydantic-settings"),
        ("anthropic", "anthropic"),
        ("openai", "openai"),
        ("rich", "rich"),
        ("httpx", "httpx"),
        ("click", "click"),
        ("aiofiles", "aiofiles"),
    ]

    for module_name, package_name in deps:
        try:
            __import__(module_name)
            console.print(f"[green]✓[/green] {package_name}")
        except ImportError:
            console.print(f"[yellow]✗[/yellow] {package_name} not installed")
            issues.append(f"{package_name} not installed")

    # Check audit directory
    try:
        settings.audit_path.parent.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Audit directory: {settings.audit_path.parent}")
    except Exception as e:
        console.print(f"[red]✗[/red] Cannot create audit directory: {e}")
        issues.append(f"Audit directory issue: {e}")

    # Summary
    console.print()
    if issues:
        console.print(f"[bold red]Found {len(issues)} issue(s):[/bold red]")
        for issue in issues:
            console.print(f"  • {issue}")
    else:
        console.print("[bold green]All checks passed! ReWoo is ready to use.[/bold green]")


if __name__ == "__main__":
    main()
