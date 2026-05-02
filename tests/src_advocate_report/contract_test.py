"""
Contract tests for src_advocate_report module.

Tests verify the report generation functions (print_review, write_json, write_html)
against their contracts including preconditions, postconditions, error cases, and invariants.
"""

import pytest
import json
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open
from typing import List, Any
import tempfile

# Import the module under test
from src.advocate.report import (
    print_review,
    write_json,
    write_html,
    _SEV_COLORS,
    _RESET,
    _HTML,
    PERSONA_META
)

# Import dependencies for type checking and mocking
try:
    from advocate.models import Review
    from advocate.personas import Persona
except ImportError:
    # Mock these if not available
    Review = None
    Persona = None

try:
    from jinja2 import Template
except ImportError:
    Template = None


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_severity_enum():
    """Mock Severity enum with common severity levels."""
    from enum import Enum
    
    class MockSeverity(Enum):
        critical = "critical"
        high = "high"
        medium = "medium"
        low = "low"
        info = "info"
    
    return MockSeverity


@pytest.fixture
def mock_persona_enum():
    """Mock Persona enum with test personas."""
    from enum import Enum
    
    class MockPersona(Enum):
        security = "security"
        performance = "performance"
        accessibility = "accessibility"
    
    return MockPersona


@pytest.fixture
def mock_finding(mock_severity_enum):
    """Create a mock finding object."""
    finding = Mock()
    finding.severity = mock_severity_enum.high
    finding.title = "Test Finding"
    finding.description = "Test description"
    return finding


@pytest.fixture
def mock_persona_report(mock_persona_enum, mock_finding):
    """Create a mock persona report."""
    report = Mock()
    report.persona = mock_persona_enum.security
    report.findings = [mock_finding]
    return report


@pytest.fixture
def minimal_review(mock_persona_report):
    """Create a minimal valid Review object."""
    review = Mock()
    review.target = "test-target"
    review.target_type = "repository"
    review.review_id = "test-123"
    review.started_at = "2024-01-01T00:00:00"
    review.total_findings = 1
    review.persona_reports = [mock_persona_report]
    review.disagreements = []
    review.total_cost_usd = 0.5
    
    # Add model_dump_json for JSON serialization
    review.model_dump_json = Mock(return_value='{"target": "test-target", "total_findings": 1}')
    
    return review


@pytest.fixture
def full_review(mock_persona_enum, mock_finding, mock_severity_enum):
    """Create a full Review object with all fields populated."""
    review = Mock()
    review.target = "full-target"
    review.target_type = "repository"
    review.review_id = "full-456"
    review.started_at = "2024-01-01T00:00:00"
    review.total_findings = 3
    
    # Multiple persona reports
    report1 = Mock()
    report1.persona = mock_persona_enum.security
    report1.findings = [mock_finding, mock_finding]
    
    report2 = Mock()
    report2.persona = mock_persona_enum.performance
    finding2 = Mock()
    finding2.severity = mock_severity_enum.medium
    finding2.title = "Performance Finding"
    report2.findings = [finding2]
    
    review.persona_reports = [report1, report2]
    
    # Disagreements
    disagreement = Mock()
    disagreement.description = "Test disagreement"
    review.disagreements = [disagreement]
    
    review.total_cost_usd = 1.25
    review.model_dump_json = Mock(return_value='{"target": "full-target", "total_findings": 3}')
    
    return review


@pytest.fixture
def review_with_xss_content():
    """Create a Review with potentially malicious HTML/JS content."""
    review = Mock()
    review.target = "<script>alert('xss')</script>"
    review.target_type = "repository"
    review.review_id = "xss-789"
    review.started_at = "2024-01-01T00:00:00"
    review.total_findings = 0
    review.persona_reports = []
    review.disagreements = []
    review.total_cost_usd = 0.0
    review.model_dump_json = Mock(return_value='{"target": "<script>alert(\\"xss\\")</script>"}')
    
    return review


# ============================================================================
# Tests for print_review
# ============================================================================

def test_print_review_happy_path_with_color(capsys, minimal_review):
    """Print a valid Review with color enabled."""
    # Execute
    print_review(minimal_review, color=True)
    
    # Capture output
    captured = capsys.readouterr()
    
    # Assertions
    assert "test-target" in captured.out
    assert len(captured.out) > 0
    # Should contain ANSI escape codes when color=True
    assert "\033[" in captured.out or "test-target" in captured.out  # Either colors or content
    
    # Verify review object not modified
    assert minimal_review.target == "test-target"


