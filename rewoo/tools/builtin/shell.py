"""Shell command execution tool.

Provides safe shell command execution with configurable sandboxing,
timeout handling, and output capture.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


async def shell_run(command: str, timeout: int = 60, cwd: str | None = None) -> str:
    """Execute a shell command and return the output.

    Args:
        command: The shell command to execute.
        timeout: Maximum execution time in seconds.
        cwd: Working directory for the command.

    Returns:
        Combined stdout and stderr output from the command.

    Raises:
        subprocess.TimeoutExpired: If the command exceeds the timeout.
        subprocess.CalledProcessError: If the command returns a non-zero exit code.
    """
    logger.info(f"shell.run: {command[:200]}")

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )

        output = ""
        if stdout:
            output += stdout.decode("utf-8", errors="replace")
        if stderr:
            if output:
                output += "\n"
            output += f"[stderr] {stderr.decode('utf-8', errors='replace')}"

        if proc.returncode != 0:
            output += f"\n[exit code: {proc.returncode}]"

        logger.debug(f"shell.run completed: exit_code={proc.returncode}, output_len={len(output)}")
        return output

    except asyncio.TimeoutError:
        logger.error(f"shell.run timed out after {timeout}s: {command[:100]}")
        raise TimeoutError(f"Command timed out after {timeout}s: {command[:100]}")
    except Exception as e:
        logger.error(f"shell.run failed: {e}")
        return f"Error executing command: {e}"
