# Advocate — improvement notes

Field notes from using `advocate review` in the MEA build (2026-06-24). Logged by
the MEA engineering agent.

Status: the high-priority model/default failure in section 1 is fixed in v0.1.2
and the public install docs were corrected in v0.1.3.
The section 4 defects (tracked bytecode, misreported 529, Claude 5 cost/thinking
handling) are fixed in v0.1.5.
The triage and diff/stdin notes remain future enhancements.

## 1. BUG (high): default model 404s, and the failure is silent → FALSE "0 findings"

`advocate review <file>` (no `--model`) sends every persona to model
`claude-sonnet-4-20250514`, which returns:

```
Error code: 404 - {'type':'error','error':{'type':'not_found_error','message':'model: claude-sonnet-4-20250514'}}
```

Each persona then prints **"No findings. (This is a strong positive signal.)"** and
the summary reports **"0 findings | $0.0000 | 6 personas"**. That is a *false pass*:
an operator who doesn't read the per-persona `... failed:` lines will believe the
code was reviewed clean when **no review ran**. This is the most dangerous possible
failure mode for a review tool.

**Fixes (in priority order):**
1. **Fail loudly.** If any persona errors, exit non-zero and print a clear banner
   (`REVIEW INCOMPLETE: N/6 personas failed`). Never render an error as
   "No findings / strong positive signal."
2. **Update the default model** to a currently-available one (e.g. `claude-sonnet-4-6`).
   The hardcoded `claude-sonnet-4-20250514` is gone.
3. **Honor a model env var.** `ADVOCATE_MODEL=...` was NOT picked up; only the
   `--model` flag worked. Support the env (and `provider.py`'s default) consistently.
4. **Pre-flight the model.** On startup, do a 1-token ping; if the model 404s, error
   out with the available-model hint before spawning 6 persona calls.

**Workaround that works today:** `advocate review --model claude-sonnet-4-6 <file>`.
With a live model the tool is genuinely good — it produced 45 well-categorized
findings (race/TOCTOU/atomicity/authz/injection) on one route file.

## 2. Enhancement: triage signal

The 45 findings included several that were already mitigated (DB UNIQUE constraint,
atomic commit-with-audit) or convention (ORM-parameterized queries). A
`--severity-min high` filter and a per-finding "is this already mitigated?" prompt
hint would cut triage time. The genuinely valuable output was "prove your mitigations"
— findings that pushed untested-but-correct guards into explicit tests.

## 3. Enhancement: diff/stdin review of a multi-file change

For an increment touching model + schema + route + migration, reviewing one file at a
time loses cross-file context. `git diff | advocate review --stdin` works but the
personas would benefit from a "this is a unified diff across N files" framing.

## 4. BUGs (fixed 2026-08-24): tracked bytecode, misreported 529, Claude 5 handling

Field notes from live overnight usage. Logged by the Claude Fable 5 maintenance agent.

**Tracked `__pycache__`.** `src/advocate/__pycache__/*.pyc` were committed to git despite
`.gitignore` already listing `__pycache__/` and `*.pyc` — they'd been force-added before
the ignore rules existed. Untracked from the index (`git rm --cached`-equivalent); working
tree files and `.gitignore` were already correct.

**Preflight misreported a transient 529 as a rejected model.** `--model claude-opus-5` hit
`overloaded_error` (HTTP 529 — Anthropic is busy, unrelated to the model name) and Advocate
printed "Model 'claude-opus-5' was rejected by Anthropic. Run with a current Claude model
such as 'claude-sonnet-4-6'" — wrong on both counts: a 529 isn't a rejection, and the
suggested replacement model is itself just one release away from being wrong. Fixed:
`LLMProvider.preflight()` now retries a transient error (429, or any 5xx including 529)
twice with a short backoff before giving up; the CLI reports "REVIEW NOT STARTED:
{provider} overloaded, try again" for a transient failure, distinct from "model preflight
failed" + hint for a genuine rejection (400/404). `model_error_hint()` no longer hardcodes
a specific replacement model — it points at Advocate's own current default constant, so the
hint can't itself go stale.

**Claude 5 family: pricing, thinking blocks, temperature.** `estimate_cost()` had no entries
past the Claude 4 tier; an unrecognized model silently fell back to Sonnet-4 pricing, which
is a guess dressed up as a number. Fixed: unknown models now return cost as `None`
("unknown"), never a fabricated figure — deliberately no Claude 5 prices were added, since
Sonnet 5's published rate includes a time-limited introductory price that would go stale
within days of being hardcoded. Response parsing was already correct (filters
`response.content` by `type == "text"`, not `content[0].text`, so a leading `thinking`
block from a Claude 5 model was never a problem) — hardened further by explicitly sending
`thinking: {"type": "disabled"}` for opus-5/sonnet-5/haiku-5 so a small `max_tokens` (like
the preflight's 16) can't be entirely consumed by thinking, leaving zero response text.
Confirmed Advocate never sends `temperature` (Claude 5 models reject it). Verified live: the
existing default (`claude-sonnet-4-6`) is still accepted by the API as of this writing, so
it was left unchanged — see the model catalog / `ADVOCATE_MODEL` if that changes.
