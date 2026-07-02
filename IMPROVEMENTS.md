# Advocate — improvement notes

Field notes from using `advocate review` in the MEA build (2026-06-24). Logged by
the MEA engineering agent.

Status: the high-priority model/default failure in section 1 is fixed in v0.1.2.
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
