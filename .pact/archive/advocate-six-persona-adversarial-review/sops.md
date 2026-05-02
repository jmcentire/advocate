# Operating Procedures

## Tech Stack
- Language: Python 3.12+
- Testing: pytest
- Build: hatchling
- CLI: click

## Standards
- Type annotations on all public functions
- Pydantic v2 for all data models
- Async for LLM calls
- Jinja2 for HTML templates

## Verification
- All modules must be importable
- Self-review must produce actionable findings
- Good Friend returning zero findings = strong positive signal

## Preferences
- Prefer stdlib over third-party
- Keep files under 400 lines
- No premature abstraction
- All deps MIT/Apache/BSD compatible