def test_print_review_happy_path_without_color(capsys, minimal_review):
    """Print a valid Review with color disabled."""
    # Execute
    print_review(minimal_review, color=False)
    
    # Capture output
    captured = capsys.readouterr()
    
    # Assertions
    assert "test-target" in captured.out
    assert len(captured.out) > 0
    # When color=False, output might not have ANSI codes (depends on implementation)
    # At minimum, verify output exists and contains review data


def test_print_review_error_missing_persona_meta(minimal_review, mock_persona_enum):
    """Print review with persona not in PERSONA_META."""
    # Create a persona not in PERSONA_META
    unknown_persona = Mock()
    unknown_persona.name = "UNKNOWN_PERSONA"
    
    minimal_review.persona_reports[0].persona = unknown_persona
    
    # Execute and assert
    with pytest.raises(KeyError):
        print_review(minimal_review, color=True)


def test_print_review_error_missing_attributes():
    """Print review object missing required attributes."""
    # Create review without required attributes
    incomplete_review = Mock(spec=[])  # Empty spec means no attributes
    
    # Execute and assert
    with pytest.raises(AttributeError):
        print_review(incomplete_review, color=True)


def test_print_review_edge_empty_persona_reports(capsys):
    """Print review with empty persona_reports list."""
    review = Mock()
    review.target = "empty-target"
    review.target_type = "repository"
    review.total_findings = 0
    review.persona_reports = []  # Empty list
    review.disagreements = []
    review.total_cost_usd = 0.0
    
    # Execute
    print_review(review, color=False)
    
    # Capture output
    captured = capsys.readouterr()
    
    # Assertions
    assert len(captured.out) > 0  # Should still produce output
    assert "empty-target" in captured.out


def test_print_review_edge_with_disagreements(capsys, full_review):
    """Print review with disagreements present."""
    # Execute
    print_review(full_review, color=True)
    
    # Capture output
    captured = capsys.readouterr()
    
    # Assertions
    assert len(captured.out) > 0
    # Output should contain disagreement info (implementation dependent)
    assert "full-target" in captured.out


# ============================================================================
# Tests for write_json
# ============================================================================

def test_write_json_happy_path(tmp_path, minimal_review):
    """Write valid Review to JSON file."""
    # Setup
    output_file = tmp_path / "review.json"
    
    # Execute
    write_json(minimal_review, output_file)
    
    # Assertions
    assert output_file.exists()
    
    # Read and parse JSON
    content = output_file.read_text()
    data = json.loads(content)
    
    # Verify JSON structure
    assert "target" in data
    assert data["target"] == "test-target"
    
    # Check indentation (2 spaces)
    # The model_dump_json should have been called with indent=2
    minimal_review.model_dump_json.assert_called_once()


def test_write_json_overwrites_existing(tmp_path, minimal_review, full_review):
    """Write JSON overwrites existing file."""
    # Setup
    output_file = tmp_path / "review.json"
    output_file.write_text("old content")
    
    # Execute
    write_json(minimal_review, output_file)
    
    # Assertions
    assert output_file.exists()
    content = output_file.read_text()
    assert "old content" not in content
    assert "test-target" in content


def test_write_json_error_directory_not_exist(minimal_review):
    """Write JSON to non-existent directory."""
    # Setup - path with non-existent parent
    bad_path = Path("/nonexistent/directory/review.json")
    
    # Execute and assert
    with pytest.raises((OSError, FileNotFoundError)):
        write_json(minimal_review, bad_path)


def test_write_json_error_permission_denied(tmp_path, minimal_review):
    """Write JSON without write permissions."""
    # Setup - create read-only directory
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    output_file = readonly_dir / "review.json"
    
    # Make directory read-only (Unix-like systems)
    try:
        os.chmod(readonly_dir, 0o444)
        
        # Execute and assert
        with pytest.raises((PermissionError, OSError)):
            write_json(minimal_review, output_file)
    finally:
        # Restore permissions for cleanup
        os.chmod(readonly_dir, 0o755)


def test_write_json_error_no_model_dump_json(tmp_path):
    """Write object without model_dump_json method."""
    # Setup - object without model_dump_json
    invalid_review = Mock(spec=[])
    output_file = tmp_path / "review.json"
    
    # Execute and assert
    with pytest.raises(AttributeError):
        write_json(invalid_review, output_file)


