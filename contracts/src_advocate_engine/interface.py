# === Advocate Review Engine (src_advocate_engine) v1 ===
#  Dependencies: asyncio, json, logging, re, time, datetime, pathlib, advocate.models, advocate.personas, advocate.provider
# Core review orchestration engine that runs six adversarial personas against input content, collects findings, detects disagreements between personas, and generates comprehensive review reports. Handles LLM interactions, JSON parsing, prompt injection sanitization, and file/directory loading.

# Module invariants:
#   - Prompt injection patterns are always sanitized before LLM submission
#   - PersonaReport always includes persona and duration_ms fields
#   - Review aggregates costs and findings from all persona reports
#   - Disagreements require minimum 0.3 title overlap and 2-level severity gap
#   - Supported file extensions: .py, .ts, .js, .tsx, .jsx, .go, .rs, .java, .md, .yaml, .yml, .toml, .json
#   - Blacklisted directory components: .git, __pycache__, node_modules
#   - All timestamps in Review are ISO8601 UTC format
#   - Path traversal protection: resolved paths must be under base directory

class tuple_list_dict_str:
    """Return type for _parse_findings_json: (list of finding dicts, summary text)"""
    findings: list[dict]                     # required
    summary: str                             # required

class tuple_content_target_type:
    """Return type for load_input: (content, target path, target type)"""
    content: str                             # required
    target: str                              # required
    target_type: str                         # required

def _sanitize_content_for_prompt(
    content: str,
) -> str:
    """
    Strip prompt injection patterns from user content before embedding in prompts. Replaces patterns like 'ignore previous instructions', 'you are now', and 'system:' with '[CONTENT_REDACTED]'.

    Postconditions:
      - All case-insensitive matches of prompt injection patterns are replaced with '[CONTENT_REDACTED]'
      - Original string structure preserved except for replaced patterns

    Side effects: none
    Idempotent: no
    """
    ...

def _parse_findings_json(
    text: str,
) -> tuple[list[dict], str]:
    """
    Robustly extract JSON findings array from LLM response. Tries markdown code blocks first, then bracket-matched JSON arrays. Returns (parsed_items, summary_text). On failure returns ([], full_text).

    Postconditions:
      - Returns tuple of (list[dict], str)
      - If parsing succeeds, first element is list of dicts, second is remaining text
      - If parsing fails, returns ([], original_text)

    Errors:
      - json_decode_error_caught (json.JSONDecodeError): JSON parsing fails for candidate blocks
          handling: Exception caught internally, returns ([], text)

    Side effects: none
    Idempotent: no
    """
    ...

async def _run_persona(
    persona: Persona,
    llm: LLMProvider,
    content: str,
    target_description: str,
) -> PersonaReport:
    """
    Run a single persona's review against content. Builds prompts from persona metadata, sanitizes content, calls LLM, parses JSON findings, and returns PersonaReport with findings, costs, and timing.

    Preconditions:
      - persona exists in PERSONA_META dictionary
      - persona exists in SYSTEM_PROMPTS dictionary

    Postconditions:
      - Returns PersonaReport with persona, findings list, summary, duration_ms
      - If LLM call succeeds, includes input_tokens, output_tokens, estimated_cost_usd
      - If LLM call fails, returns PersonaReport with error summary and duration_ms

    Errors:
      - llm_completion_exception (Exception): llm.complete() raises any exception
          handling: Caught, logged, returns PersonaReport with error summary
      - key_error_meta_lookup (KeyError): persona not in PERSONA_META or SYSTEM_PROMPTS
          handling: Not caught, will propagate

    Side effects: Calls llm.complete() which makes network requests, Logs error if LLM call fails, Logs warning if JSON parsing fails, Calls transmogrify() which may make network requests
    Idempotent: no
    """
    ...

