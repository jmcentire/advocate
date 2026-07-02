"""LLM provider abstraction -- same pattern as webprobe but standalone."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


# ---- Approximate pricing (USD per 1M tokens) ----

_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (0.25, 1.25),
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.15, 0.90),
    "gpt-5.4": (2.5, 15.0),
    "gpt-5": (1.25, 10.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.15, 0.60),
}

_RETIRED_MODEL_REPLACEMENTS: dict[str, str] = {
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    "claude-opus-4-20250514": "claude-opus-4-8",
    "claude-opus-4-1-20250805": "claude-opus-4-8",
    "claude-3-opus-20240229": "claude-opus-4-8",
    "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
    "claude-3-5-sonnet-20240620": "claude-sonnet-4-6",
    "claude-3-haiku-20240307": "claude-haiku-4-5-20251001",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5-20251001",
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    for key, (inp, out) in _PRICING.items():
        if model.startswith(key) or key.startswith(model):
            return (input_tokens * inp + output_tokens * out) / 1_000_000
    return (input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000


def model_error_hint(provider: str, model: str) -> str:
    """Return a concise operator hint for unavailable model failures."""
    replacement = _RETIRED_MODEL_REPLACEMENTS.get(model)
    env_vars = f"ADVOCATE_{provider.upper()}_MODEL or ADVOCATE_MODEL"
    if replacement:
        return (
            f"Model '{model}' is retired or unavailable. Try '{replacement}', "
            f"or set {env_vars}."
        )
    if provider == "anthropic":
        return (
            f"Model '{model}' was rejected by Anthropic. Run with a current "
            f"Claude model such as 'claude-sonnet-4-6', or set {env_vars}."
        )
    if provider == "openai":
        return (
            f"Model '{model}' was rejected by OpenAI. Use a Responses API model "
            f"such as 'gpt-5.4-mini' or 'gpt-5.5', or set {env_vars}."
        )
    return f"Model '{model}' was rejected. Set {env_vars} to a current model."


def _token_count(value: object) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _response_output_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                parts.append(text)
            elif isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "".join(parts)


class LLMProvider(ABC):
    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        """Returns (response_text, input_tokens, output_tokens)."""

    async def preflight(self) -> None:
        """Fail fast if the configured model is unavailable."""
        await self.complete(
            "You are checking whether this model is available. Reply with OK only.",
            "OK",
            max_tokens=16,
        )

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
        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", "text") == "text" and getattr(block, "text", None)
        )
        usage = response.usage
        return text, _token_count(usage.input_tokens), _token_count(usage.output_tokens)


class OpenAIProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()

        if hasattr(client, "responses"):
            response = await client.responses.create(
                model=self.model,
                instructions=system,
                input=user,
                max_output_tokens=max(16, max_tokens),
            )
            usage = getattr(response, "usage", None)
            return (
                _response_output_text(response),
                _token_count(getattr(usage, "input_tokens", None)),
                _token_count(getattr(usage, "output_tokens", None)),
            )

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
            _token_count(getattr(usage, "prompt_tokens", None)) if usage else 0,
            _token_count(getattr(usage, "completion_tokens", None)) if usage else 0,
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
            _token_count(getattr(usage, "prompt_token_count", None)) if usage else 0,
            _token_count(getattr(usage, "candidates_token_count", None)) if usage else 0,
        )


_DEFAULTS: dict[str, tuple[type[LLMProvider], str]] = {
    "anthropic": (AnthropicProvider, "claude-sonnet-4-6"),
    "openai": (OpenAIProvider, "gpt-5.4-mini"),
    "gemini": (GeminiProvider, "gemini-2.5-flash"),
}


def create_provider(provider: str = "anthropic", model: str | None = None) -> LLMProvider:
    if provider not in _DEFAULTS:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(_DEFAULTS)}")
    cls, default_model = _DEFAULTS[provider]
    resolved_model = (
        model
        or os.getenv(f"ADVOCATE_{provider.upper()}_MODEL")
        or os.getenv("ADVOCATE_MODEL")
        or default_model
    )
    return cls(model=resolved_model)


async def transmogrify(text: str, model: str) -> str:
    """Normalize prompt register via transmogrifier if available."""
    try:
        from transmogrifier.core import Transmogrifier
        return Transmogrifier().translate(text, model=model).output_text
    except (ImportError, Exception):
        return text
