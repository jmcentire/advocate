# Advocate — Six-Persona Adversarial Review Engine

## Task

Build a tool that runs six distinct adversarial perspectives against any input (code, design docs, architecture decisions) simultaneously. Each persona attacks from a different angle with a different standard of success. Disagreements between personas are surfaced as valuable signal.

## Context

Code review is bottlenecked by individual perspective. A security engineer sees different things than a UX designer, who sees different things than the person who'll be paged at 3am. Advocate codifies six of these perspectives as LLM-driven personas that run in parallel, producing structured findings with severity, dimension, evidence, and recommendations.

## Constraints

- LLM provider must be configurable (Claude, OpenAI, Gemini)
- User content must be sanitized before embedding in prompts (prompt injection defense)
- Path traversal must be prevented when reading directories
- Binary files must be detected and skipped
- Failed personas must be reported, not silently dropped
- JSON parsing must be robust (LLMs return varied formats)
- Cost must be visible (tokens and estimated USD per persona)

## Requirements

- Six personas: Red Team, Adversarial, Sage, User, SME, Good Friend
- 14 dimensions of coverage across engineering, architecture, and operational reality
- Parallel execution by default (~30s for all six)
- Disagreement detection between personas
- Terminal, JSON, and HTML output formats
- Self-reviewed: Advocate must review itself and survive
