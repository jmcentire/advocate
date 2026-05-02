"""
Contract tests for Advocate Data Models (src_advocate_models)

Tests verify the behavior of enums, data models, and the all_findings() method
according to the contract specification.
"""

import pytest
import re
from datetime import datetime
from unittest.mock import Mock, patch
from src.advocate.models import (
    Persona,
    Severity,
    Dimension,
    Finding,
    PersonaReport,
    Disagreement,
    Review
)


# =============================================================================
# ENUM INVARIANT TESTS
# =============================================================================

def test_persona_enum_variants():
    """Verify Persona enum has exactly 6 variants as specified in contract."""
    expected_variants = {'red_team', 'adversarial', 'sage', 'user', 'sme', 'good_friend'}
    actual_variants = {member.name for member in Persona}
    
    assert len(Persona) == 6, f"Expected 6 Persona variants, got {len(Persona)}"
    assert actual_variants == expected_variants, f"Persona variants mismatch: {actual_variants}"
    
    # Verify each can be accessed
    assert Persona.red_team
    assert Persona.adversarial
    assert Persona.sage
    assert Persona.user
    assert Persona.sme
    assert Persona.good_friend


def test_severity_enum_variants():
    """Verify Severity enum has exactly 5 levels from critical to info."""
    expected_variants = {'critical', 'high', 'medium', 'low', 'info'}
    actual_variants = {member.name for member in Severity}
    
    assert len(Severity) == 5, f"Expected 5 Severity levels, got {len(Severity)}"
    assert actual_variants == expected_variants, f"Severity variants mismatch: {actual_variants}"
    
    # Verify each can be accessed
    assert Severity.critical
    assert Severity.high
    assert Severity.medium
    assert Severity.low
    assert Severity.info


def test_dimension_enum_variants():
    """Verify Dimension enum has exactly 14 review categories."""
    expected_variants = {
        'security', 'data_corruption', 'injection', 'exploitation', 'edge_cases',
        'race_conditions', 'failure_modes', 'wrong_assumptions', 'backward_compatibility',
        'blast_radius', 'financial_risk', 'three_am_test', 'design', 'concept'
    }
    actual_variants = {member.name for member in Dimension}
    
    assert len(Dimension) == 14, f"Expected 14 Dimension categories, got {len(Dimension)}"
    assert actual_variants == expected_variants, f"Dimension variants mismatch: {actual_variants}"
    
    # Verify each can be accessed
    assert Dimension.security
    assert Dimension.data_corruption
    assert Dimension.injection
    assert Dimension.exploitation
    assert Dimension.edge_cases
    assert Dimension.race_conditions
    assert Dimension.failure_modes
    assert Dimension.wrong_assumptions
    assert Dimension.backward_compatibility
    assert Dimension.blast_radius
    assert Dimension.financial_risk
    assert Dimension.three_am_test
    assert Dimension.design
    assert Dimension.concept


# =============================================================================
# FINDING TESTS
# =============================================================================

def test_finding_construction_happy_path():
    """Create Finding with all required fields and verify structure."""
    finding = Finding(
        persona=Persona.red_team,
        severity=Severity.critical,
        dimension=Dimension.security,
        title="SQL Injection vulnerability",
        detail="User input not sanitized in query builder",
        evidence="Line 42: cursor.execute(f'SELECT * FROM users WHERE id={user_id}')",
        recommendation="Use parameterized queries"
    )
    
    assert finding.persona == Persona.red_team
    assert finding.severity == Severity.critical
    assert finding.dimension == Dimension.security
    assert finding.title == "SQL Injection vulnerability"
    assert finding.detail == "User input not sanitized in query builder"
    assert finding.evidence == "Line 42: cursor.execute(f'SELECT * FROM users WHERE id={user_id}')"
    assert finding.recommendation == "Use parameterized queries"


def test_finding_default_values():
    """Verify Finding.evidence and Finding.recommendation default to empty string."""
    finding = Finding(
        persona=Persona.sage,
        severity=Severity.medium,
        dimension=Dimension.design,
        title="Architecture concern",
        detail="Component coupling is too tight"
    )
    
    assert finding.evidence == "", f"Expected evidence='', got {finding.evidence!r}"
    assert finding.recommendation == "", f"Expected recommendation='', got {finding.recommendation!r}"


