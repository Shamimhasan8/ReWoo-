"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    raw: Any = None

    @property
    def total_tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseProvider(ABC):
    """Abstract base class that all LLM providers must implement."""

    def __init__(self, model: str, api_key: str | None = None, **kwargs: Any) -> None:
        self.model = model
        self.api_key = api_key
        self.kwargs = kwargs

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a completion from the LLM.

        Args:
            messages: List of conversation messages.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            stop: Optional stop sequences.

        Returns:
            LLMResponse with the generated content and usage stats.
        """
        ...

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """Estimate the token count for a given text.

        Args:
            text: The text to count tokens for.

        Returns:
            Estimated token count.
        """
        ...

    def format_messages(self, messages: list[Message]) -> list[dict[str, str]]:
        """Convert Message objects to dict format.

        Args:
            messages: List of Message objects.

        Returns:
            List of dicts with 'role' and 'content' keys.
        """
        return [{"role": m.role, "content": m.content} for m in messages]
