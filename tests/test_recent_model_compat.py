from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import json

import pytest
from click.testing import CliRunner

from advocate.cli import main
from advocate.engine import review as run_review
from advocate.models import Dimension, Persona, PersonaReport, Review, Severity
from advocate.provider import LLMProvider, OpenAIProvider, create_provider
from advocate.report import print_review


def test_anthropic_default_uses_current_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADVOCATE_MODEL", raising=False)
    monkeypatch.delenv("ADVOCATE_ANTHROPIC_MODEL", raising=False)

    provider = create_provider("anthropic")

    assert provider.model == "claude-sonnet-4-6"


def test_model_env_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADVOCATE_MODEL", "generic-model")
    monkeypatch.setenv("ADVOCATE_ANTHROPIC_MODEL", "anthropic-model")

    assert create_provider("anthropic").model == "anthropic-model"
    assert create_provider("anthropic", "explicit-model").model == "explicit-model"


@pytest.mark.asyncio
async def test_openai_provider_uses_responses_api_for_recent_models() -> None:
    usage = SimpleNamespace(input_tokens=11, output_tokens=7)
    response = SimpleNamespace(output_text="ok", usage=usage)
    mock_client = Mock()
    mock_client.responses.create = AsyncMock(return_value=response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        text, input_tokens, output_tokens = await OpenAIProvider("gpt-5.4-mini").complete(
            "system prompt",
            "user prompt",
            128,
        )

    assert text == "ok"
    assert input_tokens == 11
    assert output_tokens == 7
    mock_client.responses.create.assert_awaited_once_with(
        model="gpt-5.4-mini",
        instructions="system prompt",
        input="user prompt",
        max_output_tokens=128,
    )


class FailingProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "test"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        raise RuntimeError("model 404")


class EmptyFindingsProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "test"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        return "```json\n[]\n```\nSummary: no issues found.", 10, 5


class ShapeDriftProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "test"

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        findings = [
            {
                "severity": "HIGH",
                "dimension": "failure-modes",
                "title": {"nested": "dict title"},
                "detail": ["list", "detail"],
                "evidence": {"line": 12},
                "recommendation": None,
            },
            "not-json",
            {
                "severity": 123,
                "dimension": None,
                "title": 42,
                "detail": True,
            },
        ]
        return json.dumps(json.dumps(findings)), 10, 5


@pytest.mark.asyncio
async def test_review_marks_persona_provider_failures_incomplete() -> None:
    result = await run_review(
        content="def f(): pass",
        target="example.py",
        target_type="file",
        llm=FailingProvider("retired-model"),
        personas=[Persona.red_team],
    )

    assert result.total_findings == 0
    assert not result.is_complete()
    assert result.failed_reports()[0].error == "model 404"


@pytest.mark.asyncio
async def test_valid_empty_findings_json_is_not_parse_failure() -> None:
    result = await run_review(
        content="def f(): pass",
        target="example.py",
        target_type="file",
        llm=EmptyFindingsProvider("current-model"),
        personas=[Persona.good_friend],
    )

    assert result.total_findings == 0
    assert result.is_complete()
    assert result.persona_reports[0].error is None
    assert "PARSE_FAILED" not in result.persona_reports[0].summary


@pytest.mark.asyncio
async def test_stringified_and_misshapen_findings_are_coerced_per_item() -> None:
    result = await run_review(
        content="def f(): pass",
        target="example.py",
        target_type="file",
        llm=ShapeDriftProvider("current-model"),
        personas=[Persona.red_team],
    )

    assert result.is_complete()
    assert result.total_findings == 2
    first, second = result.all_findings()
    assert first.severity == Severity.high
    assert first.dimension == Dimension.failure_modes
    assert "dict title" in first.title
    assert "list" in first.detail
    assert "line" in first.evidence
    assert second.severity == Severity.medium
    assert second.dimension == Dimension.concept
    assert second.title == "42"
    assert second.detail == "True"


def test_print_review_does_not_render_failed_persona_as_positive(capsys: pytest.CaptureFixture[str]) -> None:
    result = Review(
        target="example.py",
        target_type="file",
        persona_reports=[
            PersonaReport(
                persona=Persona.red_team,
                ok=False,
                error="model 404",
                summary="FAILED: model 404",
            )
        ],
    )

    print_review(result, color=False)

    output = capsys.readouterr().out
    assert "REVIEW INCOMPLETE: 1/1 personas failed" in output
    assert "PERSONA FAILED: model 404" in output
    assert "strong positive signal" not in output


def test_cli_exits_nonzero_when_review_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    import advocate.engine
    import advocate.provider
    import advocate.report

    class DummyProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return "test"

        async def preflight(self) -> None:
            return None

        async def complete(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
            return "", 0, 0

    async def fake_review(**kwargs: object) -> Review:
        return Review(
            target="<stdin>",
            target_type="stdin",
            persona_reports=[
                PersonaReport(
                    persona=Persona.red_team,
                    ok=False,
                    error="model 404",
                    summary="FAILED: model 404",
                )
            ],
        )

    monkeypatch.setattr(advocate.provider, "create_provider", lambda provider, model: DummyProvider("dummy"))
    monkeypatch.setattr(advocate.engine, "review", fake_review)
    monkeypatch.setattr(advocate.report, "print_review", lambda review, color=True: None)

    result = CliRunner().invoke(main, ["review", "--stdin", "-p", "red_team"], input="content")

    assert result.exit_code == 2
    assert "REVIEW INCOMPLETE: 1/1 personas failed" in result.output
