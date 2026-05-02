"""LLM provider abstraction -- same pattern as webprobe but standalone."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from advocate.models import Persona


# ---- Approximate pricing (USD per 1M tokens) ----

_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (0.25, 1.25),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.15, 0.60),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    for key, (inp, out) in _PRICING.items():
        if model.startswith(key) or key.startswith(model):
            return (input_tokens * inp + output_tokens * out) / 1_000_000
    return (input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000


class LLMProvider(ABC):
    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        """Returns (response_text, input_tokens, output_tokens)."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...


class AnthropicProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        import anthropic
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text, response.usage.input_tokens, response.usage.output_tokens


class OpenAIProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
        usage = response.usage
        return (
            response.choices[0].message.content or "",
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )


class GeminiProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "gemini"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        from google import genai
        client = genai.Client()
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=[{"role": "user", "parts": [{"text": user}]}],
            config={"system_instruction": system, "max_output_tokens": max_tokens},
        )
        usage = response.usage_metadata
        return (
            response.text or "",
            usage.prompt_token_count if usage else 0,
            usage.candidates_token_count if usage else 0,
        )


_DEFAULTS: dict[str, tuple[type[LLMProvider], str]] = {
    "anthropic": (AnthropicProvider, "claude-sonnet-4-20250514"),
    "openai": (OpenAIProvider, "gpt-4o"),
    "gemini": (GeminiProvider, "gemini-2.5-flash"),
}


def create_provider(provider: str = "anthropic", model: str | None = None) -> LLMProvider:
    if provider not in _DEFAULTS:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(_DEFAULTS)}")
    cls, default_model = _DEFAULTS[provider]
    return cls(model=model or default_model)


async def transmogrify(text: str, model: str) -> str:
    """Normalize prompt register via transmogrifier if available."""
    try:
        from transmogrifier.core import Transmogrifier
        return Transmogrifier().translate(text, model=model).output_text
    except (ImportError, Exception):
        return text
