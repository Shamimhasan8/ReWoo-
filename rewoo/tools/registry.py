"""Tool registry — registration and lookup for ReWoo tools.

Provides a centralized registry where tools can be registered by name
and later looked up by the Worker for execution. Supports both sync
and async tool functions.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


class ToolFunc(Protocol):
    """Protocol for tool functions."""

    def __call__(self, **kwargs: Any) -> Any: ...


class ToolRegistry:
    """Centralized registry for tool functions.

    Tools are registered with a name and optional metadata (description,
    risk default, etc.). The Worker looks up tools by name when executing
    plan steps.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        *,
        description: str = "",
        risk_default: str = "MEDIUM",
        **meta: Any,
    ) -> None:
        """Register a tool function.

        Args:
            name: Unique tool name (e.g., "shell.run").
            fn: The callable tool function.
            description: Human-readable description of what the tool does.
            risk_default: Default risk level for this tool.
            **meta: Additional metadata.
        """
        if name in self._tools:
            logger.warning(f"Overwriting existing tool: {name}")

        self._tools[name] = fn
        self._metadata[name] = {
            "description": description,
            "risk_default": risk_default,
            **meta,
        }
        logger.debug(f"Registered tool: {name}")

    def get(self, name: str) -> Callable[..., Any] | None:
        """Look up a tool function by name.

        Args:
            name: The tool name to look up.

        Returns:
            The tool function, or None if not found.
        """
        return self._tools.get(name)

    def get_metadata(self, name: str) -> dict[str, Any]:
        """Get metadata for a registered tool.

        Args:
            name: The tool name.

        Returns:
            Metadata dict, or empty dict if tool not found.
        """
        return self._metadata.get(name, {})

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            Sorted list of tool names.
        """
        return sorted(self._tools.keys())

    def has(self, name: str) -> bool:
        """Check if a tool is registered.

        Args:
            name: The tool name to check.

        Returns:
            True if the tool is registered.
        """
        return name in self._tools

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: The tool name to remove.
        """
        self._tools.pop(name, None)
        self._metadata.pop(name, None)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def create_default_registry() -> ToolRegistry:
    """Create a registry with all built-in tools registered.

    Returns:
        A ToolRegistry with shell, file, and web tools registered.
    """
    from rewoo.tools.builtin.shell import shell_run
    from rewoo.tools.builtin.file import file_read, file_write, file_delete
    from rewoo.tools.builtin.web import web_search, web_scrape

    registry = ToolRegistry()

    registry.register(
        "shell.run",
        shell_run,
        description="Execute a shell command",
        risk_default="MEDIUM",
    )
    registry.register(
        "file.read",
        file_read,
        description="Read a file's contents",
        risk_default="LOW",
    )
    registry.register(
        "file.write",
        file_write,
        description="Write content to a file",
        risk_default="MEDIUM",
    )
    registry.register(
        "file.delete",
        file_delete,
        description="Delete a file",
        risk_default="HIGH",
    )
    registry.register(
        "web.search",
        web_search,
        description="Search the web for information",
        risk_default="LOW",
    )
    registry.register(
        "web.scrape",
        web_scrape,
        description="Scrape a web page's content",
        risk_default="LOW",
    )
    registry.register(
        "synthesize",
        lambda **kwargs: "",
        description="Internal step — no tool execution needed",
        risk_default="LOW",
    )

    return registry