def test_finding_empty_strings():
    """Test Finding with empty strings for title and detail."""
    finding = Finding(
        persona=Persona.user,
        severity=Severity.info,
        dimension=Dimension.concept,
        title="",
        detail=""
    )
    
    assert finding.title == ""
    assert finding.detail == ""
    assert finding.evidence == ""
    assert finding.recommendation == ""


def test_finding_unicode_strings():
    """Test Finding with unicode characters in strings."""
    finding = Finding(
        persona=Persona.sme,
        severity=Severity.low,
        dimension=Dimension.edge_cases,
        title="Unicode handling: 你好 🚀",
        detail="Testing émojis and spëcial çharacters",
        evidence="Input: '日本語' → Output: '???'",
        recommendation="Use UTF-8 encoding everywhere 💯"
    )
    
    assert "你好" in finding.title
    assert "🚀" in finding.title
    assert "émojis" in finding.detail
    assert "日本語" in finding.evidence
    assert "💯" in finding.recommendation


def test_finding_serialization_roundtrip():
    """Test Finding can be serialized to dict and back."""
    original = Finding(
        persona=Persona.adversarial,
        severity=Severity.high,
        dimension=Dimension.injection,
        title="XSS vulnerability",
        detail="Unescaped HTML in template",
        evidence="<script>alert('xss')</script>",
        recommendation="Sanitize all user inputs"
    )
    
    # Serialize to dict
    data = original.model_dump()
    
    # Deserialize back
    restored = Finding.model_validate(data)
    
    assert restored.persona == original.persona
    assert restored.severity == original.severity
    assert restored.dimension == original.dimension
    assert restored.title == original.title
    assert restored.detail == original.detail
    assert restored.evidence == original.evidence
    assert restored.recommendation == original.recommendation


# =============================================================================
# PERSONA REPORT TESTS
# =============================================================================

def test_persona_report_construction_happy_path():
    """Create PersonaReport with valid data including findings and metadata."""
    findings = [
        Finding(
            persona=Persona.red_team,
            severity=Severity.critical,
            dimension=Dimension.security,
            title="Critical finding",
            detail="Details here"
        ),
        Finding(
            persona=Persona.red_team,
            severity=Severity.medium,
            dimension=Dimension.edge_cases,
            title="Edge case",
            detail="Another detail"
        )
    ]
    
    report = PersonaReport(
        persona=Persona.red_team,
        findings=findings,
        summary="Found 2 issues requiring attention",
        duration_ms=1234.56,
        input_tokens=500,
        output_tokens=750,
        estimated_cost_usd=0.0125
    )
    
    assert report.persona == Persona.red_team
    assert len(report.findings) == 2
    assert report.findings[0].title == "Critical finding"
    assert report.findings[1].title == "Edge case"
    assert report.summary == "Found 2 issues requiring attention"
    assert report.duration_ms == 1234.56
    assert report.input_tokens == 500
    assert report.output_tokens == 750
    assert report.estimated_cost_usd == 0.0125


def test_persona_report_default_numeric_fields():
    """Verify PersonaReport numeric fields default to 0 or 0.0."""
    report = PersonaReport(
        persona=Persona.sage,
        findings=[],
        summary="No issues found"
    )
    
    assert report.duration_ms == 0.0, f"Expected duration_ms=0.0, got {report.duration_ms}"
    assert report.input_tokens == 0, f"Expected input_tokens=0, got {report.input_tokens}"
    assert report.output_tokens == 0, f"Expected output_tokens=0, got {report.output_tokens}"
    assert report.estimated_cost_usd == 0.0, f"Expected estimated_cost_usd=0.0, got {report.estimated_cost_usd}"


def test_persona_report_empty_findings():
    """Test PersonaReport with empty findings list."""
    report = PersonaReport(
        persona=Persona.user,
        findings=[],
        summary="Everything looks good"
    )
    
    assert report.findings == []
    assert len(report.findings) == 0


def test_persona_report_large_metrics():
    """Test PersonaReport with very large numeric values."""
    report = PersonaReport(
        persona=Persona.good_friend,
        findings=[],
        summary="Large metrics test",
        duration_ms=999999999.99,
        input_tokens=1000000,
        output_tokens=2000000,
        estimated_cost_usd=9999.99
    )
    
    assert report.duration_ms == 999999999.99
    assert report.input_tokens == 1000000
    assert report.output_tokens == 2000000
    assert report.estimated_cost_usd == 9999.99


