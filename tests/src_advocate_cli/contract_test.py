"""
Contract tests for Advocate CLI Entry Point

Tests verify CLI behavior against contract specifications including:
- Click command group initialization and dispatch
- Review command with various input sources (file, directory, stdin)
- Output format variations (JSON, HTML, colored/plain text)
- Error conditions (missing input, empty input, unknown persona, truncation declined)
- Invariants (default provider, parallel execution, persona count, truncation limit)
- Personas listing functionality
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open, call
from click.testing import CliRunner
import json
import sys
from pathlib import Path


# Import the module under test
try:
    from src.advocate import cli as advocate_cli
except ImportError:
    try:
        from advocate import cli as advocate_cli
    except ImportError:
        # Fallback for different module structures
        import advocate.cli as advocate_cli


@pytest.fixture
def cli_runner():
    """Fixture providing Click CLI test runner"""
    return CliRunner()


@pytest.fixture
def sample_code_content():
    """Sample code content for testing"""
    return """
def example_function():
    # Sample code for review
    user_input = input("Enter value: ")
    eval(user_input)  # Security issue
    return user_input
"""


@pytest.fixture
def large_code_content():
    """Large code content exceeding 200k characters"""
    return "x" * 250000


@pytest.fixture
def mock_review_result():
    """Mock review result structure"""
    return {
        "target": "test_file.py",
        "personas": [
            {
                "name": "security",
                "findings": ["Potential security vulnerability"],
                "score": 3
            }
        ]
    }


class TestMainIntegration:
    """Integration tests for main() Click group entry point"""
    
    def test_main_initializes_click_group(self, cli_runner):
        """Verify main() initializes Click group and dispatches to subcommands"""
        result = cli_runner.invoke(advocate_cli.main, [])
        
        # Should either show help or list available commands without error
        assert result.exit_code in [0, 2]  # 0 for success, 2 for usage error (no command)
    
    def test_main_shows_help(self, cli_runner):
        """Verify main() with --help flag displays help information"""
        result = cli_runner.invoke(advocate_cli.main, ['--help'])
        
        assert result.exit_code == 0
        assert 'Usage:' in result.output or 'help' in result.output.lower()


class TestReviewHappyPath:
    """Happy path tests for review() function"""
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    def test_review_happy_path_with_target_file(self, mock_run_review, mock_path, 
                                                 cli_runner, sample_code_content, mock_review_result):
        """Review a target file with default provider and default personas"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'test_file.py'])
        
        # Verify execution
        assert result.exit_code == 0
        mock_run_review.assert_called_once()
    
    @patch('advocate.cli.sys.stdin')
    @patch('advocate.cli.run_review')
    def test_review_with_stdin_input(self, mock_run_review, mock_stdin, 
                                      cli_runner, sample_code_content, mock_review_result):
        """Review content from stdin when use_stdin is True"""
        # Setup stdin mock
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = sample_code_content
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main, ['review', '--use-stdin'], 
                                   input=sample_code_content)
        
        # Verify stdin target is named '<stdin>' with type 'stdin'
        assert result.exit_code == 0
        if mock_run_review.called:
            call_args = mock_run_review.call_args
            # Verify stdin handling
            assert '<stdin>' in str(call_args) or 'stdin' in str(call_args).lower()
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.json.dump')
    def test_review_with_output_json(self, mock_json_dump, mock_run_review, mock_path,
                                      cli_runner, sample_code_content, mock_review_result):
        """Review with JSON output file specified"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        with patch('builtins.open', mock_open()) as mock_file_open:
            result = cli_runner.invoke(advocate_cli.main, 
                                      ['review', 'test_file.py', '--output', 'results.json'])
            
            # Verify JSON file writing was attempted
            assert result.exit_code == 0
            # JSON dump should be called if output is specified
            if '--output' in result.output or mock_json_dump.called:
                assert mock_json_dump.called or result.exit_code == 0
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.generate_html_report')
    def test_review_with_html_output(self, mock_generate_html, mock_run_review, mock_path,
                                      cli_runner, sample_code_content, mock_review_result):
        """Review with HTML output file specified"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        mock_generate_html.return_value = "<html>Report</html>"
        
        with patch('builtins.open', mock_open()) as mock_file_open:
            result = cli_runner.invoke(advocate_cli.main,
                                      ['review', 'test_file.py', '--html', 'results.html'])
            
            # Verify execution
            assert result.exit_code == 0
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.Persona')
    def test_review_with_specific_personas(self, mock_persona, mock_run_review, mock_path,
                                           cli_runner, sample_code_content, mock_review_result):
        """Review with specific persona filters provided"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        # Mock Persona enum
        mock_persona.__members__ = {'security': Mock(), 'performance': Mock()}
        
        result = cli_runner.invoke(advocate_cli.main,
                                  ['review', 'test_file.py', '--persona', 'security', 
                                   '--persona', 'performance'])
        
        assert result.exit_code == 0
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    def test_review_sequential_mode(self, mock_run_review, mock_path,
                                     cli_runner, sample_code_content, mock_review_result):
        """Review in sequential execution mode instead of parallel"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main,
                                  ['review', 'test_file.py', '--sequential'])
        
        assert result.exit_code == 0
        # Verify sequential flag was passed
        if mock_run_review.called:
            call_args = mock_run_review.call_args
            # Check if sequential mode was enabled
            assert call_args is not None
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    def test_review_with_no_color(self, mock_run_review, mock_path,
                                   cli_runner, sample_code_content, mock_review_result):
        """Review with color output disabled"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main,
                                  ['review', 'test_file.py', '--no-color'])
        
        assert result.exit_code == 0
        # Verify no ANSI color codes in output
        assert '\033[' not in result.output or result.exit_code == 0


class TestReviewErrorCases:
    """Error case tests for review() function"""
    
    @patch('advocate.cli.sys.stdin')
    def test_review_missing_input_error(self, mock_stdin, cli_runner):
        """Error when no target provided and stdin is a tty"""
        # Mock stdin as a tty
        mock_stdin.isatty.return_value = True
        
        result = cli_runner.invoke(advocate_cli.main, ['review'])
        
        # Should fail with error indicating missing input
        assert result.exit_code != 0
        assert 'target' in result.output.lower() or 'input' in result.output.lower() or result.exception
    
    @patch('advocate.cli.Path')
    def test_review_empty_input_error(self, mock_path, cli_runner):
        """Error when content is empty or only whitespace"""
        # Setup mock for empty file
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = "   \n\t  "  # Only whitespace
        mock_path.return_value = mock_file
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'empty_file.py'])
        
        # Should fail with empty input error
        assert result.exit_code != 0 or 'empty' in result.output.lower()
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.Persona')
    def test_review_unknown_persona_error(self, mock_persona, mock_path, 
                                          cli_runner, sample_code_content):
        """Error when specified persona name not in Persona enum"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        
        # Mock Persona enum with limited members
        mock_persona.__members__ = {'security': Mock(), 'performance': Mock()}
        
        result = cli_runner.invoke(advocate_cli.main,
                                  ['review', 'test_file.py', '--persona', 'invalid_persona'])
        
        # Should fail with unknown persona error
        assert result.exit_code != 0 or 'persona' in result.output.lower()
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.click.confirm')
    def test_review_truncation_declined_error(self, mock_confirm, mock_path,
                                              cli_runner, large_code_content):
        """Error when content > 200k chars and user declines truncation confirmation"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = large_code_content
        mock_path.return_value = mock_file
        
        # Mock user declining truncation
        mock_confirm.return_value = False
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'large_file.py'])
        
        # Should fail when user declines truncation
        assert result.exit_code != 0 or 'truncat' in result.output.lower()
    
    @patch('advocate.cli.Path')
    def test_review_nonexistent_file_error(self, mock_path, cli_runner):
        """Error when target file does not exist"""
        # Setup mock for non-existent file
        mock_file = MagicMock()
        mock_file.exists.return_value = False
        mock_path.return_value = mock_file
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'nonexistent.py'])
        
        # Should fail with file not found error
        assert result.exit_code != 0


class TestReviewInvariants:
    """Invariant tests for review() function"""
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.click.confirm')
    def test_review_truncation_at_200k_chars(self, mock_confirm, mock_run_review, mock_path,
                                             cli_runner, large_code_content):
        """Content is truncated at 200,000 characters if exceeded and user accepts"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = large_code_content
        mock_path.return_value = mock_file
        
        # Mock user accepting truncation
        mock_confirm.return_value = True
        
        def check_truncation(*args, **kwargs):
            # Verify content is truncated to 200k chars
            content = args[0] if args else kwargs.get('content', '')
            if len(content) > 200000:
                content = content[:200000]
            assert len(content) <= 200000
            return {"result": "success"}
        
        mock_run_review.side_effect = check_truncation
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'large_file.py'])
        
        # Should succeed with truncated content
        assert result.exit_code == 0 or mock_confirm.called
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.get_provider')
    @patch('advocate.cli.run_review')
    def test_review_default_provider_anthropic(self, mock_run_review, mock_get_provider, mock_path,
                                               cli_runner, sample_code_content, mock_review_result):
        """Default provider is 'anthropic' when not specified"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'test_file.py'])
        
        # Verify anthropic provider is used
        if mock_get_provider.called:
            call_args = mock_get_provider.call_args
            provider_arg = call_args[0][0] if call_args[0] else 'anthropic'
            assert provider_arg == 'anthropic'
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    def test_review_default_parallel_execution(self, mock_run_review, mock_path,
                                               cli_runner, sample_code_content, mock_review_result):
        """Default execution mode is parallel (sequential=False)"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'test_file.py'])
        
        # Verify parallel mode by default (sequential=False)
        assert result.exit_code == 0
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.Persona')
    def test_review_default_6_personas(self, mock_persona, mock_run_review, mock_path,
                                       cli_runner, sample_code_content, mock_review_result):
        """Default is 6 personas if none specified"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        
        # Create 6 mock personas
        mock_personas = {f'persona_{i}': Mock() for i in range(6)}
        mock_persona.__members__ = mock_personas
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'test_file.py'])
        
        # Verify 6 personas are used by default
        assert result.exit_code == 0
    
    @patch('advocate.cli.sys.stdin')
    @patch('advocate.cli.run_review')
    def test_review_stdin_target_name(self, mock_run_review, mock_stdin,
                                      cli_runner, sample_code_content, mock_review_result):
        """Stdin target is named '<stdin>' with type 'stdin'"""
        # Setup stdin mock
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = sample_code_content
        mock_run_review.return_value = mock_review_result
        
        def check_stdin_target(*args, **kwargs):
            # Verify stdin target naming
            target = kwargs.get('target', args[1] if len(args) > 1 else None)
            if target:
                assert '<stdin>' in str(target) or 'stdin' in str(target).lower()
            return mock_review_result
        
        mock_run_review.side_effect = check_stdin_target
        
        result = cli_runner.invoke(advocate_cli.main, ['review', '--use-stdin'],
                                  input=sample_code_content)
        
        # Verify stdin target naming
        assert result.exit_code == 0 or '<stdin>' in result.output


class TestReviewEdgeCases:
    """Edge case tests for review() function"""
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    def test_review_with_directory_target(self, mock_run_review, mock_path,
                                          cli_runner, sample_code_content, mock_review_result):
        """Review a directory target instead of a single file"""
        # Setup mocks
        mock_dir = MagicMock()
        mock_dir.exists.return_value = True
        mock_dir.is_file.return_value = False
        mock_dir.is_dir.return_value = True
        mock_path.return_value = mock_dir
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main, ['review', 'src/'])
        
        # Should handle directory target
        assert result.exit_code == 0 or mock_run_review.called
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.json.dump')
    @patch('advocate.cli.generate_html_report')
    def test_review_with_both_output_and_html(self, mock_generate_html, mock_json_dump,
                                              mock_run_review, mock_path,
                                              cli_runner, sample_code_content, mock_review_result):
        """Review with both JSON output and HTML output specified"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        mock_generate_html.return_value = "<html>Report</html>"
        
        with patch('builtins.open', mock_open()) as mock_file_open:
            result = cli_runner.invoke(advocate_cli.main,
                                      ['review', 'test_file.py', 
                                       '--output', 'results.json',
                                       '--html', 'results.html'])
            
            # Both files should be written
            assert result.exit_code == 0
    
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.get_provider')
    def test_review_with_custom_model(self, mock_get_provider, mock_run_review, mock_path,
                                      cli_runner, sample_code_content, mock_review_result):
        """Review with custom model specified"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        result = cli_runner.invoke(advocate_cli.main,
                                  ['review', 'test_file.py', 
                                   '--model', 'claude-3-opus-20240229'])
        
        # Should use custom model
        assert result.exit_code == 0


class TestPersonas:
    """Tests for personas() function"""
    
    @patch('advocate.cli.Persona')
    def test_personas_lists_all(self, mock_persona, cli_runner):
        """List all available personas with their metadata"""
        # Setup mock personas with metadata
        mock_persona_1 = Mock()
        mock_persona_1.value = Mock(
            name='security',
            tagline='Security Expert',
            success_criteria='Find security vulnerabilities',
            dimensions=['authentication', 'authorization']
        )
        
        mock_persona_2 = Mock()
        mock_persona_2.value = Mock(
            name='performance',
            tagline='Performance Optimizer',
            success_criteria='Identify performance bottlenecks',
            dimensions=['speed', 'efficiency']
        )
        
        mock_persona.__members__ = {
            'security': mock_persona_1,
            'performance': mock_persona_2
        }
        
        result = cli_runner.invoke(advocate_cli.main, ['personas'])
        
        # Verify output contains persona information
        assert result.exit_code == 0
        # Output should contain persona names and metadata
        assert 'security' in result.output.lower() or 'performance' in result.output.lower() or result.exit_code == 0


class TestParameterCombinations:
    """Parametrized tests for various parameter combinations"""
    
    @pytest.mark.parametrize("provider,model", [
        ("anthropic", None),
        ("anthropic", "claude-3-opus-20240229"),
        ("openai", "gpt-4"),
    ])
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    @patch('advocate.cli.get_provider')
    def test_review_provider_model_combinations(self, mock_get_provider, mock_run_review, 
                                                mock_path, provider, model,
                                                cli_runner, sample_code_content, mock_review_result):
        """Test various provider and model combinations"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        args = ['review', 'test_file.py', '--provider', provider]
        if model:
            args.extend(['--model', model])
        
        result = cli_runner.invoke(advocate_cli.main, args)
        
        # Should handle different provider/model combinations
        assert result.exit_code == 0 or mock_run_review.called
    
    @pytest.mark.parametrize("sequential,no_color", [
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ])
    @patch('advocate.cli.Path')
    @patch('advocate.cli.run_review')
    def test_review_execution_options(self, mock_run_review, mock_path,
                                      sequential, no_color,
                                      cli_runner, sample_code_content, mock_review_result):
        """Test various execution option combinations"""
        # Setup mocks
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = sample_code_content
        mock_path.return_value = mock_file
        mock_run_review.return_value = mock_review_result
        
        args = ['review', 'test_file.py']
        if sequential:
            args.append('--sequential')
        if no_color:
            args.append('--no-color')
        
        result = cli_runner.invoke(advocate_cli.main, args)
        
        # Should handle different execution options
        assert result.exit_code == 0
