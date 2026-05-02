# === Advocate Data Models (src_advocate_models) v1 ===
#  Dependencies: datetime, enum, uuid, pydantic
# Data models for Advocate reviews. Defines Pydantic models and enums for representing multi-persona adversarial code review results, including findings, persona reports, disagreements, and complete review artifacts.

# Module invariants:
#   - Persona enum has exactly 6 variants representing review personas
#   - Severity enum has exactly 5 levels from critical to info
#   - Dimension enum has exactly 14 review categories
#   - Review.review_id format is always YYYYMMDDTHHMMSS-{8 hex chars}
#   - All Pydantic models validate their fields on instantiation
#   - Finding.evidence and Finding.recommendation default to empty string
#   - PersonaReport numeric fields (duration_ms, tokens, cost) default to 0 or 0.0
#   - Review.completed_at can be None to represent incomplete reviews

class Persona(Enum):
    """Enumeration of reviewer personas that can conduct adversarial reviews"""
    red_team = "red_team"
    adversarial = "adversarial"
    sage = "sage"
    user = "user"
    sme = "sme"
    good_friend = "good_friend"

class Severity(Enum):
    """Severity levels for findings"""
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"

class Dimension(Enum):
    """Review dimensions or categories for findings"""
    security = "security"
    data_corruption = "data_corruption"
    injection = "injection"
    exploitation = "exploitation"
    edge_cases = "edge_cases"
    race_conditions = "race_conditions"
    failure_modes = "failure_modes"
    wrong_assumptions = "wrong_assumptions"
    backward_compatibility = "backward_compatibility"
    blast_radius = "blast_radius"
    financial_risk = "financial_risk"
    three_am_test = "three_am_test"
    design = "design"
    concept = "concept"

class Finding:
    """A single finding from one persona's review"""
    persona: Persona                         # required, Which persona identified this finding
    severity: Severity                       # required, Severity level of the finding
    dimension: Dimension                     # required, Review dimension this finding belongs to
    title: str                               # required, Brief title of the finding
    detail: str                              # required, Detailed description of the finding
    evidence: str = None                     # optional, Supporting evidence for the finding
    recommendation: str = None               # optional, Recommended remediation

class PersonaReport:
    """Complete output from one persona's review including findings and metadata"""
    persona: Persona                         # required, The persona that conducted this review
    findings: list[Finding] = []             # optional, All findings from this persona
    summary: str = None                      # optional, Summary of the persona's review
    duration_ms: float = 0.0                 # optional, Time taken for this persona's review in milliseconds
    input_tokens: int = 0                    # optional, LLM input tokens consumed
    output_tokens: int = 0                   # optional, LLM output tokens generated
    estimated_cost_usd: float = 0.0          # optional, Estimated cost in USD for this review

class Disagreement:
    """Represents when two personas disagree, which reveals signal about edge cases or ambiguity"""
    finding_a: Finding                       # required, First finding in the disagreement
    finding_b: Finding                       # required, Second finding in the disagreement
    tension: str                             # required, Description of what the disagreement reveals

class Review:
    """Complete Advocate review with all persona reports, findings, and metadata"""
    review_id: str = generated from timestamp and uuid4 # optional, Unique identifier in format YYYYMMDDTHHMMSS-<8-char-hex>
    target: str                              # required, What was reviewed (file path, description, etc.)
    target_type: str = None                  # optional, Type of target: 'file', 'directory', 'pr', 'stdin', 'text'
    started_at: str = None                   # optional, ISO timestamp when review started
    completed_at: str | None = None          # optional, ISO timestamp when review completed
    persona_reports: list[PersonaReport] = [] # optional, All persona reports from this review
    disagreements: list[Disagreement] = []   # optional, Identified disagreements between personas
    total_findings: int = 0                  # optional, Total count of all findings across all personas
    total_cost_usd: float = 0.0              # optional, Total estimated cost in USD for the entire review

def all_findings(
    self: Review,
) -> list[Finding]:
    """
    Flattens all findings from all persona reports into a single list. Method on Review class.

    Preconditions:
      - self.persona_reports is a valid list (may be empty)

    Postconditions:
      - Returns a list containing all findings from all persona reports in order
      - Empty list if no persona reports or no findings in any report
      - Order preserves persona_reports iteration order and findings order within each report

    Side effects: none
    Idempotent: yes
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['Persona', 'Severity', 'Dimension', 'Finding', 'PersonaReport', 'Disagreement', 'Review', 'all_findings']
