"""LLM provider abstraction -- same pattern as webprobe but standalone."""

from __future__ import annotations

import asyncio
import os
import re
from abc import ABC, abstractmethod


# ---- Approximate pricing (USD per 1M tokens) ----
#
# Claude 5 figures are the standard rates: Sonnet 5's time-limited
# introductory rate lapsed 2026-08-31, so the standard price is the one
# worth recording. `estimate_cost` still reports `None` (unknown) for any
# model absent here instead of guessing -- see the docstring below.

_PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
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

# Claude 5-tier models (opus-5, sonnet-5, haiku-5, ...) think by default.
# Advocate's personas expect a text/JSON-only response, and `max_tokens`
# caps thinking + text combined -- so a small `max_tokens` (e.g. the
# preflight's 16) could be entirely consumed by thinking, leaving zero
# response text. Disable thinking for these models to preserve the
# text-only contract. (Fable/Mythos are excluded: they reject an explicit
# `thinking: {"type": "disabled"}` outright, at any effort level.)
_CLAUDE_5_THINKING_DISABLE_RE = re.compile(r"^claude-(opus|sonnet|haiku)-5(-|$)")

# Claude Opus 5.5 thinks on every request. It returns a 400 for
# `thinking: {"type": "disabled"}` (and for a `budget_tokens` form) at every
# effort level, so the `thinking` field is omitted and `output_config.effort`
# is the only control. Thinking still counts toward `max_tokens`, so effort is
# kept at `medium` for review calls and `low` for tiny calls like preflight.
# Checked before the disable pattern, which would otherwise match
# "claude-opus-5-5".
_CLAUDE_THINKING_ALWAYS_ON_RE = re.compile(r"^claude-opus-5-5(-|$)")
_SMALL_REQUEST_MAX_TOKENS = 1024

# Status codes worth a short retry: 429 rate-limited, and any 5xx --
# including Anthropic's 529 overloaded_error. These mean "the API is
# busy," not "the model was rejected" (400/404 are never retried).
_TRANSIENT_STATUS_MIN = 500
_TRANSIENT_STATUS_MAX = 599

_RETIRED_MODEL_REPLACEMENTS: dict[str, str] = {
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    "claude-opus-4-20250514": "claude-opus-4-8",
    "claude-opus-4-1-20250805": "claude-opus-4-8",
    "claude-3-opus-20240229": "claude-opus-4-8",
    "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
    "claude-3-5-sonnet-20240620": "claude-sonnet-4-6",
    "claude-3-haiku-20240307": "claude-haiku-4-5",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5",
}

_ANTHROPIC_API_KEY_ENV_VARS = (
    "WANDER_ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY",
    "JMC_ANTHROPIC_API_KEY",
)


