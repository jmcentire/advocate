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
from pydantic import ValidationError

logger = logging.getLogger("advocate")


def _sanitize_content_for_prompt(content: str) -> str:
    """Strip prompt injection patterns from user content before embedding in prompts."""
    sanitized = re.sub(
        r'(?i)(ignore|disregard|forget)\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)',
        '[CONTENT_REDACTED]', content)
    sanitized = re.sub(r'(?i)you\s+are\s+now\s+', '[CONTENT_REDACTED]', sanitized)
    sanitized = re.sub(r'(?i)system\s*:\s*', '[CONTENT_REDACTED]', sanitized)
    return sanitized


def _coerce_findings_array(value: object) -> list[object] | None:
    if isinstance(value, str):
        try:
            return _coerce_findings_array(json.loads(value))
        except json.JSONDecodeError:
            return None
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("findings"), list):
        return value["findings"]
    return None


def _string_field(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _coerce_enum_value(enum_type, value: object, default):
    if isinstance(value, enum_type):
        return value
    normalized = _string_field(value).strip().lower().replace("-", "_").replace(" ", "_")
    for member in enum_type:
        if normalized in {member.name.lower(), str(member.value).lower()}:
            return member
    return default


def _parse_findings_json_result(text: str) -> tuple[list[object], str, bool]:
    """Robustly extract JSON findings array from LLM response.

    Returns (parsed_items, summary_text, parsed_ok).
    """
    text = text.strip()

    try:
        items = _coerce_findings_array(json.loads(text))
        if items is not None:
            return items, "", True
    except json.JSONDecodeError:
        pass

    # Try markdown code block first
    for match in re.finditer(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL):
        block = match.group(1)
        try:
            items = _coerce_findings_array(json.loads(block.strip()))
            if items is not None:
                remainder = (text[:match.start()] + text[match.end():]).strip()
                return items, remainder, True
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
                    items = _coerce_findings_array(json.loads(text[start:i + 1]))
                    if items is not None:
                        summary = text[i + 1:].strip()
                        return items, summary, True
                except json.JSONDecodeError:
                    start = -1

    return [], text, False


def _parse_findings_json(text: str) -> tuple[list[object], str]:
    """Return (parsed_items, summary_text). On failure returns ([], full_text)."""
    items, summary, _ = _parse_findings_json_result(text)
    return items, summary


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
            summary=f"FAILED: {e}",
            ok=False,
            error=str(e),
            duration_ms=(time.monotonic() - start) * 1000,
        )
    duration = (time.monotonic() - start) * 1000

    # Parse findings with robust extraction
    findings: list[Finding] = []
    items, summary, parsed_ok = _parse_findings_json_result(response)

    parse_failed = not parsed_ok
    if parse_failed:
        logger.warning("Persona %s: JSON parsing failed, raw response preserved in summary", persona.value)

    for item in items:
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except json.JSONDecodeError:
                logger.warning("Persona %s: skipping string finding that is not JSON", persona.value)
                continue
        if not isinstance(item, dict):
            logger.warning("Persona %s: skipping non-object finding: %r", persona.value, item)
            continue
        sev = _coerce_enum_value(Severity, item.get("severity", "medium"), Severity.medium)
        dim = _coerce_enum_value(Dimension, item.get("dimension", "concept"), Dimension.concept)
        try:
            findings.append(Finding(
                persona=persona,
                severity=sev,
                dimension=dim,
                title=_string_field(item.get("title")) or "Untitled finding",
                detail=_string_field(item.get("detail")),
                evidence=_string_field(item.get("evidence")),
                recommendation=_string_field(item.get("recommendation")),
            ))
        except ValidationError as exc:
            logger.warning("Persona %s: skipping invalid finding: %s", persona.value, exc)
            continue

    if parse_failed:
        summary = f"[PARSE_FAILED] Raw response:\n{response[:500]}"

    return PersonaReport(
        persona=persona,
        findings=findings,
        summary=summary,
        ok=not parse_failed,
        error="Could not parse findings JSON" if parse_failed else None,
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
                logger.error("Persona %s raised exception: %s", personas[i].value, result)
                rev.persona_reports.append(PersonaReport(
                    persona=personas[i],
                    summary=f"FAILED: {result}",
                    ok=False,
                    error=str(result),
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
