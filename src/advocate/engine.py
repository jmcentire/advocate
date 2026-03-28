"""Review engine -- runs all six personas against input, detects disagreements."""

from __future__ import annotations

import asyncio
import json
import logging
import re
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

logger = logging.getLogger("advocate")


def _sanitize_content_for_prompt(content: str) -> str:
    """Strip prompt injection patterns from user content before embedding in prompts."""
    sanitized = re.sub(
        r'(?i)(ignore|disregard|forget)\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)',
        '[CONTENT_REDACTED]', content)
    sanitized = re.sub(r'(?i)you\s+are\s+now\s+', '[CONTENT_REDACTED]', sanitized)
    sanitized = re.sub(r'(?i)system\s*:\s*', '[CONTENT_REDACTED]', sanitized)
    return sanitized


def _parse_findings_json(text: str) -> tuple[list[dict], str]:
    """Robustly extract JSON findings array from LLM response.

    Returns (parsed_items, summary_text). On failure returns ([], full_text).
    """
    text = text.strip()

    # Try markdown code block first
    for block in re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL):
        try:
            items = json.loads(block.strip())
            if isinstance(items, list):
                remainder = text.replace(f"```json\n{block}\n```", "").replace(f"```\n{block}\n```", "").strip()
                return items, remainder
        except json.JSONDecodeError:
            continue

    # Try finding [ ... ] with bracket matching
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '[':
            if depth == 0:
                start = i
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    items = json.loads(text[start:i + 1])
                    if isinstance(items, list):
                        summary = text[i + 1:].strip()
                        return items, summary
                except json.JSONDecodeError:
                    start = -1

    return [], text


async def _run_persona(
    persona: Persona,
    llm: LLMProvider,
    content: str,
    target_description: str,
) -> PersonaReport:
    """Run a single persona's review."""
    meta = PERSONA_META[persona]
    system = SYSTEM_PROMPTS[persona]

    # Sanitize user content before embedding in prompt
    safe_content = _sanitize_content_for_prompt(content)

    user_prompt = f"""Review the following. You are the {meta['name']}. {meta['tagline']}

**Target**: {target_description}

---

{safe_content}

---

Apply your perspective. Your assigned dimensions: {', '.join(d.value for d in meta['dimensions'])}.
Your success criterion: {meta['success']}"""

    user_prompt = await transmogrify(user_prompt, llm.model)

    start = time.monotonic()
    try:
        response, in_tokens, out_tokens = await llm.complete(system, user_prompt)
    except Exception as e:
        logger.error("Persona %s failed: %s", persona.value, e)
        return PersonaReport(
            persona=persona,
            summary=f"Error: {e}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    duration = (time.monotonic() - start) * 1000

    # Parse findings with robust extraction
    findings: list[Finding] = []
    items, summary = _parse_findings_json(response)

    sev_map = {s.value: s for s in Severity}
    dim_map = {d.value: d for d in Dimension}

    parse_failed = False
    if not items and response.strip():
        parse_failed = True
        logger.warning("Persona %s: JSON parsing failed, raw response preserved in summary", persona.value)

    for item in items:
        if not isinstance(item, dict):
            continue
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

    if parse_failed:
        summary = f"[PARSE_FAILED] Raw response:\n{response[:500]}"

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
    """Find cases where personas disagree -- this is valuable signal."""
    disagreements: list[Disagreement] = []

    for i, report_a in enumerate(reports):
        for report_b in reports[i + 1:]:
            for finding_a in report_a.findings:
                for finding_b in report_b.findings:
                    if not finding_a.title or not finding_b.title:
                        continue
                    title_overlap = _word_overlap(finding_a.title, finding_b.title)
                    if title_overlap < 0.3:
                        continue

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

    return disagreements


def _word_overlap(a: str, b: str) -> float:
    """Simple word-level Jaccard similarity."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


async def review(
    content: str,
    target: str,
    target_type: str,
    llm: LLMProvider,
    personas: list[Persona] | None = None,
    parallel: bool = True,
) -> Review:
    """Run an Advocate review."""
    if personas is None:
        personas = list(Persona)

    rev = Review(
        target=target,
        target_type=target_type,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    if parallel:
        tasks = [_run_persona(p, llm, content, target) for p in personas]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, PersonaReport):
                rev.persona_reports.append(result)
            elif isinstance(result, Exception):
                # Don't silently drop failures (Adversarial fix)
                logger.error("Persona %s raised exception: %s", personas[i].value, result)
                rev.persona_reports.append(PersonaReport(
                    persona=personas[i],
                    summary=f"Error: {result}",
                ))
    else:
        for p in personas:
            report = await _run_persona(p, llm, content, target)
            rev.persona_reports.append(report)

    rev.disagreements = _detect_disagreements(rev.persona_reports)
    rev.total_findings = sum(len(r.findings) for r in rev.persona_reports)
    rev.total_cost_usd = sum(r.estimated_cost_usd for r in rev.persona_reports)
    rev.completed_at = datetime.now(timezone.utc).isoformat()

    return rev


def _is_binary(path: Path) -> bool:
    """Check if a file is binary by looking for null bytes."""
    try:
        chunk = path.read_bytes()[:1024]
        return b'\x00' in chunk
    except Exception:
        return True


def load_input(path: str) -> tuple[str, str, str]:
    """Load review input from a path. Returns (content, target, target_type)."""
    p = Path(path).resolve()
    if p.is_dir():
        parts = []
        skipped: list[str] = []
        extensions = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java",
                      ".md", ".yaml", ".yml", ".toml", ".json"}
        for f in sorted(p.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix not in extensions:
                continue
            if ".git" in f.parts or "__pycache__" in f.parts or "node_modules" in f.parts:
                continue
            # Path traversal protection: ensure resolved path is under base dir
            try:
                f.resolve().relative_to(p)
            except ValueError:
                skipped.append(str(f))
                continue
            if _is_binary(f):
                skipped.append(str(f))
                continue
            try:
                text = f.read_text(encoding="utf-8")
                parts.append(f"--- {f.relative_to(p)} ---\n{text}\n")
            except (UnicodeDecodeError, PermissionError) as e:
                skipped.append(f"{f}: {e}")
                continue
        if skipped:
            logger.info("Skipped %d files: %s", len(skipped), ", ".join(skipped[:5]))
        if not parts:
            raise ValueError(f"No source files found in {p}. Supported: {', '.join(sorted(extensions))}")
        return "\n".join(parts), str(p), "directory"
    elif p.is_file():
        if _is_binary(p):
            raise ValueError(f"Binary file not supported: {p}")
        try:
            return p.read_text(encoding="utf-8"), str(p), "file"
        except UnicodeDecodeError:
            raise ValueError(f"File encoding error: {p}. Only UTF-8 is supported.")
    else:
        raise FileNotFoundError(f"Not found: {path}")
