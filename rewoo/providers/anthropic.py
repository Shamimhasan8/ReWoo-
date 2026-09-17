"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from rewoo.providers.base import BaseProvider, LLMResponse, Message

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic's Claude models."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, api_key=api_key, **kwargs)
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = anthropic.AsyncAnthropic(**client_kwargs)

    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a completion using Anthropic's Claude API.

        Separates system messages from conversation messages as required by the
        Anthropic API format, then sends the request and parses the response.
        """
        # Separate system message from conversation
        system_content = ""
        conversation: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation.append({"role": msg.role, "content": msg.content})

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_content:
            request_kwargs["system"] = system_content
        if stop:
            request_kwargs["stop_sequences"] = stop
        request_kwargs.update(kwargs)

        logger.debug(f"Anthropic request: model={self.model}, messages={len(conversation)}")

        response = await self.client.messages.create(**request_kwargs)

        content = ""
        if response.content:
            content = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        input_tokens = getattr(response.usage, "input_tokens", 0) or 0
        output_tokens = getattr(response.usage, "output_tokens", 0) or 0

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            finish_reason=response.stop_reason or "",
            raw=response,
        )

    async def count_tokens(self, text: str) -> int:
        """Estimate token count. Uses rough heuristic (~4 chars per token)."""
        return max(1, len(text) // 4)