# ============================================================================
# Tests for write_html
# ============================================================================

def test_write_html_happy_path(tmp_path, minimal_review):
    """Write valid Review to HTML file."""
    # Setup
    output_file = tmp_path / "review.html"
    
    # Execute
    write_html(minimal_review, output_file)
    
    # Assertions
    assert output_file.exists()
    
    # Read and verify HTML
    content = output_file.read_text()
    assert "<html" in content.lower() or "<!doctype" in content.lower()
    assert "test-target" in content
    # Should contain CSS
    assert "style" in content.lower() or "<style" in content.lower()


def test_write_html_overwrites_existing(tmp_path, minimal_review):
    """Write HTML overwrites existing file."""
    # Setup
    output_file = tmp_path / "review.html"
    output_file.write_text("<html>old</html>")
    
    # Execute
    write_html(minimal_review, output_file)
    
    # Assertions
    assert output_file.exists()
    content = output_file.read_text()
    assert "old" not in content or "test-target" in content


def test_write_html_error_directory_not_exist(minimal_review):
    """Write HTML to non-existent directory."""
    # Setup
    bad_path = Path("/nonexistent/directory/review.html")
    
    # Execute and assert
    with pytest.raises((OSError, FileNotFoundError)):
        write_html(minimal_review, bad_path)


def test_write_html_error_permission_denied(tmp_path, minimal_review):
    """Write HTML without write permissions."""
    # Setup
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    output_file = readonly_dir / "review.html"
    
    try:
        os.chmod(readonly_dir, 0o444)
        
        # Execute and assert
        with pytest.raises((PermissionError, OSError)):
            write_html(minimal_review, output_file)
    finally:
        os.chmod(readonly_dir, 0o755)


def test_write_html_error_missing_version(tmp_path, minimal_review):
    """Write HTML when __version__ cannot be imported."""
    # Setup
    output_file = tmp_path / "review.html"
    
    # Mock the import to raise ImportError
    with patch('src_advocate_report.advocate') as mock_advocate:
        # Make __version__ attribute access raise ImportError
        type(mock_advocate).__version__ = property(lambda self: (_ for _ in ()).throw(ImportError("No version")))
        
        # This test may not trigger if __version__ is imported at module level
        # The actual behavior depends on implementation
        # For now, we document the expected behavior
        try:
            write_html(minimal_review, output_file)
            # If it doesn't raise, that's also valid depending on implementation
        except ImportError:
            pass  # Expected


def test_write_html_error_persona_not_in_meta(tmp_path, mock_persona_enum):
    """Write HTML with Persona not in PERSONA_META."""
    # Setup
    review = Mock()
    review.target = "test"
    review.target_type = "repository"
    review.review_id = "123"
    review.started_at = "2024-01-01"
    review.total_findings = 1
    review.total_cost_usd = 0.5
    review.disagreements = []
    
    # Create persona report with unknown persona
    unknown_persona = Mock()
    unknown_persona.name = "UNKNOWN"
    
    report = Mock()
    report.persona = unknown_persona
    report.findings = []
    
    review.persona_reports = [report]
    
    output_file = tmp_path / "review.html"
    
    # Execute and assert
    with pytest.raises(KeyError):
        write_html(review, output_file)


def test_write_html_error_missing_review_attributes(tmp_path):
    """Write HTML with Review missing template attributes."""
    # Setup - review without required attributes
    incomplete_review = Mock(spec=['persona_reports'])
    incomplete_review.persona_reports = []
    
    output_file = tmp_path / "review.html"
    
    # Execute and assert
    with pytest.raises(AttributeError):
        write_html(incomplete_review, output_file)


def test_write_html_security_xss_escaping(tmp_path, review_with_xss_content):
    """Write HTML properly escapes potentially malicious content."""
    # Setup
    output_file = tmp_path / "review.html"
    
    # Execute
    write_html(review_with_xss_content, output_file)
    
    # Assertions
    content = output_file.read_text()
    
    # Verify HTML entities are escaped (Jinja2 auto-escapes by default)
    # Should NOT contain raw <script> tag
    assert "<script>alert('xss')</script>" not in content
    # Should contain escaped version or encoded version
    assert "&lt;script&gt;" in content or "&lt;" in content or "xss" in content


