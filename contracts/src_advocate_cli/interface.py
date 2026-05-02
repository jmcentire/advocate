# === Advocate CLI Entry Point (src_advocate_cli) v1 ===
#  Dependencies: asyncio, sys, pathlib, click, advocate.engine, advocate.models, advocate.provider, advocate.report, advocate.personas
# Command-line interface for the Advocate six-persona adversarial review engine. Provides commands to review code/documentation via files, directories, or stdin, and to list available personas. Orchestrates input loading, LLM provider setup, parallel/sequential review execution, and output formatting (terminal, JSON, HTML).

# Module invariants:
#   - Content is truncated at 200,000 characters if exceeded
#   - Default provider is 'anthropic'
#   - Default execution mode is parallel (sequential=False)
#   - Default is 6 personas if none specified
#   - Stdin target is named '<stdin>' with type 'stdin'

def main() -> None:
    """
    Click command group entry point for Advocate CLI. Serves as the root command for all subcommands.

    Postconditions:
      - Click group is initialized and ready to dispatch to subcommands

    Side effects: Registers click command group
    Idempotent: no
    """
    ...

def review(
    target: str | None = None,
    provider: str,             # custom(in ['anthropic', 'openai', 'gemini'])
    model: str | None = None,
    persona: tuple[str, ...],
    output: str | None = None,
    html: str | None = None,
    sequential: bool,
    no_color: bool,
    use_stdin: bool,
) -> None:
    """
    Review command that analyzes a file, directory, or stdin input using multiple adversarial personas. Supports provider selection, persona filtering, output formats (JSON/HTML), and parallel/sequential execution modes.

    Preconditions:
      - Either target is provided or use_stdin is True
      - If no target and not use_stdin, stdin must not be a tty
      - All specified persona names must exist in Persona enum

    Postconditions:
      - Review is executed and results are printed to stdout
      - If output specified, JSON file is written
      - If html specified, HTML file is written

    Errors:
      - missing_input (SystemExit): No target provided and stdin is a tty
          exit_code: 1
          message: Error: provide a target path or use --stdin.
      - empty_input (SystemExit): Content is empty or only whitespace
          exit_code: 1
          message: Error: empty input.
      - unknown_persona (SystemExit): Specified persona name not in Persona enum
          exit_code: 1
          message: Error: unknown persona '{name}'. Choose from: {list}
      - truncation_declined (SystemExit): Content > 200k chars and user declines truncation confirmation
          exit_code: 0

    Side effects: Reads from stdin if use_stdin or target is None, Writes to stdout (click.echo), Writes to stderr (click.echo with err=True), Calls sys.exit on error conditions, May write JSON file if output specified, May write HTML file if html specified, Makes network calls to LLM provider, May read files/directories via load_input, May prompt user for confirmation if content > 200k chars
    Idempotent: no
    """
    ...

def personas() -> None:
    """
    List all available personas with their metadata including name, tagline, success criteria, and dimensions.

    Postconditions:
      - All Persona enum values and their metadata are printed to stdout

    Side effects: Writes to stdout via click.echo
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['main', 'review', 'SystemExit', 'personas']
