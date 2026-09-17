"""Sandboxed execution for destructive or high-risk tools.

Provides an execution environment that limits what tools can do,
particularly for shell commands and file operations that could
cause irreversible changes.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SandboxedExecutor:
    """Executes tools in a sandboxed environment.

    For shell commands, the sandbox:
    - Runs in a temporary directory by default
    - Sets a timeout for command execution
    - Blocks certain dangerous patterns
    - Captures stdout and stderr

    For file operations, the sandbox:
    - Restricts paths to allowed directories
    - Prevents writes outside allowed paths
    - Logs all file operations
    """

    # Commands that are always blocked
    BLOCKED_PATTERNS = [
        "rm -rf /",
        "mkfs",
        "dd if=",
        "> /dev/sd",
        "shutdown",
        "reboot",
        "init 0",
        "init 6",
    ]

    def __init__(
        self,
        enabled: bool = True,
        allowed_paths: list[str] | None = None,
        timeout: int = 300,
    ) -> None:
        self.enabled = enabled
        self.allowed_paths = [Path(p).resolve() for p in (allowed_paths or ["."])]
        self.timeout = timeout

    async def execute(
        self,
        tool_name: str,
        tool_fn: Callable[..., Any],
        args: dict[str, Any],
    ) -> Any:
        """Execute a tool in the sandbox.

        Args:
            tool_name: Name of the tool being executed.
            tool_fn: The tool function to call.
            args: Arguments to pass to the tool.

        Returns:
            The tool's return value.

        Raises:
            PermissionError: If the operation is blocked by sandbox policy.
            TimeoutError: If the execution exceeds the timeout.
        """
        logger.info(f"Sandboxed execution: {tool_name}")

        # Pre-execution checks
        self._check_args(tool_name, args)

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._call_tool(tool_fn, args),
                timeout=self.timeout,
            )
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Sandboxed execution of {tool_name} timed out after {self.timeout}s"
            )

    async def _call_tool(self, tool_fn: Callable[..., Any], args: dict[str, Any]) -> Any:
        """Call a tool function, handling both sync and async functions.

        Args:
            tool_fn: The tool function.
            args: Arguments to pass.

        Returns:
            The tool's return value.
        """
        if asyncio.iscoroutinefunction(tool_fn):
            return await tool_fn(**args)
        else:
            return await asyncio.to_thread(tool_fn, **args)

    def _check_args(self, tool_name: str, args: dict[str, Any]) -> None:
        """Check tool arguments against sandbox policies.

        Args:
            tool_name: Name of the tool.
            args: Tool arguments to check.

        Raises:
            PermissionError: If the arguments violate sandbox policy.
        """
        if tool_name == "shell.run":
            command = args.get("command", "")
            for pattern in self.BLOCKED_PATTERNS:
                if pattern in command:
                    raise PermissionError(
                        f"Sandbox blocked dangerous command pattern: '{pattern}'"
                    )

        elif tool_name in ("file.write", "file.delete"):
            path = args.get("path", "")
            if path and self.allowed_paths:
                resolved = Path(path).resolve()
                if not any(
                    str(resolved).startswith(str(allowed))
                    for allowed in self.allowed_paths
                ):
                    raise PermissionError(
                        f"Sandbox blocked file operation outside allowed paths: {path}"
                    )

    async def run_shell_sandboxed(self, command: str, cwd: str | None = None) -> str:
        """Run a shell command in a subprocess sandbox.

        Args:
            command: The shell command to run.
            cwd: Working directory (defaults to a temp directory).

        Returns:
            Combined stdout and stderr output.

        Raises:
            PermissionError: If the command is blocked.
            subprocess.TimeoutExpired: If the command times out.
        """
        # Check for blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in command:
                raise PermissionError(f"Blocked dangerous command: '{pattern}'")

        work_dir = cwd or tempfile.mkdtemp(prefix="rewoo_sandbox_")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )

            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += stderr.decode("utf-8", errors="replace")

            return output

        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(
                f"Shell command timed out after {self.timeout}s: {command[:100]}"
            )
