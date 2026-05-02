# === Advocate Report Generation (src_advocate_report) v1 ===
#  Dependencies: json, pathlib, jinja2, advocate.models, advocate.personas, advocate
# Multi-format report generation for Advocate review results. Renders Review objects to terminal (with ANSI color support), JSON, and HTML outputs. Terminal rendering includes severity-coded findings, persona summaries, and disagreement detection. HTML output uses Jinja2 templating with embedded dark-mode stylesheet.

# Module invariants:
#   - _SEV_COLORS maps Severity enum members to ANSI escape codes
#   - _RESET is ANSI reset code '\033[0m'
#   - _HTML is a pre-compiled Jinja2 Template constant containing the full HTML template
#   - PERSONA_META must contain entries for all Persona enum values
#   - Severity enum ordering determines finding sort order in terminal output

def print_review(
    review: advocate.models.Review,
    color: bool = True,
) -> None:
    """
    Prints a formatted Review to terminal with optional ANSI color codes. Outputs header with target/findings/cost summary, iterates persona_reports showing findings sorted by severity, and displays disagreements if present. Uses _SEV_COLORS for severity highlighting and PERSONA_META for persona metadata.

    Preconditions:
      - review.persona_reports must be iterable
      - Each report.persona must exist as a key in PERSONA_META
      - Each finding must have a severity attribute that can be indexed in list(Severity)

    Postconditions:
      - Formatted text written to stdout via print()
      - No return value
      - No modification to review object

    Errors:
      - KeyError (KeyError): report.persona not found in PERSONA_META
      - AttributeError (AttributeError): Review object missing required attributes (target, total_findings, persona_reports, etc.)

    Side effects: Writes to stdout, Accesses global PERSONA_META dict
    Idempotent: yes
    """
    ...

def write_json(
    review: advocate.models.Review,
    path: pathlib.Path,
) -> None:
    """
    Serializes a Review object to JSON and writes to the specified file path. Uses pydantic's model_dump_json with 2-space indentation.

    Preconditions:
      - review must be a pydantic BaseModel with model_dump_json() method
      - path must be a valid Path object

    Postconditions:
      - File at path contains JSON representation of review with indent=2
      - File is overwritten if it already exists

    Errors:
      - OSError (OSError): Path is not writable or directory does not exist
      - PermissionError (PermissionError): Insufficient permissions to write to path
      - AttributeError (AttributeError): review does not have model_dump_json method

    Side effects: Writes file to filesystem at path location
    Idempotent: no
    """
    ...

def write_html(
    review: advocate.models.Review,
    path: pathlib.Path,
) -> None:
    """
    Renders a Review object to HTML using the _HTML Jinja2 template and writes to the specified file path. Injects PERSONA_META and __version__ into template context. Template generates dark-mode styled report with summary cards, persona findings, and disagreements.

    Preconditions:
      - review object must have attributes used in template (target, target_type, review_id, started_at, total_findings, persona_reports, disagreements, total_cost_usd)
      - _HTML template must be initialized and valid Jinja2 Template
      - All Persona enum values must exist in PERSONA_META
      - advocate.__version__ must be importable

    Postconditions:
      - File at path contains rendered HTML with embedded CSS
      - File is overwritten if it already exists

    Errors:
      - OSError (OSError): Path is not writable or directory does not exist
      - PermissionError (PermissionError): Insufficient permissions to write to path
      - ImportError (ImportError): advocate.__version__ cannot be imported
      - KeyError (KeyError): Persona value not found in PERSONA_META during dict comprehension
      - AttributeError (AttributeError): Review object missing attributes referenced in template

    Side effects: Imports advocate.__version__ at runtime, Accesses global PERSONA_META dict, Writes file to filesystem at path location
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['print_review', 'write_json', 'write_html', 'ImportError']