# =============================================================================
# DISAGREEMENT TESTS
# =============================================================================

def test_disagreement_construction_happy_path():
    """Create Disagreement with two findings and tension description."""
    finding_a = Finding(
        persona=Persona.red_team,
        severity=Severity.critical,
        dimension=Dimension.security,
        title="This is a critical security flaw",
        detail="Immediate attention required"
    )
    
    finding_b = Finding(
        persona=Persona.sage,
        severity=Severity.low,
        dimension=Dimension.security,
        title="This is acceptable risk",
        detail="Can be addressed in future sprint"
    )
    
    disagreement = Disagreement(
        finding_a=finding_a,
        finding_b=finding_b,
        tension="Red team sees critical risk, sage sees acceptable risk - severity mismatch"
    )
    
    assert disagreement.finding_a.persona == Persona.red_team
    assert disagreement.finding_b.persona == Persona.sage
    assert disagreement.finding_a.severity == Severity.critical
    assert disagreement.finding_b.severity == Severity.low
    assert "severity mismatch" in disagreement.tension


# =============================================================================
# REVIEW TESTS
# =============================================================================

def test_review_construction_happy_path():
    """Create Review with all fields populated including persona reports."""
    finding1 = Finding(
        persona=Persona.red_team,
        severity=Severity.high,
        dimension=Dimension.security,
        title="Finding 1",
        detail="Detail 1"
    )
    
    report1 = PersonaReport(
        persona=Persona.red_team,
        findings=[finding1],
        summary="1 finding",
        duration_ms=1000.0,
        input_tokens=100,
        output_tokens=200,
        estimated_cost_usd=0.01
    )
    
    disagreement = Disagreement(
        finding_a=finding1,
        finding_b=finding1,
        tension="Example tension"
    )
    
    review = Review(
        review_id="20231215T143022-a1b2c3d4",
        target="user_service.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[report1],
        disagreements=[disagreement],
        total_findings=1,
        total_cost_usd=0.01
    )
    
    assert review.review_id == "20231215T143022-a1b2c3d4"
    assert review.target == "user_service.py"
    assert review.target_type == "file"
    assert review.started_at == "2023-12-15T14:30:22Z"
    assert review.completed_at == "2023-12-15T14:35:45Z"
    assert len(review.persona_reports) == 1
    assert len(review.disagreements) == 1
    assert review.total_findings == 1
    assert review.total_cost_usd == 0.01


def test_review_id_format_invariant():
    """Verify Review.review_id follows YYYYMMDDTHHMMSS-{8 hex chars} format."""
    review = Review(
        review_id="20231215T143022-a1b2c3d4",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at=None,
        persona_reports=[],
        disagreements=[],
        total_findings=0,
        total_cost_usd=0.0
    )
    
    # Pattern: YYYYMMDDTHHMMSS-{8 hex chars}
    pattern = r'^\d{8}T\d{6}-[0-9a-fA-F]{8}$'
    assert re.match(pattern, review.review_id), f"review_id {review.review_id} doesn't match format YYYYMMDDTHHMMSS-{{8 hex chars}}"


def test_review_completed_at_none():
    """Verify Review.completed_at can be None for incomplete reviews."""
    review = Review(
        review_id="20231215T143022-abcd1234",
        target="ongoing_review.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at=None,
        persona_reports=[],
        disagreements=[],
        total_findings=0,
        total_cost_usd=0.0
    )
    
    assert review.completed_at is None, f"Expected completed_at=None, got {review.completed_at}"


def test_review_empty_disagreements():
    """Test Review with empty disagreements list."""
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[],
        disagreements=[],
        total_findings=0,
        total_cost_usd=0.0
    )
    
    assert review.disagreements == []
    assert len(review.disagreements) == 0


def test_review_zero_metrics():
    """Test Review with total_findings=0 and total_cost_usd=0.0."""
    review = Review(
        review_id="20231215T143022-00000000",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[],
        disagreements=[],
        total_findings=0,
        total_cost_usd=0.0
    )
    
    assert review.total_findings == 0
    assert review.total_cost_usd == 0.0


