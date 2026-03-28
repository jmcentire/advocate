# Advocate

Six-persona adversarial review engine. Feed it code, a design doc, or an architecture decision and six distinct perspectives attack it simultaneously, each with a different standard of success.

## Quick Start

```bash
pip install advocate[anthropic]

# Review a file
advocate review src/main.py

# Review a directory
advocate review ./my-project/

# Review from stdin
echo "We plan to store session tokens in localStorage" | advocate review --stdin

# Just the hardest personas
advocate review src/auth.py -p red_team -p good_friend
```

## The Six Personas

| Persona | Angle | Success Criterion |
|---|---|---|
| **Red Team** | It's vulnerable; harden. | The thing survives assault. |
| **Adversarial** | It's wrong; defend. | The argument holds under direct challenge. |
| **Sage** | It's complicated; simplify. | A smart person can explain it simply. |
| **User** | It's unintuitive; clarify. | Someone unfamiliar can navigate it without a guide. |
| **Subject Matter Expert** | Peer-review. | A peer would sign off on it. |
| **Good Friend** | The harsh truth you need to hear. | You'd rather know now than later. |

They run in parallel (6 simultaneous LLM calls) and sometimes disagree with each other. The disagreements are signal, not noise -- they reveal tensions worth examining.

## Dimensions of Coverage

Each persona covers specific dimensions, but the perspectives overlap deliberately:

- **Security** -- authentication, authorization, privilege escalation
- **Injection** -- SQL, XSS, command, template, path traversal
- **Exploitation** -- race conditions, TOCTOU, replay attacks
- **Data corruption** -- truncation, encoding, integrity violations
- **Edge cases** -- boundaries, empty inputs, Unicode, timezones
- **Race conditions** -- concurrency, inconsistent state
- **Failure modes** -- dependency failures, network issues, disk full
- **Wrong assumptions** -- implicit assumptions never validated
- **Backward compatibility** -- breaking existing users, data, integrations
- **Blast radius** -- if this fails, how much else breaks?
- **Financial risk** -- hidden costs, vendor lock-in, scaling surprises
- **The 3am test** -- would you be comfortable being woken up to deal with this?
- **Design** -- over-engineering, premature abstraction, wrong patterns
- **Concept** -- is the fundamental approach sound?

## The 3am Test

> "Would you be comfortable being woken up at 3am to deal with this in production?"

One of the most useful single-question heuristics in engineering. The Good Friend applies it ruthlessly. If the answer is no, you'll hear about it.

## Output

Terminal output with color-coded severity, plus optional JSON and HTML:

```bash
# Terminal only (default)
advocate review src/explorer.py

# Save JSON for CI integration
advocate review src/ -o findings.json

# Generate HTML report
advocate review src/ --html report.html

# Both
advocate review src/ -o findings.json --html report.html
```

### Severity Levels

- **critical** -- stop what you're doing and fix this
- **high** -- fix before shipping
- **medium** -- fix soon, or accept the risk explicitly
- **low** -- nice to fix, won't keep you up at night
- **info** -- awareness, not action

## Disagreements

When two personas disagree about the same thing, Advocate surfaces it:

```
DISAGREEMENTS (1)
==================================================
Sage rates this low, but Red Team rates it high.
The gap suggests different risk models worth examining.
```

A Sage saying "simplify this" while the SME says "this complexity is necessary" is useful information. The tension itself is the finding.

## CLI Reference

```
advocate review <target>           # Review a file or directory
advocate review --stdin            # Review from stdin
advocate review -p red_team        # Specific persona(s)
advocate review --sequential       # Run one at a time (cheaper)
advocate review --no-color         # Disable terminal colors
advocate personas                  # List all personas
```

### Options

```
--provider NAME     anthropic (default), openai, gemini
--model NAME        Override model
-p, --persona NAME  Run specific persona(s), repeatable
-o, --output PATH   Write JSON output
--html PATH         Write HTML report
--sequential        Run personas one at a time
--no-color          Disable terminal colors
--stdin             Read from stdin
```

## LLM Providers

| Provider | Default Model | Install |
|---|---|---|
| Anthropic | claude-sonnet-4 | `pip install advocate[anthropic]` |
| OpenAI | gpt-4o | `pip install advocate[openai]` |
| Gemini | gemini-2.5-flash | `pip install advocate[gemini]` |

Set the corresponding API key environment variable (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

## Supported File Types

When reviewing directories, Advocate reads: `.py`, `.ts`, `.js`, `.tsx`, `.jsx`, `.go`, `.rs`, `.java`, `.md`, `.yaml`, `.yml`, `.toml`, `.json`

Binary files, `__pycache__`, `.git`, and `node_modules` are skipped automatically.

## Cost

Six parallel calls to Claude Sonnet costs ~$0.15-0.30 per review depending on input size. Use `--sequential` or `-p` to reduce costs. Token counts and estimated USD are shown in the output.

## Self-Reviewed

Advocate reviewed itself. First pass: 30 findings. Fixed the real ones (prompt injection sanitization, path traversal protection, binary file detection, error visibility, robust JSON parsing). Second pass: 13 findings remaining, Good Friend returned zero.

## Dependencies

All permissive licenses:

| Package | License | Required |
|---|---|---|
| pydantic | MIT | Yes |
| pyyaml | MIT | Yes |
| click | BSD 3-Clause | Yes |
| jinja2 | BSD 3-Clause | Yes |
| anthropic | MIT | Optional |
| openai | MIT | Optional |
| google-genai | Apache 2.0 | Optional |
| transmogrifier | MIT | Optional |

## License

MIT
