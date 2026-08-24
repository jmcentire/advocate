# REVIEW.md — Advocate

Guidance for automated code review of this repo. Concise by design.

## Always check

- **Every finding needs evidence** (constraints.yaml C007): a `Finding` without `evidence`
  is an opinion, not a review result.
- **Persona failures must stay visible** (C003, C009): a failed persona is rendered as
  `PERSONA FAILED: ...`, never silently dropped, and never rendered as "No findings /
  strong positive signal." An empty findings list from a persona that *succeeded* is a
  real, valuable signal — don't conflate the two states.
- **Cost/token transparency** (C004): every LLM call must report input tokens, output
  tokens, and an estimated cost — or explicitly `None`/"unknown" when the model's price
  isn't known. Never invent a price by falling back to another model's rate, and never
  silently coerce an unknown cost to `$0.00`.
- **Prompt injection defense** (C001): user-supplied content embedded into persona prompts
  must go through `_sanitize_content_for_prompt` (or an equivalent) first.
- **Path traversal / binary safety** (C002, C005): directory review must keep resolved
  paths inside the target root and skip binary files before they reach a prompt.
- **Provider isolation** (C006): provider-specific logic (Anthropic/OpenAI/Gemini SDK
  calls, model-family quirks) stays behind the `LLMProvider` abstraction in `provider.py`
  — never leaks into `engine.py`, `report.py`, or `cli.py`.
- **Model-family correctness**: a change touching `provider.py`'s request construction
  should be checked against current Claude API behavior for whichever models it affects —
  sampling params (`temperature`/`top_p`/`top_k`) rejected on Claude 5-tier models,
  `thinking` defaults/effort interaction, response content-block parsing (never
  `content[0].text` — filter by `type == "text"`), and transient (429/5xx, incl. 529
  `overloaded_error`) vs. genuine-rejection (400/404) error handling in `preflight()`.
- **New pytest coverage for new behavior**: per `sops.md`, every function needs at least
  one test; a new/changed persona-parsing, cost-estimation, or preflight code path needs a
  test that would fail on the old behavior (not just one that passes on the new).
- **Pydantic model changes**: check `models.py` field-type changes against every reader in
  `report.py` (terminal + Jinja HTML template) and `engine.py`'s aggregation — an
  `Optional` field introduced without updating every consumer is a crash waiting to happen
  (e.g. `f"{x:.4f}"` on `None`).

## Style

- Type annotations on all public functions (`sops.md`).
- Prefer composition over inheritance; prefer stdlib over third-party deps.
- Keep files under ~300 lines where reasonable.
- Small, targeted diffs — this is a ~7-module core; avoid touching unrelated modules for a
  single-defect fix.

## Skip

- `src/src_advocate_*/` and `tests/src_advocate_*/contract_test.py` — orphaned Pact
  decomposition scaffolding. Not part of the packaged `advocate` module (only
  `src/advocate` is packaged), and `contract_test.py` files are not collected by pytest
  (`pyproject.toml` restricts `python_files` to `test_*.py`). Don't review or "fix" these
  as if they were live code; flag for cleanup separately if touched.
- `contracts/`, `decomposition/`, `learnings/`, `.pact/` — Pact pipeline artifacts, not
  runtime code.
- Generated/build output: `__pycache__/`, `*.egg-info/`, `dist/`, `build/` (already
  gitignored — flag if any reappear as tracked).
- `.kin/` — exported kindex knowledge graph; not hand-edited.