def test_review_serialization_roundtrip():
    """Test complete Review can be serialized to dict and back."""
    finding = Finding(
        persona=Persona.adversarial,
        severity=Severity.medium,
        dimension=Dimension.design,
        title="Design issue",
        detail="Needs refactoring"
    )
    
    report = PersonaReport(
        persona=Persona.adversarial,
        findings=[finding],
        summary="1 design issue",
        duration_ms=500.5,
        input_tokens=50,
        output_tokens=100,
        estimated_cost_usd=0.005
    )
    
    original = Review(
        review_id="20231215T143022-ffffffff",
        target="module.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[report],
        disagreements=[],
        total_findings=1,
        total_cost_usd=0.005
    )
    
    # Serialize to dict
    data = original.model_dump()
    
    # Deserialize back
    restored = Review.model_validate(data)
    
    assert restored.review_id == original.review_id
    assert restored.target == original.target
    assert restored.target_type == original.target_type
    assert restored.started_at == original.started_at
    assert restored.completed_at == original.completed_at
    assert len(restored.persona_reports) == 1
    assert restored.persona_reports[0].persona == Persona.adversarial
    assert len(restored.persona_reports[0].findings) == 1
    assert restored.total_findings == original.total_findings
    assert restored.total_cost_usd == original.total_cost_usd


# =============================================================================
# ALL_FINDINGS METHOD TESTS
# =============================================================================

def test_all_findings_empty_persona_reports():
    """Test all_findings with no persona reports returns empty list."""
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[],
        disagreements=[],
        total_findings=0,
        total_cost_usd=0.0
    )
    
    result = review.all_findings()
    
    assert result == []
    assert len(result) == 0


def test_all_findings_single_persona_single_finding():
    """Test all_findings with one persona report containing one finding."""
    finding = Finding(
        persona=Persona.red_team,
        severity=Severity.critical,
        dimension=Dimension.security,
        title="Single finding",
        detail="Single detail"
    )
    
    report = PersonaReport(
        persona=Persona.red_team,
        findings=[finding],
        summary="1 finding"
    )
    
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[report],
        disagreements=[],
        total_findings=1,
        total_cost_usd=0.0
    )
    
    result = review.all_findings()
    
    assert len(result) == 1
    assert result[0].title == "Single finding"
    assert result[0].persona == Persona.red_team


def test_all_findings_multiple_personas_multiple_findings():
    """Test all_findings flattens findings from multiple persona reports preserving order."""
    # Create findings for persona 1
    finding1_p1 = Finding(
        persona=Persona.red_team,
        severity=Severity.high,
        dimension=Dimension.security,
        title="P1-F1",
        detail="First finding from red_team"
    )
    finding2_p1 = Finding(
        persona=Persona.red_team,
        severity=Severity.medium,
        dimension=Dimension.injection,
        title="P1-F2",
        detail="Second finding from red_team"
    )
    
    # Create findings for persona 2
    finding1_p2 = Finding(
        persona=Persona.sage,
        severity=Severity.low,
        dimension=Dimension.design,
        title="P2-F1",
        detail="First finding from sage"
    )
    finding2_p2 = Finding(
        persona=Persona.sage,
        severity=Severity.info,
        dimension=Dimension.concept,
        title="P2-F2",
        detail="Second finding from sage"
    )
    
    # Create findings for persona 3
    finding1_p3 = Finding(
        persona=Persona.user,
        severity=Severity.medium,
        dimension=Dimension.edge_cases,
        title="P3-F1",
        detail="First finding from user"
    )
    finding2_p3 = Finding(
        persona=Persona.user,
        severity=Severity.low,
        dimension=Dimension.failure_modes,
        title="P3-F2",
        detail="Second finding from user"
    )
    
    # Create persona reports
    report1 = PersonaReport(
        persona=Persona.red_team,
        findings=[finding1_p1, finding2_p1],
        summary="2 findings"
    )
    report2 = PersonaReport(
        persona=Persona.sage,
        findings=[finding1_p2, finding2_p2],
        summary="2 findings"
    )
    report3 = PersonaReport(
        persona=Persona.user,
        findings=[finding1_p3, finding2_p3],
        summary="2 findings"
    )
    
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[report1, report2, report3],
        disagreements=[],
        total_findings=6,
        total_cost_usd=0.0
    )
    
    result = review.all_findings()
    
    assert len(result) == 6
    # Verify order is preserved: report1 findings, then report2, then report3
    assert result[0].title == "P1-F1"
    assert result[1].title == "P1-F2"
    assert result[2].title == "P2-F1"
    assert result[3].title == "P2-F2"
    assert result[4].title == "P3-F1"
    assert result[5].title == "P3-F2"


