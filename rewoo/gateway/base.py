"""Abstract gateway interface for multi-channel input.

Gateways handle the interface between the user and the ReWoo agent.
The CLI gateway is the default, but the architecture supports adding
Telegram, Discord, WhatsApp, and other channels in the future.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from rewoo.core.types import ExecutionResult


class BaseGateway(ABC):
    """Abstract base class for gateway implementations.

    Gateways are responsible for:
    1. Receiving user input (tasks, commands)
    2. Displaying execution plans and progress
    3. Collecting approval decisions
    4. Presenting final results
    """

    @abstractmethod
    async def receive_task(self) -> str:
        """Receive a task from the user.

        Returns:
            The task description entered by the user.
        """
        ...

    @abstractmethod
    async def display_plan(self, plan: Any) -> None:
        """Display an execution plan to the user.

        Args:
            plan: The execution plan to display.
        """
        ...

    @abstractmethod
    async def display_result(self, result: ExecutionResult) -> None:
        """Display the final execution result to the user.

        Args:
            result: The execution result to display.
        """
        ...

    @abstractmethod
    async def display_error(self, error: str) -> None:
        """Display an error message to the user.

        Args:
            error: The error message to display.
        """
        ...
