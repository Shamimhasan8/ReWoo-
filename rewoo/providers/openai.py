"""OpenAI and OpenRouter LLM provider."""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from rewoo.providers.base import BaseProvider, LLMResponse, Message

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI models and OpenRouter-compatible endpoints.

    Supports standard OpenAI models (gpt-4o, etc.) and OpenRouter models
    through the same OpenAI-compatible API interface. The base_url parameter
    is used to route requests to OpenRouter when needed.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
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
        self.client = AsyncOpenAI(**client_kwargs)

    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a completion using the OpenAI-compatible API.

        Formats messages into the OpenAI chat format, sends the request,
        and returns a normalized LLMResponse with token usage statistics.
        """
        formatted = self.format_messages(messages)

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": formatted,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            request_kwargs["stop"] = stop
        request_kwargs.update(kwargs)

        logger.debug(f"OpenAI request: model={self.model}, messages={len(formatted)}")

        response = await self.client.chat.completions.create(**request_kwargs)

        content = ""
        if response.choices and response.choices[0].message:
            content = response.choices[0].message.content or ""

        input_tokens = 0
        output_tokens = 0
        if response.usage:
            input_tokens = response.usage.prompt_tokens or 0
            output_tokens = response.usage.completion_tokens or 0

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            finish_reason=response.choices[0].finish_reason if response.choices else "",
            raw=response,
        )

    async def count_tokens(self, text: str) -> int:
        """Estimate token count. Uses rough heuristic (~4 chars per token)."""
        return max(1, len(text) // 4)