def _anthropic_api_key() -> str | None:
    """Resolve the Anthropic billing key, preferring the Wander account."""
    for name in _ANTHROPIC_API_KEY_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def _anthropic_base_url() -> str:
    """Resolve the Anthropic endpoint, ignoring ambient ANTHROPIC_BASE_URL.

    The surrounding shell often points ANTHROPIC_BASE_URL at a gateway
    (e.g. a coding-agent proxy) fronting a different account than the key
    `_anthropic_api_key` resolves; the gateway then 404s on models that
    key does have. The SDK reads that env var by default, so Advocate pins
    the public API explicitly. ADVOCATE_ANTHROPIC_BASE_URL is the
    deliberate opt-in for routing elsewhere.
    """
    return os.environ.get("ADVOCATE_ANTHROPIC_BASE_URL", "").strip() or _ANTHROPIC_BASE_URL


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate USD cost for a completion, or ``None`` if the model's price
    is not known.

    Never guesses: an unrecognized/unpriced model (e.g. a newly released
    one not yet in `_PRICING`) returns `None` rather than substituting
    another model's rate. Callers must treat `None` as "cost unknown" and
    display it as such -- silently reporting $0.00 or another model's
    price would be worse than admitting the gap.
    """
    # The longest key the model id starts with wins, so "claude-opus-5-5"
    # gets its own rate and not the rate of its prefix "claude-opus-5".
    # A key that starts with the model id (a short alias) is the fallback.
    forward = [k for k in _PRICING if model.startswith(k)]
    matches = forward or [k for k in _PRICING if k.startswith(model)]
    if not matches:
        return None
    inp, out = _PRICING[max(matches, key=len) if forward else matches[0]]
    return (input_tokens * inp + output_tokens * out) / 1_000_000


def model_error_hint(provider: str, model: str) -> str:
    """Return a concise operator hint for unavailable model failures.

    Points at Advocate's own current default and the override env vars
    rather than naming a specific alternate model: a hardcoded suggestion
    goes stale the moment that model is itself retired, which is exactly
    the failure this hint exists to avoid repeating.
    """
    replacement = _RETIRED_MODEL_REPLACEMENTS.get(model)
    env_vars = f"ADVOCATE_{provider.upper()}_MODEL or ADVOCATE_MODEL"
    if replacement:
        return (
            f"Model '{model}' is retired or unavailable. Try '{replacement}', "
            f"or set {env_vars}."
        )
    default_model = _DEFAULTS[provider][1] if provider in _DEFAULTS else None
    provider_label = provider.title() if provider != "openai" else "OpenAI"
    if default_model and default_model != model:
        return (
            f"Model '{model}' was rejected by {provider_label}. Try Advocate's "
            f"current default for this provider ('{default_model}'), or set "
            f"{env_vars} to a model your account has access to."
        )
    return (
        f"Model '{model}' was rejected by {provider_label}. Set {env_vars} to "
        f"a model your account currently has access to."
    )


def is_transient_error(exc: BaseException) -> bool:
    """True for a transient provider error (rate limit / server overload)
    that a short retry can plausibly recover from; false for a genuine
    rejection (bad request, invalid/unavailable model, auth failure) that
    retrying will not fix.

    A 529 `overloaded_error` is the case that mattered in practice: it is
    Anthropic saying "busy, try again," not "this model does not exist,"
    and must never be reported to the operator as the latter.
    """
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        return False
    return status == 429 or _TRANSIENT_STATUS_MIN <= status <= _TRANSIENT_STATUS_MAX


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
        """Fail fast if the configured model is unavailable.

        A transient error (rate limit, server overload -- e.g. Anthropic's
        529 `overloaded_error`) is retried with a short backoff rather than
        immediately reported as a rejected model: the two look identical
        from a bare exception message, but only one of them means the
        model name is wrong. A genuine rejection (400/404) is raised on
        the first attempt.
        """
        backoff_seconds = (1.0, 2.0)  # 3 attempts total
        for attempt in range(len(backoff_seconds) + 1):
            try:
                await self.complete(
                    "You are checking whether this model is available. Reply with OK only.",
                    "OK",
                    max_tokens=16,
                )
                return
            except Exception as exc:
                if attempt < len(backoff_seconds) and is_transient_error(exc):
                    await asyncio.sleep(backoff_seconds[attempt])
                    continue
                raise

    @property
    @abstractmethod
    def provider_name(self) -> str: ...


class AnthropicProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        import anthropic
        api_key = _anthropic_api_key()
        client_kwargs: dict[str, object] = {"base_url": _anthropic_base_url()}
        if api_key:
            client_kwargs["api_key"] = api_key
        client = anthropic.AsyncAnthropic(**client_kwargs)
        request: dict[str, object] = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # No `temperature` -- Claude 5-family models reject it outright, and
        # Advocate never relied on sampling variance to begin with.
        if _CLAUDE_THINKING_ALWAYS_ON_RE.match(self.model):
            effort = "low" if max_tokens < _SMALL_REQUEST_MAX_TOKENS else "medium"
            request["output_config"] = {"effort": effort}
        elif _CLAUDE_5_THINKING_DISABLE_RE.match(self.model):
            request["thinking"] = {"type": "disabled"}
        response = await client.messages.create(**request)
        # Only "text"-type blocks are joined. Claude 5-family models think
        # by default and can return a leading `thinking` block ahead of the
        # `text` block(s); `content[0].text` would break here (a thinking
        # block has no `.text`). Filtering by type -- not by index -- reads
        # correctly whether or not thinking is present.
        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", "text") == "text" and getattr(block, "text", None)
        )
        usage = response.usage
        if (
            not text
            and max_tokens >= _SMALL_REQUEST_MAX_TOKENS
            and getattr(response, "stop_reason", None) == "max_tokens"
        ):
            # Thinking can spend the whole budget before any text is written.
            # Fail loudly so the persona is reported as failed with the cause,
            # not as an unparseable empty response. Small requests (preflight)
            # are exempt: they only prove the model answers, and a reply with
            # no text is still an answer.
            raise RuntimeError(
                f"{self.model} used all {max_tokens} output tokens without "
                "writing a response (stop_reason=max_tokens); thinking likely "
                "consumed the budget"
            )
        return text, _token_count(usage.input_tokens), _token_count(usage.output_tokens)


class OpenAIProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        reasoning_effort = os.environ.get("OPENAI_REASONING_EFFORT", "").strip()

        if hasattr(client, "responses"):
            request = dict(
                model=self.model,
                instructions=system,
                input=user,
                max_output_tokens=max(16, max_tokens),
            )
            # Keep this provider-specific control opt-in. Ollama reasoning
            # models may otherwise spend the completion budget without
            # emitting output text, while generic compatible servers may not
            # accept the field at all.
            if reasoning_effort:
                request["reasoning"] = {"effort": reasoning_effort}
            response = await client.responses.create(**request)
            usage = getattr(response, "usage", None)
            return (
                _response_output_text(response),
                _token_count(getattr(usage, "input_tokens", None)),
                _token_count(getattr(usage, "output_tokens", None)),
            )

        request = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
        if reasoning_effort:
            request["reasoning_effort"] = reasoning_effort
        response = await client.chat.completions.create(**request)
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
    "anthropic": (AnthropicProvider, "claude-opus-5"),
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
