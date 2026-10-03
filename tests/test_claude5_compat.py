"""Regression tests for tonight's live-usage defects (2026-08-24):

1. Tracked bytecode -- covered at the repo level (.gitignore + git index),
   not exercised by pytest.
2. Preflight must retry a transient error (e.g. Anthropic's 529
   overloaded_error) with backoff, and must never report it as a rejected
   model.
3. Claude 5-family models: no invented pricing for unpriced models,
   correct text-block extraction when a `thinking` block is present, and
   thinking is explicitly disabled for opus-5/sonnet-5/haiku-5 (but never
   for fable-5/mythos-5, which reject that outright).
4. Default model handling stays correct (covered by
   test_recent_model_compat.py; not duplicated here).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from click.testing import CliRunner

from advocate.cli import main
from advocate.provider import AnthropicProvider, estimate_cost, is_transient_error, model_error_hint
from advocate.models import PersonaReport, Persona, Review
from advocate.engine import review as run_review
from advocate.provider import LLMProvider


class _FakeStatusError(Exception):
    """Stand-in for an SDK APIStatusError subclass -- only the duck-typed
    `status_code` attribute that `is_transient_error` reads is real."""

    def __init__(self, status_code: int, message: str = "error") -> None:
        super().__init__(message)
        self.status_code = status_code


# ---- is_transient_error ----


def test_529_overloaded_is_transient() -> None:
    assert is_transient_error(_FakeStatusError(529, "overloaded_error")) is True


def test_429_rate_limit_is_transient() -> None:
    assert is_transient_error(_FakeStatusError(429)) is True


def test_5xx_is_transient() -> None:
    assert is_transient_error(_FakeStatusError(500)) is True
    assert is_transient_error(_FakeStatusError(503)) is True


def test_404_not_found_is_not_transient() -> None:
    assert is_transient_error(_FakeStatusError(404, "not_found_error")) is False


def test_400_bad_request_is_not_transient() -> None:
    assert is_transient_error(_FakeStatusError(400, "invalid_request_error")) is False


def test_error_without_status_code_is_not_transient() -> None:
    assert is_transient_error(RuntimeError("network blip")) is False


# ---- preflight retry behavior ----


class _FlakyThenOkProvider(LLMProvider):
    """Fails with a transient error N times, then succeeds."""

    def __init__(self, model: str, failures_before_success: int) -> None:
        super().__init__(model)
        self.remaining_failures = failures_before_success
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "test"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        self.call_count += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise _FakeStatusError(529, "overloaded_error")
        return "OK", 5, 1


class _AlwaysRejectedProvider(LLMProvider):
    """Fails with a genuine (non-transient) rejection every time."""

    def __init__(self, model: str) -> None:
        super().__init__(model)
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "test"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        self.call_count += 1
        raise _FakeStatusError(404, "not_found_error: model does not exist")


@pytest.mark.asyncio
async def test_preflight_retries_transient_error_then_succeeds() -> None:
    provider = _FlakyThenOkProvider("claude-opus-5", failures_before_success=2)
    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await provider.preflight()  # must not raise
    assert provider.call_count == 3
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
async def test_preflight_gives_up_after_repeated_transient_errors() -> None:
    provider = _FlakyThenOkProvider("claude-opus-5", failures_before_success=99)
    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(_FakeStatusError) as exc_info:
            await provider.preflight()
    assert exc_info.value.status_code == 529
    assert provider.call_count == 3  # bounded retries, not infinite


@pytest.mark.asyncio
async def test_preflight_does_not_retry_genuine_rejection() -> None:
    provider = _AlwaysRejectedProvider("claude-typo-model")
    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        with pytest.raises(_FakeStatusError) as exc_info:
            await provider.preflight()
    assert exc_info.value.status_code == 404
    assert provider.call_count == 1  # no retry for a genuine rejection
    mock_sleep.assert_not_awaited()


def test_model_error_hint_does_not_hardcode_a_specific_model_string() -> None:
    # The hint must reflect Advocate's own live default, not a literal that
    # can itself go stale/retired.
    from advocate.provider import _DEFAULTS

    hint = model_error_hint("anthropic", "claude-opus-4-6-fast")
    assert _DEFAULTS["anthropic"][1] in hint


def test_model_error_hint_distinct_from_overload_language() -> None:
    hint = model_error_hint("anthropic", "some-bad-model")
    assert "overloaded" not in hint.lower()


# ---- estimate_cost: Claude 5 priced at standard rates, no guessing ----


def test_estimate_cost_claude5_family_priced_at_standard_rates() -> None:
    # Standard (post-introductory) rates; Sonnet 5's intro rate lapsed
    # 2026-08-31. Behavior change from the earlier "report None for
    # Claude 5" stance, which predated a stable published price.
    assert estimate_cost("claude-opus-5", 1_000_000, 1_000_000) == 30.0
    assert estimate_cost("claude-sonnet-5", 1_000_000, 1_000_000) == 18.0
    assert estimate_cost("claude-fable-5", 1_000_000, 1_000_000) == 60.0


def test_estimate_cost_unknown_model_returns_none() -> None:
    assert estimate_cost("totally-unrecognized-model", 1000, 1000) is None


def test_estimate_cost_known_model_still_returns_a_number() -> None:
    cost = estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost is not None
    assert cost > 0


# ---- Claude 5 thinking-block parsing (not content[0].text) ----


@pytest.mark.asyncio
async def test_anthropic_provider_skips_leading_thinking_block() -> None:
    """A Claude 5-family response can return a `thinking` block before the
    `text` block. Reading content[0].text would break (no .text on a
    thinking block) or return reasoning instead of the answer -- the
    provider must extract only the text-type block(s)."""
    thinking_block = SimpleNamespace(type="thinking", thinking="reasoning about the answer...")
    text_block = SimpleNamespace(type="text", text='{"findings": []}')
    usage = SimpleNamespace(input_tokens=20, output_tokens=8)
    response = SimpleNamespace(content=[thinking_block, text_block], usage=usage)

    mock_client = Mock()
    mock_client.messages.create = AsyncMock(return_value=response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        text, in_tok, out_tok = await AnthropicProvider("claude-sonnet-5").complete(
            "system", "user", 4096
        )

    assert text == '{"findings": []}'
    assert in_tok == 20
    assert out_tok == 8


@pytest.mark.asyncio
async def test_anthropic_provider_disables_thinking_for_claude5_family() -> None:
    usage = SimpleNamespace(input_tokens=1, output_tokens=1)
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="OK")], usage=usage)
    mock_client = Mock()
    mock_client.messages.create = AsyncMock(return_value=response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await AnthropicProvider("claude-opus-5").complete("system", "user", 16)

    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs.get("thinking") == {"type": "disabled"}
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_anthropic_provider_leaves_thinking_untouched_for_non_claude5_models() -> None:
    usage = SimpleNamespace(input_tokens=1, output_tokens=1)
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="OK")], usage=usage)
    mock_client = Mock()
    mock_client.messages.create = AsyncMock(return_value=response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await AnthropicProvider("claude-sonnet-4-6").complete("system", "user", 16)

    kwargs = mock_client.messages.create.call_args.kwargs
    assert "thinking" not in kwargs
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_anthropic_provider_never_disables_thinking_for_fable_or_mythos() -> None:
    """Fable 5 / Mythos 5 return a 400 on an explicit thinking:disabled at
    any effort level -- must never send it for those models."""
    usage = SimpleNamespace(input_tokens=1, output_tokens=1)
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="OK")], usage=usage)
    mock_client = Mock()
    mock_client.messages.create = AsyncMock(return_value=response)

    for model in ("claude-fable-5", "claude-mythos-5"):
        mock_client.messages.create.reset_mock()
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            await AnthropicProvider(model).complete("system", "user", 16)
        kwargs = mock_client.messages.create.call_args.kwargs
        assert "thinking" not in kwargs, f"{model} must not get thinking:disabled"


# ---- engine/report aggregation with an unknown-cost persona ----


class _UnpricedModelProvider(LLMProvider):
    """Simulates a persona call against a model with no pricing entry."""

    @property
    def provider_name(self) -> str:
        return "test"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        return "[]", 10, 5


@pytest.mark.asyncio
async def test_review_aggregation_handles_unknown_persona_cost_without_crashing() -> None:
    result = await run_review(
        content="def f(): pass",
        target="example.py",
        target_type="file",
        llm=_UnpricedModelProvider("some-unpriced-model"),
        personas=[Persona.red_team],
    )

    assert result.persona_reports[0].estimated_cost_usd is None
    assert result.cost_partial is True
    assert result.total_cost_usd == 0.0  # known-cost sum; no known costs here


def test_review_defaults_to_not_partial() -> None:
    rev = Review(target="x", target_type="file")
    assert rev.cost_partial is False


# ---- CLI end-to-end: the exact defect from tonight's live usage ----
#
# Original report: `advocate review --model claude-opus-5 ...` hit a 529
# overloaded_error and printed "Model 'claude-opus-5' was rejected by
# Anthropic. Run with a current Claude model such as 'claude-sonnet-4-6'"
# -- wrong on both counts (transient overload, and a hardcoded suggestion
# that itself rots). These tests probe the CLI's actual stderr output.


class _InstantTransientProvider(LLMProvider):
    """Raises a transient error on the very first preflight() attempt,
    bypassing the base class's own retry/backoff so this test is fast and
    isolates the CLI's error-branching, not the retry loop (covered above)."""

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def preflight(self) -> None:
        raise _FakeStatusError(529, "overloaded_error")

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        raise AssertionError("should not be called; preflight must fail first")


