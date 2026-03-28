"""CLI entry point for Advocate."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click


@click.group()
def main() -> None:
    """advocate -- Six-persona adversarial review engine."""


@main.command()
@click.argument("target", required=False)
@click.option("--provider", type=click.Choice(["anthropic", "openai", "gemini"]),
              default="anthropic", help="LLM provider.")
@click.option("--model", default=None, help="Override model name.")
@click.option("--persona", "-p", multiple=True,
              help="Run specific persona(s) only. Can be repeated.")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write JSON output to file.")
@click.option("--html", type=click.Path(), default=None,
              help="Write HTML report to file.")
@click.option("--sequential", is_flag=True, default=False,
              help="Run personas sequentially instead of in parallel.")
@click.option("--no-color", is_flag=True, default=False,
              help="Disable terminal colors.")
@click.option("--stdin", "use_stdin", is_flag=True, default=False,
              help="Read input from stdin.")
def review(target: str | None, provider: str, model: str | None,
           persona: tuple[str, ...], output: str | None, html: str | None,
           sequential: bool, no_color: bool, use_stdin: bool) -> None:
    """Review a file, directory, or stdin input.

    \b
    Examples:
      advocate review src/main.py
      advocate review ./my-project/
      echo "some design doc" | advocate review --stdin
      advocate review src/auth.py -p red_team -p adversarial
    """
    async def _review() -> None:
        from advocate.engine import load_input, review as run_review
        from advocate.models import Persona
        from advocate.provider import create_provider
        from advocate.report import print_review, write_json, write_html

        # Load input
        if use_stdin or target is None:
            if sys.stdin.isatty() and target is None:
                click.echo("Error: provide a target path or use --stdin.", err=True)
                sys.exit(1)
            content = sys.stdin.read()
            target_name = "<stdin>"
            target_type = "stdin"
        else:
            content, target_name, target_type = load_input(target)

        if not content.strip():
            click.echo("Error: empty input.", err=True)
            sys.exit(1)

        # Truncation guard
        if len(content) > 200_000:
            click.echo(f"Warning: input is {len(content)} chars, truncating to 200k.", err=True)
            content = content[:200_000] + "\n\n[... truncated ...]"

        # Persona selection
        persona_map = {p.value: p for p in Persona}
        selected: list[Persona] | None = None
        if persona:
            selected = []
            for name in persona:
                if name not in persona_map:
                    click.echo(f"Error: unknown persona '{name}'. Choose from: {list(persona_map)}", err=True)
                    sys.exit(1)
                selected.append(persona_map[name])

        # Create provider
        llm = create_provider(provider, model)
        n = len(selected) if selected else 6
        mode = "sequentially" if sequential else "in parallel"
        click.echo(f"Reviewing {target_name} with {n} personas ({mode}, {provider})...")

        # Run review
        result = await run_review(
            content=content,
            target=target_name,
            target_type=target_type,
            llm=llm,
            personas=selected,
            parallel=not sequential,
        )

        # Output
        print_review(result, color=not no_color)

        if output:
            write_json(result, Path(output))
            click.echo(f"JSON: {output}")

        if html:
            write_html(result, Path(html))
            click.echo(f"HTML: {html}")

    asyncio.run(_review())


@main.command()
def personas() -> None:
    """List all available personas."""
    from advocate.models import Persona
    from advocate.personas import PERSONA_META

    for p in Persona:
        meta = PERSONA_META[p]
        click.echo(f"  {p.value:15s}  {meta['name']}")
        click.echo(f"  {'':15s}  {meta['tagline']}")
        click.echo(f"  {'':15s}  Success: {meta['success']}")
        click.echo(f"  {'':15s}  Dimensions: {', '.join(d.value for d in meta['dimensions'])}")
        click.echo()


if __name__ == "__main__":
    main()