def test_all_findings_persona_with_no_findings():
    """Test all_findings with persona reports that have empty findings lists."""
    report1 = PersonaReport(
        persona=Persona.red_team,
        findings=[],
        summary="No findings"
    )
    report2 = PersonaReport(
        persona=Persona.sage,
        findings=[],
        summary="No findings"
    )
    
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[report1, report2],
        disagreements=[],
        total_findings=0,
        total_cost_usd=0.0
    )
    
    result = review.all_findings()
    
    assert result == []
    assert len(result) == 0


def test_all_findings_mixed_empty_and_populated():
    """Test all_findings with mix of empty and populated findings lists."""
    finding1 = Finding(
        persona=Persona.red_team,
        severity=Severity.high,
        dimension=Dimension.security,
        title="Finding 1",
        detail="Detail 1"
    )
    finding2 = Finding(
        persona=Persona.user,
        severity=Severity.medium,
        dimension=Dimension.edge_cases,
        title="Finding 2",
        detail="Detail 2"
    )
    
    report1 = PersonaReport(
        persona=Persona.red_team,
        findings=[finding1],
        summary="1 finding"
    )
    report2 = PersonaReport(
        persona=Persona.sage,
        findings=[],
        summary="No findings"
    )
    report3 = PersonaReport(
        persona=Persona.user,
        findings=[finding2],
        summary="1 finding"
    )
    report4 = PersonaReport(
        persona=Persona.sme,
        findings=[],
        summary="No findings"
    )
    
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[report1, report2, report3, report4],
        disagreements=[],
        total_findings=2,
        total_cost_usd=0.0
    )
    
    result = review.all_findings()
    
    assert len(result) == 2
    assert result[0].title == "Finding 1"
    assert result[1].title == "Finding 2"
    assert result[0].persona == Persona.red_team
    assert result[1].persona == Persona.user


# =============================================================================
# ADDITIONAL EDGE CASE TESTS
# =============================================================================

def test_all_findings_order_preservation_detailed():
    """Detailed test to verify exact order preservation in all_findings."""
    findings = []
    for i in range(10):
        findings.append(Finding(
            persona=Persona.red_team,
            severity=Severity.info,
            dimension=Dimension.concept,
            title=f"Finding-{i}",
            detail=f"Detail-{i}"
        ))
    
    report = PersonaReport(
        persona=Persona.red_team,
        findings=findings,
        summary="10 findings"
    )
    
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=[report],
        disagreements=[],
        total_findings=10,
        total_cost_usd=0.0
    )
    
    result = review.all_findings()
    
    assert len(result) == 10
    for i in range(10):
        assert result[i].title == f"Finding-{i}", f"Order not preserved at index {i}"


def test_persona_report_with_many_findings():
    """Test PersonaReport can handle many findings."""
    findings = []
    for i in range(100):
        findings.append(Finding(
            persona=Persona.adversarial,
            severity=Severity.low,
            dimension=Dimension.edge_cases,
            title=f"Finding {i}",
            detail=f"Detail {i}"
        ))
    
    report = PersonaReport(
        persona=Persona.adversarial,
        findings=findings,
        summary="100 findings"
    )
    
    assert len(report.findings) == 100


def test_all_findings_with_many_reports():
    """Test all_findings performance with many persona reports."""
    reports = []
    expected_count = 0
    
    for persona in [Persona.red_team, Persona.sage, Persona.user]:
        findings = []
        for i in range(10):
            findings.append(Finding(
                persona=persona,
                severity=Severity.info,
                dimension=Dimension.concept,
                title=f"{persona.name}-{i}",
                detail="Detail"
            ))
            expected_count += 1
        
        reports.append(PersonaReport(
            persona=persona,
            findings=findings,
            summary=f"{len(findings)} findings"
        ))
    
    review = Review(
        review_id="20231215T143022-12345678",
        target="test.py",
        target_type="file",
        started_at="2023-12-15T14:30:22Z",
        completed_at="2023-12-15T14:35:45Z",
        persona_reports=reports,
        disagreements=[],
        total_findings=expected_count,
        total_cost_usd=0.0
    )
    
    result = review.all_findings()
    
    assert len(result) == expected_count
    assert len(result) == 30  # 3 personas * 10 findings each
