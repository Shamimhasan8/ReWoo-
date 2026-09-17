"""File operation tools — read, write, and delete files.

All file operations support path restriction through the sandbox
system to prevent unauthorized access to sensitive files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def file_read(path: str, encoding: str = "utf-8", max_lines: int | None = None) -> str:
    """Read the contents of a file.

    Args:
        path: Path to the file to read.
        encoding: File encoding (default: utf-8).
        max_lines: Maximum number of lines to read (None = all).

    Returns:
        The file contents as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be read.
    """
    logger.info(f"file.read: {path}")
    file_path = Path(path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not file_path.is_file():
        raise ValueError(f"Not a file: {path}")

    try:
        content = file_path.read_text(encoding=encoding)

        if max_lines is not None:
            lines = content.splitlines()
            content = "\n".join(lines[:max_lines])
            if len(lines) > max_lines:
                content += f"\n... ({len(lines) - max_lines} more lines)"

        logger.debug(f"file.read completed: {len(content)} chars from {path}")
        return content

    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {path}")
    except Exception as e:
        logger.error(f"file.read failed: {e}")
        raise


async def file_write(path: str, content: str, encoding: str = "utf-8", append: bool = False) -> str:
    """Write content to a file.

    Args:
        path: Path to the file to write.
        content: Content to write.
        encoding: File encoding (default: utf-8).
        append: Whether to append instead of overwriting.

    Returns:
        Confirmation message.

    Raises:
        PermissionError: If the file cannot be written.
    """
    logger.info(f"file.write: {path} (append={append})")
    file_path = Path(path).resolve()

    # Create parent directories if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        mode = "a" if append else "w"
        file_path.write_text(content, encoding=encoding)

        action = "Appended to" if append else "Wrote"
        result = f"{action} {path} ({len(content)} chars)"
        logger.debug(result)
        return result

    except PermissionError:
        raise PermissionError(f"Permission denied writing file: {path}")
    except Exception as e:
        logger.error(f"file.write failed: {e}")
        raise


async def file_delete(path: str) -> str:
    """Delete a file.

    This is a HIGH risk operation and will always require approval
    in the ReWoo safety model.

    Args:
        path: Path to the file to delete.

    Returns:
        Confirmation message.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be deleted.
    """
    logger.warning(f"file.delete: {path}")
    file_path = Path(path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not file_path.is_file():
        raise ValueError(f"Not a file: {path}")

    try:
        file_path.unlink()
        result = f"Deleted {path}"
        logger.info(result)
        return result

    except PermissionError:
        raise PermissionError(f"Permission denied deleting file: {path}")
    except Exception as e:
        logger.error(f"file.delete failed: {e}")
        raise
