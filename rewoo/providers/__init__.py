"""LLM provider abstractions."""

from rewoo.providers.base import BaseProvider, LLMResponse, Message
from rewoo.providers.openai import OpenAIProvider

# Conditionally import anthropic to avoid hard dependency at import time
try:
    from rewoo.providers.anthropic import AnthropicProvider
except ImportError:
    AnthropicProvider = None  # type: ignore[assignment,misc]

__all__ = [
    "BaseProvider",
    "LLMResponse",
    "Message",
    "AnthropicProvider",
    "OpenAIProvider",
]