def _detect_disagreements(
    reports: list[PersonaReport],
) -> list[Disagreement]:
    """
    Find cases where personas disagree on severity for similar findings. Compares all pairs of findings across reports, identifies those with title overlap >= 0.3 and severity difference >= 2 levels.

    Postconditions:
      - Returns list of Disagreement objects
      - Each disagreement has severity gap of at least 2 levels
      - Each disagreement has title overlap of at least 0.3

    Errors:
      - value_error_severity_index (ValueError): finding.severity not in Severity enum
          handling: Not caught, will propagate from list().index()
      - key_error_persona_meta (KeyError): finding.persona not in PERSONA_META
          handling: Not caught, will propagate

    Side effects: none
    Idempotent: no
    """
    ...

def _word_overlap(
    a: str,
    b: str,
) -> float:
    """
    Calculate word-level Jaccard similarity between two strings. Returns ratio of intersection to union of word sets (case-insensitive).

    Postconditions:
      - Returns float between 0.0 and 1.0
      - Returns 0.0 if either input is empty or contains no words
      - Returns 1.0 if both inputs have identical word sets

    Side effects: none
    Idempotent: no
    """
    ...

async def review(
    content: str,
    target: str,
    target_type: str,
    llm: LLMProvider,
    personas: list[Persona] | None = None,
    parallel: bool = True,
) -> Review:
    """
    Run an Advocate review. Executes persona reviews (in parallel or sequential), detects disagreements, aggregates findings/costs, and returns comprehensive Review object with timing data.

    Postconditions:
      - Returns Review object with persona_reports, disagreements, total_findings, total_cost_usd
      - Review.started_at is ISO8601 UTC timestamp
      - Review.completed_at is ISO8601 UTC timestamp
      - All personas in input list have corresponding PersonaReport (may contain errors)
      - If parallel=True, exceptions from personas are captured and converted to error reports

    Errors:
      - exception_in_sequential_mode (Exception): parallel=False and _run_persona raises exception
          handling: Not caught, will propagate

    Side effects: Calls _run_persona for each persona (makes LLM API calls), Logs errors if parallel execution produces exceptions, Creates multiple concurrent tasks if parallel=True
    Idempotent: no
    """
    ...

def _is_binary(
    path: Path,
) -> bool:
    """
    Check if a file is binary by looking for null bytes in first 1024 bytes.

    Postconditions:
      - Returns True if file contains null byte in first 1024 bytes
      - Returns True if any exception occurs reading file
      - Returns False if file is text (no null bytes found)

    Errors:
      - file_read_exception (Exception): Any exception reading file
          handling: Caught, returns True (treats unreadable as binary)

    Side effects: none
    Idempotent: no
    """
    ...

def load_input(
    path: str,
) -> tuple[str, str, str]:
    """
    Load review input from a path. Handles both files and directories. For directories, recursively collects source files (filtered by extension whitelist), skips binaries and blacklisted paths. Returns (content, target, target_type).

    Postconditions:
      - Returns tuple of (content_string, resolved_path_string, type_string)
      - For directories: type='directory', content is concatenated source files with headers
      - For files: type='file', content is file text
      - All paths are resolved to absolute paths
      - Path traversal attempts are blocked

    Errors:
      - file_not_found (FileNotFoundError): Path does not exist or is neither file nor directory
          message: Not found: {path}
      - binary_file_error (ValueError): Single file path points to binary file
          message: Binary file not supported: {path}
      - encoding_error (ValueError): File is not UTF-8 encoded
          message: File encoding error: {path}. Only UTF-8 is supported.
      - no_source_files (ValueError): Directory contains no supported source files
          message: No source files found in {path}. Supported: {extensions}

    Side effects: Reads file(s) from filesystem, Logs info about skipped files if any
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['tuple_list_dict_str', 'tuple_content_target_type', '_sanitize_content_for_prompt', '_parse_findings_json', '_run_persona', '_detect_disagreements', '_word_overlap', 'review', '_is_binary', 'load_input']