class _InstantRejectionProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def preflight(self) -> None:
        raise _FakeStatusError(404, "not_found_error: model: claude-typo-999")

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        raise AssertionError("should not be called; preflight must fail first")


def test_cli_reports_overload_distinctly_from_model_rejection() -> None:
    import advocate.provider

    with patch.object(
        advocate.provider, "create_provider",
        lambda provider, model: _InstantTransientProvider("claude-opus-5"),
    ):
        result = CliRunner().invoke(main, ["review", "--stdin"], input="def f(): pass")

    assert result.exit_code == 2
    assert "overloaded, try again" in result.output
    assert "was rejected" not in result.output
    assert "REVIEW NOT STARTED: model preflight failed" not in result.output


def test_cli_reports_genuine_rejection_with_hint_not_overload_language() -> None:
    import advocate.provider

    with patch.object(
        advocate.provider, "create_provider",
        lambda provider, model: _InstantRejectionProvider("claude-typo-999"),
    ):
        result = CliRunner().invoke(main, ["review", "--stdin"], input="def f(): pass")

    assert result.exit_code == 2
    assert "REVIEW NOT STARTED: model preflight failed" in result.output
    assert "overloaded" not in result.output.lower()


# ---- Claude Opus 5.5: thinking always on, effort is the control ----


