"""Data models for Advocate reviews."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class Persona(str, Enum):
    red_team = "red_team"
    adversarial = "adversarial"
    sage = "sage"
    user = "user"
    sme = "sme"
    good_friend = "good_friend"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class Dimension(str, Enum):
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


class Finding(BaseModel):
    """A single finding from one persona."""

    persona: Persona
    severity: Severity
    dimension: Dimension
    title: str
    detail: str
    evidence: str = ""
    recommendation: str = ""


class PersonaReport(BaseModel):
    """Complete output from one persona's review."""

    persona: Persona
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""
    duration_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class Disagreement(BaseModel):
    """When two personas disagree -- this is signal, not noise."""

    finding_a: Finding
    finding_b: Finding
    tension: str  # What the disagreement reveals


class Review(BaseModel):
    """Complete Advocate review."""

    review_id: str = Field(default_factory=lambda: f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}")
    target: str  # What was reviewed (file path, description, etc.)
    target_type: str = ""  # "file", "directory", "pr", "stdin", "text"
    started_at: str = ""
    completed_at: str | None = None
    persona_reports: list[PersonaReport] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    total_findings: int = 0
    total_cost_usd: float = 0.0

    def all_findings(self) -> list[Finding]:
        return [f for r in self.persona_reports for f in r.findings]