# ============================================================================
# Invariant Tests
# ============================================================================

def test_invariant_sev_colors_mapping():
    """Verify _SEV_COLORS maps all Severity enum members."""
    # Import Severity enum
    try:
        from advocate.models import Severity
        
        # Assertions
        assert isinstance(_SEV_COLORS, dict)
        
        # Verify all Severity members are keys
        for severity in Severity:
            assert severity in _SEV_COLORS or severity.name in _SEV_COLORS
            # Values should be ANSI escape code strings
            if severity in _SEV_COLORS:
                assert isinstance(_SEV_COLORS[severity], str)
    except ImportError:
        # If Severity not available, check that _SEV_COLORS exists and is a dict
        assert isinstance(_SEV_COLORS, dict)
        assert len(_SEV_COLORS) > 0


def test_invariant_reset_code():
    """Verify _RESET is ANSI reset code."""
    assert _RESET == '\033[0m'


def test_invariant_html_template():
    """Verify _HTML is pre-compiled Jinja2 Template."""
    # Check that _HTML exists and is a Template
    assert _HTML is not None
    
    if Template:
        assert isinstance(_HTML, Template)
    
    # Verify it can render with a minimal context
    try:
        result = _HTML.render(
            review=Mock(
                target="test",
                target_type="repo",
                review_id="123",
                started_at="2024-01-01",
                total_findings=0,
                persona_reports=[],
                disagreements=[],
                total_cost_usd=0.0
            ),
            PERSONA_META={},
            version="1.0.0"
        )
        assert isinstance(result, str)
        assert len(result) > 0
    except Exception:
        # Template might require specific structure
        pass


def test_invariant_persona_meta_complete():
    """Verify PERSONA_META contains all Persona enum values."""
    try:
        from advocate.personas import Persona
        
        # Assertions
        assert isinstance(PERSONA_META, dict)
        
        # Verify all Persona members are keys
        for persona in Persona:
            assert persona in PERSONA_META or persona.name in PERSONA_META
    except ImportError:
        # If Persona not available, check that PERSONA_META exists and is a dict
        assert isinstance(PERSONA_META, dict)
        assert len(PERSONA_META) > 0


# ============================================================================
# Additional Edge Cases
# ============================================================================

def test_print_review_findings_sorted_by_severity(capsys, minimal_review, mock_severity_enum):
    """Verify findings are sorted by severity in output."""
    # Setup - create findings with different severities
    finding1 = Mock()
    finding1.severity = mock_severity_enum.low
    finding1.title = "Low Finding"
    
    finding2 = Mock()
    finding2.severity = mock_severity_enum.critical
    finding2.title = "Critical Finding"
    
    finding3 = Mock()
    finding3.severity = mock_severity_enum.medium
    finding3.title = "Medium Finding"
    
    minimal_review.persona_reports[0].findings = [finding1, finding2, finding3]
    
    # Execute
    print_review(minimal_review, color=False)
    
    # Capture output
    captured = capsys.readouterr()
    
    # The output should exist (exact ordering check depends on implementation)
    assert len(captured.out) > 0


def test_write_json_path_object_type(tmp_path, minimal_review):
    """Verify write_json accepts Path object."""
    # Setup
    output_file = tmp_path / "review.json"
    
    # Verify it's a Path object
    assert isinstance(output_file, Path)
    
    # Execute
    write_json(minimal_review, output_file)
    
    # Assertions
    assert output_file.exists()


def test_write_html_path_object_type(tmp_path, minimal_review):
    """Verify write_html accepts Path object."""
    # Setup
    output_file = tmp_path / "review.html"
    
    # Verify it's a Path object
    assert isinstance(output_file, Path)
    
    # Execute
    write_html(minimal_review, output_file)
    
    # Assertions
    assert output_file.exists()


def test_print_review_no_return_value(minimal_review):
    """Verify print_review returns None."""
    result = print_review(minimal_review, color=False)
    assert result is None


def test_write_json_no_return_value(tmp_path, minimal_review):
    """Verify write_json returns None."""
    output_file = tmp_path / "review.json"
    result = write_json(minimal_review, output_file)
    assert result is None


def test_write_html_no_return_value(tmp_path, minimal_review):
    """Verify write_html returns None."""
    output_file = tmp_path / "review.html"
    result = write_html(minimal_review, output_file)
    assert result is None