def _ok_client(stop_reason: str = "end_turn", text: str = "OK") -> Mock:
    usage = SimpleNamespace(input_tokens=1, output_tokens=1)
    content = [SimpleNamespace(type="text", text=text)] if text else []
    response = SimpleNamespace(content=content, usage=usage, stop_reason=stop_reason)
    mock_client = Mock()
    mock_client.messages.create = AsyncMock(return_value=response)
    return mock_client


@pytest.mark.asyncio
async def test_anthropic_provider_never_disables_thinking_for_opus_5_5() -> None:
    """Opus 5.5 returns a 400 for thinking:disabled at every effort level.
    The old pattern matched "claude-opus-5-5" and sent it."""
    mock_client = _ok_client()
    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await AnthropicProvider("claude-opus-5-5").complete("system", "user", 16384)
    kwargs = mock_client.messages.create.call_args.kwargs
    assert "thinking" not in kwargs
    assert kwargs.get("output_config") == {"effort": "medium"}
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_anthropic_provider_uses_low_effort_for_opus_5_5_small_requests() -> None:
    mock_client = _ok_client()
    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await AnthropicProvider("claude-opus-5-5").complete("system", "user", 16)
    kwargs = mock_client.messages.create.call_args.kwargs
    assert "thinking" not in kwargs
    assert kwargs.get("output_config") == {"effort": "low"}


@pytest.mark.asyncio
async def test_anthropic_provider_still_disables_thinking_for_opus_5() -> None:
    mock_client = _ok_client()
    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await AnthropicProvider("claude-opus-5").complete("system", "user", 16384)
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs.get("thinking") == {"type": "disabled"}
    assert "output_config" not in kwargs


@pytest.mark.asyncio
async def test_anthropic_provider_raises_when_budget_exhausted_without_text() -> None:
    """Thinking can consume all of max_tokens. That must surface as a clear
    persona failure, not as an empty response the JSON parser rejects."""
    mock_client = _ok_client(stop_reason="max_tokens", text="")
    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        with pytest.raises(RuntimeError, match="stop_reason=max_tokens"):
            await AnthropicProvider("claude-opus-5-5").complete("system", "user", 16384)


@pytest.mark.asyncio
async def test_anthropic_provider_small_request_tolerates_empty_text() -> None:
    """Preflight sends max_tokens=16 and ignores the text. An empty reply
    that hit max_tokens there must not read as a rejected model."""
    mock_client = _ok_client(stop_reason="max_tokens", text="")
    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        text, _, _ = await AnthropicProvider("claude-opus-5-5").complete("system", "user", 16)
    assert text == ""


def test_estimate_cost_prices_opus_5_5_on_its_own_rate() -> None:
    """Prefix matching used to price claude-opus-5-5 at Opus 5's rate."""
    assert estimate_cost("claude-opus-5-5", 1_000_000, 1_000_000) == 24.0
    assert estimate_cost("claude-opus-5", 1_000_000, 1_000_000) == 30.0
