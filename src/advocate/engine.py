"""Review engine -- runs all six personas against input, detects disagreements."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from advocate.models import (
    Dimension,
    Disagreement,
    Finding,
    Persona,
    PersonaReport,
    Review,
    Severity,
)
from advocate.personas import PERSONA_META, SYSTEM_PROMPTS
from advocate.provider import LLMProvider, estimate_cost, transmogrify


async def _run_persona(
    persona: Persona,
    llm: LLMProvider,
    content: str,
    target_description: str,
) -> PersonaReport:
    """Run a single persona's review."""
    meta = PERSONA_META[persona]
    system = SYSTEM_PROMPTS[persona]

    user_prompt = f"""Review the following. You are the {meta['name']}. {meta['tagline']}

**Target**: {target_description}

---

{content}

---

Apply your perspective. Your assigned dimensions: {', '.join(d.value for d in meta['dimensions'])}.
Your success criterion: {meta['success']}"""

    user_prompt = await transmogrify(user_prompt, llm.model)

    start = time.monotonic()
    try:
        response, in_tokens, out_tokens = await llm.complete(system, user_prompt)
    except Exception as e:
        return PersonaReport(
            persona=persona,
            summary=f"Error: {e}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    duration = (time.monotonic() - start) * 1000

    # Parse findings from JSON
    findings: list[Finding] = []
    summary = ""

    try:
        # Extract JSON array from response (may have surrounding text)
        text = response.strip()
        json_start = text.index("[")
        json_end = text.rindex("]") + 1
        items = json.loads(text[json_start:json_end])
        # Everything after the JSON is the summary
        summary = text[json_end:].strip()

        sev_map = {s.value: s for s in Severity}
        dim_map = {d.value: d for d in Dimension}

        for item in items:
            sev = sev_map.get(item.get("severity", "medium"), Severity.medium)
            dim = dim_map.get(item.get("dimension", "concept"), Dimension.concept)
            findings.append(Finding(
                persona=persona,
                severity=sev,
                dimension=dim,
                title=item.get("title", "Untitled finding"),
                detail=item.get("detail", ""),
                evidence=item.get("evidence", ""),
                recommendation=item.get("recommendation", ""),
            ))
    except (ValueError, json.JSONDecodeError):
        # If JSON parsing fails, treat entire response as summary
        summary = response

    return PersonaReport(
        persona=persona,
        findings=findings,
        summary=summary,
        duration_ms=duration,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        estimated_cost_usd=estimate_cost(llm.model, in_tokens, out_tokens),
    )


def _detect_disagreements(reports: list[PersonaReport]) -> list[Disagreement]:
    """Find cases where personas disagree -- this is valuable signal.

    Disagreements happen when:
    - One persona flags something as a problem, another's logic implies it's fine
    - Two personas flag the same thing but with contradictory recommendations
    - The Sage says "simplify" but the SME says "this complexity is necessary"
    """
    disagreements: list[Disagreement] = []

    # Compare all pairs of personas
    for i, report_a in enumerate(reports):
        for report_b in reports[i + 1:]:
            for finding_a in report_a.findings:
                for finding_b in report_b.findings:
                    # Same topic, different conclusions
                    title_overlap = _word_overlap(finding_a.title, finding_b.title)
                    if title_overlap < 0.3:
                        continue

                    # Different severity = disagreement on importance
                    sev_a = list(Severity).index(finding_a.severity)
                    sev_b = list(Severity).index(finding_b.severity)
                    if abs(sev_a - sev_b) >= 2:
                        disagreements.append(Disagreement(
                            finding_a=finding_a,
                            finding_b=finding_b,
                            tension=f"{PERSONA_META[finding_a.persona]['name']} rates this "
                                    f"{finding_a.severity.value}, but "
                                    f"{PERSONA_META[finding_b.persona]['name']} rates it "
                                    f"{finding_b.severity.value}. The gap suggests different "
                                    f"risk models worth examining.",
                        ))

                    # Contradictory recommendations
                    if (finding_a.recommendation and finding_b.recommendation and
                            _sentiment_contradicts(finding_a.recommendation, finding_b.recommendation)):
                        disagreements.append(Disagreement(
                            finding_a=finding_a,
                            finding_b=finding_b,
                            tension=f"{PERSONA_META[finding_a.persona]['name']} recommends "
                                    f"'{finding_a.recommendation[:60]}' while "
                                    f"{PERSONA_META[finding_b.persona]['name']} recommends "
                                    f"'{finding_b.recommendation[:60]}'. Tension worth resolving.",
                        ))

    return disagreements


def _word_overlap(a: str, b: str) -> float:
    """Simple word-level Jaccard similarity."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _sentiment_contradicts(a: str, b: str) -> bool:
    """Rough heuristic: do two recommendations point in opposite directions?"""
    add_words = {"add", "include", "implement", "create", "enable", "increase", "more", "expand"}
    remove_words = {"remove", "delete", "simplify", "reduce", "disable", "less", "eliminate", "drop"}
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    a_adds = bool(words_a & add_words)
    a_removes = bool(words_a & remove_words)
    b_adds = bool(words_b & add_words)
    b_removes = bool(words_b & remove_words)
    return (a_adds and b_removes) or (a_removes and b_adds)


async def review(
    content: str,
    target: str,
    target_type: str,
    llm: LLMProvider,
    personas: list[Persona] | None = None,
    parallel: bool = True,
) -> Review:
    """Run an Advocate review.

    All six personas run by default. Set parallel=True (default) to run them
    concurrently -- 6 simultaneous LLM calls.
    """
    if personas is None:
        personas = list(Persona)

    rev = Review(
        target=target,
        target_type=target_type,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    if parallel:
        tasks = [_run_persona(p, llm, content, target) for p in personas]
        reports = await asyncio.gather(*tasks, return_exceptions=True)
        for result in reports:
            if isinstance(result, PersonaReport):
                rev.persona_reports.append(result)
    else:
        for p in personas:
            report = await _run_persona(p, llm, content, target)
            rev.persona_reports.append(report)

    # Detect disagreements
    rev.disagreements = _detect_disagreements(rev.persona_reports)

    # Totals
    rev.total_findings = sum(len(r.findings) for r in rev.persona_reports)
    rev.total_cost_usd = sum(r.estimated_cost_usd for r in rev.persona_reports)
    rev.completed_at = datetime.now(timezone.utc).isoformat()

    return rev


def load_input(path: str) -> tuple[str, str, str]:
    """Load review input from a path. Returns (content, target, target_type)."""
    p = Path(path)
    if p.is_dir():
        # Concatenate all source files
        parts = []
        extensions = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java",
                      ".md", ".yaml", ".yml", ".toml", ".json"}
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix in extensions and ".git" not in f.parts:
                try:
                    text = f.read_text(errors="replace")
                    parts.append(f"--- {f.relative_to(p)} ---\n{text}\n")
                except Exception:
                    continue
        return "\n".join(parts), str(p), "directory"
    elif p.is_file():
        return p.read_text(errors="replace"), str(p), "file"
    else:
        raise FileNotFoundError(f"Not found: {path}")
