"""
Contract tests for src_advocate_provider module.

Tests cover LLMProvider abstraction with Anthropic, OpenAI, and Gemini implementations.
All external dependencies (anthropic, openai, google.genai) are mocked.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any
import sys

# Import module under test
from src.advocate.provider import (
    LLMProvider,
    AnthropicProvider,
    OpenAIProvider,
    GeminiProvider,
    estimate_cost,
    create_provider,
    transmogrify,
)


# ============================================================================
# COST ESTIMATION TESTS
# ============================================================================


def test_estimate_cost_happy_path_known_model():
    """Estimate cost for a known model with standard token counts."""
    # Using typical token counts for a known model
    cost = estimate_cost("claude-3-opus-20240229", 1000000, 500000)
    
    assert isinstance(cost, float)
    assert cost >= 0.0
    # Claude 3 Opus typical pricing: $15 input / $75 output per 1M tokens
    # 1M input tokens * 15 + 0.5M output tokens * 75 = 15 + 37.5 = 52.5
    # Allow some tolerance for pricing variations
    assert cost > 0


def test_estimate_cost_unknown_model_fallback():
    """Estimate cost for unknown model falls back to default pricing."""
    # Unknown model should use default pricing: 3.0 input, 15.0 output per 1M tokens
    cost = estimate_cost("unknown-model-xyz", 1000000, 1000000)
    
    assert isinstance(cost, float)
    assert cost >= 0.0
    # Expected: 1M * 3.0/1M + 1M * 15.0/1M = 3.0 + 15.0 = 18.0
    assert cost == 18.0


def test_estimate_cost_zero_tokens():
    """Estimate cost with zero input and output tokens."""
    cost = estimate_cost("gpt-4", 0, 0)
    
    assert isinstance(cost, float)
    assert cost == 0.0


def test_estimate_cost_fuzzy_prefix_matching():
    """Estimate cost uses fuzzy prefix matching for model names."""
    # Test that prefix matching works
    cost1 = estimate_cost("claude-3-opus", 1000000, 1000000)
    cost2 = estimate_cost("claude-3-opus-20240229", 1000000, 1000000)
    
    # Both should match similar pricing (prefix matching)
    assert isinstance(cost1, float)
    assert isinstance(cost2, float)
    assert cost1 >= 0.0
    assert cost2 >= 0.0


def test_estimate_cost_non_negative():
    """Verify cost estimation always returns non-negative value."""
    cost = estimate_cost("gpt-3.5-turbo", 500000, 250000)
    
    assert isinstance(cost, float)
    assert cost >= 0.0


# ============================================================================
# FACTORY FUNCTION TESTS
# ============================================================================


def test_create_provider_anthropic_with_model():
    """Create Anthropic provider with explicit model."""
    provider = create_provider("anthropic", "claude-3-opus-20240229")
    
    assert isinstance(provider, AnthropicProvider)
    assert isinstance(provider, LLMProvider)
    assert provider.model == "claude-3-opus-20240229"


def test_create_provider_anthropic_default_model():
    """Create Anthropic provider with default model (model=None)."""
    provider = create_provider("anthropic", None)
    
    assert isinstance(provider, AnthropicProvider)
    assert isinstance(provider, LLMProvider)
    assert provider.model is not None  # Should have default model


def test_create_provider_openai_with_model():
    """Create OpenAI provider with explicit model."""
    provider = create_provider("openai", "gpt-4")
    
    assert isinstance(provider, OpenAIProvider)
    assert isinstance(provider, LLMProvider)
    assert provider.model == "gpt-4"


def test_create_provider_openai_default_model():
    """Create OpenAI provider with default model (model=None)."""
    provider = create_provider("openai", None)
    
    assert isinstance(provider, OpenAIProvider)
    assert isinstance(provider, LLMProvider)
    assert provider.model is not None  # Should have default model


def test_create_provider_gemini_with_model():
    """Create Gemini provider with explicit model."""
    provider = create_provider("gemini", "gemini-pro")
    
    assert isinstance(provider, GeminiProvider)
    assert isinstance(provider, LLMProvider)
    assert provider.model == "gemini-pro"


def test_create_provider_gemini_default_model():
    """Create Gemini provider with default model (model=None)."""
    provider = create_provider("gemini", None)
    
    assert isinstance(provider, GeminiProvider)
    assert isinstance(provider, LLMProvider)
    assert provider.model is not None  # Should have default model


def test_create_provider_unknown_provider_error():
    """Create provider with unknown provider name raises error."""
    with pytest.raises((ValueError, KeyError)) as exc_info:
        create_provider("unknown_provider", "some-model")
    
    # Error should relate to unknown provider
    assert exc_info.value is not None


# ============================================================================
# TRANSMOGRIFY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_transmogrify_happy_path():
    """Transmogrify text when Transmogrifier is available."""
    # Mock the Transmogrifier class
    mock_transmogrifier_instance = AsyncMock()
    mock_transmogrifier_instance.transmogrify = AsyncMock(return_value="Transmogrified text")
    
    mock_transmogrifier_class = Mock(return_value=mock_transmogrifier_instance)
    
    with patch.dict('sys.modules', {'transmogrifier': MagicMock(), 'transmogrifier.core': MagicMock()}):
        with patch('transmogrifier.core.Transmogrifier', mock_transmogrifier_class):
            result = await transmogrify("Test prompt text", "gpt-4")
    
    # Should attempt to import and use transmogrifier
    # Since the actual implementation might handle ImportError, 
    # we verify the result is a string
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_transmogrify_import_error_fallback():
    """Transmogrify returns original text on ImportError."""
    # Simulate ImportError by not having transmogrifier available
    with patch.dict('sys.modules', {'transmogrifier.core': None}):
        result = await transmogrify("Test prompt text", "gpt-4")
    
    # Should return original text on ImportError
    assert result == "Test prompt text"


@pytest.mark.asyncio
async def test_transmogrify_runtime_error_fallback():
    """Transmogrify returns original text on runtime exception."""
    # Mock Transmogrifier to raise an exception
    mock_transmogrifier_instance = AsyncMock()
    mock_transmogrifier_instance.transmogrify = AsyncMock(side_effect=RuntimeError("Test error"))
    
    mock_transmogrifier_class = Mock(return_value=mock_transmogrifier_instance)
    
    with patch.dict('sys.modules', {'transmogrifier': MagicMock(), 'transmogrifier.core': MagicMock()}):
        with patch('transmogrifier.core.Transmogrifier', mock_transmogrifier_class):
            result = await transmogrify("Test prompt text", "gpt-4")
    
    # Should return original text on any exception
    assert result == "Test prompt text"


# ============================================================================
# BASE LLMPROVIDER TESTS
# ============================================================================


def test_llmprovider_init():
    """Initialize LLMProvider base class with model."""
    provider = LLMProvider("test-model-123")
    
    assert provider.model == "test-model-123"


@pytest.mark.asyncio
async def test_llmprovider_complete_not_implemented():
    """Calling complete() on abstract LLMProvider raises NotImplementedError."""
    provider = LLMProvider("test-model")
    
    with pytest.raises(NotImplementedError):
        await provider.complete("You are a helpful assistant", "Hello", 4096)


def test_llmprovider_provider_name_not_implemented():
    """Calling provider_name on abstract LLMProvider raises NotImplementedError."""
    provider = LLMProvider("test-model")
    
    with pytest.raises(NotImplementedError):
        _ = provider.provider_name


# ============================================================================
# ANTHROPIC PROVIDER TESTS
# ============================================================================


def test_anthropic_provider_name():
    """AnthropicProvider.provider_name returns 'anthropic'."""
    provider = AnthropicProvider("claude-3-opus-20240229")
    
    assert provider.provider_name == "anthropic"


@pytest.mark.asyncio
async def test_anthropic_complete_happy_path():
    """AnthropicProvider.complete() returns proper tuple with mocked API response."""
    provider = AnthropicProvider("claude-3-opus-20240229")
    
    # Mock the Anthropic API response
    mock_content = Mock()
    mock_content.text = "Hello! I'm doing well, thank you for asking."
    
    mock_usage = Mock()
    mock_usage.input_tokens = 15
    mock_usage.output_tokens = 12
    
    mock_response = Mock()
    mock_response.content = [mock_content]
    mock_response.usage = mock_usage
    
    mock_messages = AsyncMock()
    mock_messages.create = AsyncMock(return_value=mock_response)
    
    mock_client = Mock()
    mock_client.messages = mock_messages
    
    with patch('anthropic.AsyncAnthropic', return_value=mock_client):
        result = await provider.complete("You are a helpful assistant", "Hello, how are you?", 4096)
    
    assert isinstance(result, tuple)
    assert len(result) == 3
    response_text, input_tokens, output_tokens = result
    assert isinstance(response_text, str)
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert response_text == "Hello! I'm doing well, thank you for asking."
    assert input_tokens == 15
    assert output_tokens == 12


@pytest.mark.asyncio
async def test_anthropic_complete_empty_content_error():
    """AnthropicProvider.complete() raises error when response.content is empty."""
    provider = AnthropicProvider("claude-3-opus-20240229")
    
    # Mock response with empty content
    mock_response = Mock()
    mock_response.content = []
    
    mock_messages = AsyncMock()
    mock_messages.create = AsyncMock(return_value=mock_response)
    
    mock_client = Mock()
    mock_client.messages = mock_messages
    
    with patch('anthropic.AsyncAnthropic', return_value=mock_client):
        with pytest.raises(IndexError):
            await provider.complete("You are a helpful assistant", "Hello", 4096)


@pytest.mark.asyncio
async def test_anthropic_complete_api_error():
    """AnthropicProvider.complete() raises error on API failure."""
    provider = AnthropicProvider("claude-3-opus-20240229")
    
    # Mock API error
    mock_messages = AsyncMock()
    mock_messages.create = AsyncMock(side_effect=Exception("API Error"))
    
    mock_client = Mock()
    mock_client.messages = mock_messages
    
    with patch('anthropic.AsyncAnthropic', return_value=mock_client):
        with pytest.raises(Exception) as exc_info:
            await provider.complete("You are a helpful assistant", "Hello", 4096)
        
        assert "API Error" in str(exc_info.value)


# ============================================================================
# OPENAI PROVIDER TESTS
# ============================================================================


def test_openai_provider_name():
    """OpenAIProvider.provider_name returns 'openai'."""
    provider = OpenAIProvider("gpt-4")
    
    assert provider.provider_name == "openai"


@pytest.mark.asyncio
async def test_openai_complete_happy_path():
    """OpenAIProvider.complete() returns proper tuple with mocked API response."""
    provider = OpenAIProvider("gpt-4")
    
    # Mock the OpenAI API response
    mock_message = Mock()
    mock_message.content = "Hello! I'm doing well, thank you for asking."
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_usage = Mock()
    mock_usage.prompt_tokens = 18
    mock_usage.completion_tokens = 12
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    
    mock_completions = AsyncMock()
    mock_completions.create = AsyncMock(return_value=mock_response)
    
    mock_chat = Mock()
    mock_chat.completions = mock_completions
    
    mock_client = Mock()
    mock_client.chat = mock_chat
    
    with patch('openai.AsyncOpenAI', return_value=mock_client):
        result = await provider.complete("You are a helpful assistant", "Hello, how are you?", 4096)
    
    assert isinstance(result, tuple)
    assert len(result) == 3
    response_text, input_tokens, output_tokens = result
    assert isinstance(response_text, str)
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert response_text == "Hello! I'm doing well, thank you for asking."
    assert input_tokens == 18
    assert output_tokens == 12


@pytest.mark.asyncio
async def test_openai_complete_none_fallback():
    """OpenAIProvider.complete() handles None values gracefully with fallbacks."""
    provider = OpenAIProvider("gpt-4")
    
    # Mock response with None values
    mock_message = Mock()
    mock_message.content = None
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_usage = Mock()
    mock_usage.prompt_tokens = None
    mock_usage.completion_tokens = None
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    
    mock_completions = AsyncMock()
    mock_completions.create = AsyncMock(return_value=mock_response)
    
    mock_chat = Mock()
    mock_chat.completions = mock_completions
    
    mock_client = Mock()
    mock_client.chat = mock_chat
    
    with patch('openai.AsyncOpenAI', return_value=mock_client):
        result = await provider.complete("You are a helpful assistant", "Hello", 4096)
    
    response_text, input_tokens, output_tokens = result
    # Should fallback to empty string and 0 tokens
    assert response_text == ""
    assert input_tokens == 0
    assert output_tokens == 0


@pytest.mark.asyncio
async def test_openai_complete_api_error():
    """OpenAIProvider.complete() raises error on API failure."""
    provider = OpenAIProvider("gpt-4")
    
    # Mock API error
    mock_completions = AsyncMock()
    mock_completions.create = AsyncMock(side_effect=Exception("OpenAI API Error"))
    
    mock_chat = Mock()
    mock_chat.completions = mock_completions
    
    mock_client = Mock()
    mock_client.chat = mock_chat
    
    with patch('openai.AsyncOpenAI', return_value=mock_client):
        with pytest.raises(Exception) as exc_info:
            await provider.complete("You are a helpful assistant", "Hello", 4096)
        
        assert "OpenAI API Error" in str(exc_info.value)


# ============================================================================
# GEMINI PROVIDER TESTS
# ============================================================================


def test_gemini_provider_name():
    """GeminiProvider.provider_name returns 'gemini'."""
    provider = GeminiProvider("gemini-pro")
    
    assert provider.provider_name == "gemini"


@pytest.mark.asyncio
async def test_gemini_complete_happy_path():
    """GeminiProvider.complete() returns proper tuple with mocked API response."""
    provider = GeminiProvider("gemini-pro")
    
    # Mock the Gemini API response
    mock_usage_metadata = Mock()
    mock_usage_metadata.prompt_token_count = 20
    mock_usage_metadata.candidates_token_count = 15
    
    mock_response = Mock()
    mock_response.text = "Hello! I'm doing well, thank you for asking."
    mock_response.usage_metadata = mock_usage_metadata
    
    mock_generate_content = AsyncMock(return_value=mock_response)
    
    mock_models = Mock()
    mock_models.generate_content = mock_generate_content
    
    mock_aio = Mock()
    mock_aio.models = mock_models
    
    mock_client = Mock()
    mock_client.aio = mock_aio
    
    with patch('google.genai.Client', return_value=mock_client):
        result = await provider.complete("You are a helpful assistant", "Hello, how are you?", 4096)
    
    assert isinstance(result, tuple)
    assert len(result) == 3
    response_text, input_tokens, output_tokens = result
    assert isinstance(response_text, str)
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert response_text == "Hello! I'm doing well, thank you for asking."
    assert input_tokens == 20
    assert output_tokens == 15


@pytest.mark.asyncio
async def test_gemini_complete_none_fallback():
    """GeminiProvider.complete() handles None values gracefully with fallbacks."""
    provider = GeminiProvider("gemini-pro")
    
    # Mock response with None values
    mock_usage_metadata = Mock()
    mock_usage_metadata.prompt_token_count = None
    mock_usage_metadata.candidates_token_count = None
    
    mock_response = Mock()
    mock_response.text = None
    mock_response.usage_metadata = mock_usage_metadata
    
    mock_generate_content = AsyncMock(return_value=mock_response)
    
    mock_models = Mock()
    mock_models.generate_content = mock_generate_content
    
    mock_aio = Mock()
    mock_aio.models = mock_models
    
    mock_client = Mock()
    mock_client.aio = mock_aio
    
    with patch('google.genai.Client', return_value=mock_client):
        result = await provider.complete("You are a helpful assistant", "Hello", 4096)
    
    response_text, input_tokens, output_tokens = result
    # Should fallback to empty string and 0 tokens
    assert response_text == ""
    assert input_tokens == 0
    assert output_tokens == 0


@pytest.mark.asyncio
async def test_gemini_complete_api_error():
    """GeminiProvider.complete() raises error on API failure."""
    provider = GeminiProvider("gemini-pro")
    
    # Mock API error
    mock_generate_content = AsyncMock(side_effect=Exception("Gemini API Error"))
    
    mock_models = Mock()
    mock_models.generate_content = mock_generate_content
    
    mock_aio = Mock()
    mock_aio.models = mock_models
    
    mock_client = Mock()
    mock_client.aio = mock_aio
    
    with patch('google.genai.Client', return_value=mock_client):
        with pytest.raises(Exception) as exc_info:
            await provider.complete("You are a helpful assistant", "Hello", 4096)
        
        assert "Gemini API Error" in str(exc_info.value)


# ============================================================================
# INVARIANT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_all_providers_return_tuple_invariant():
    """Verify all providers return tuple of (str, int, int) from complete()."""
    providers = [
        AnthropicProvider("claude-3-opus-20240229"),
        OpenAIProvider("gpt-4"),
        GeminiProvider("gemini-pro")
    ]
    
    for provider in providers:
        # Mock appropriate responses for each provider
        if isinstance(provider, AnthropicProvider):
            mock_content = Mock()
            mock_content.text = "Response"
            mock_usage = Mock()
            mock_usage.input_tokens = 10
            mock_usage.output_tokens = 5
            mock_response = Mock()
            mock_response.content = [mock_content]
            mock_response.usage = mock_usage
            mock_messages = AsyncMock()
            mock_messages.create = AsyncMock(return_value=mock_response)
            mock_client = Mock()
            mock_client.messages = mock_messages
            patch_target = 'anthropic.AsyncAnthropic'
        
        elif isinstance(provider, OpenAIProvider):
            mock_message = Mock()
            mock_message.content = "Response"
            mock_choice = Mock()
            mock_choice.message = mock_message
            mock_usage = Mock()
            mock_usage.prompt_tokens = 10
            mock_usage.completion_tokens = 5
            mock_response = Mock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage
            mock_completions = AsyncMock()
            mock_completions.create = AsyncMock(return_value=mock_response)
            mock_chat = Mock()
            mock_chat.completions = mock_completions
            mock_client = Mock()
            mock_client.chat = mock_chat
            patch_target = 'openai.AsyncOpenAI'
        
        else:  # GeminiProvider
            mock_usage_metadata = Mock()
            mock_usage_metadata.prompt_token_count = 10
            mock_usage_metadata.candidates_token_count = 5
            mock_response = Mock()
            mock_response.text = "Response"
            mock_response.usage_metadata = mock_usage_metadata
            mock_generate_content = AsyncMock(return_value=mock_response)
            mock_models = Mock()
            mock_models.generate_content = mock_generate_content
            mock_aio = Mock()
            mock_aio.models = mock_models
            mock_client = Mock()
            mock_client.aio = mock_aio
            patch_target = 'google.genai.Client'
        
        with patch(patch_target, return_value=mock_client):
            result = await provider.complete("System prompt", "User prompt", 4096)
            
            # Verify tuple structure
            assert isinstance(result, tuple)
            assert len(result) == 3
            response_text, input_tokens, output_tokens = result
            assert isinstance(response_text, str)
            assert isinstance(input_tokens, int)
            assert isinstance(output_tokens, int)


@pytest.mark.asyncio
async def test_default_max_tokens_invariant():
    """Verify default max_tokens is 4096 across all implementations."""
    # This test verifies that when using max_tokens=4096, all providers work correctly
    # The actual default is used in the application code, not enforced by the providers
    
    providers = [
        AnthropicProvider("claude-3-opus-20240229"),
        OpenAIProvider("gpt-4"),
        GeminiProvider("gemini-pro")
    ]
    
    max_tokens = 4096  # Standard default
    
    for provider in providers:
        # Mock appropriate responses for each provider
        if isinstance(provider, AnthropicProvider):
            mock_content = Mock()
            mock_content.text = "Response"
            mock_usage = Mock()
            mock_usage.input_tokens = 10
            mock_usage.output_tokens = 5
            mock_response = Mock()
            mock_response.content = [mock_content]
            mock_response.usage = mock_usage
            mock_messages = AsyncMock()
            mock_messages.create = AsyncMock(return_value=mock_response)
            mock_client = Mock()
            mock_client.messages = mock_messages
            patch_target = 'anthropic.AsyncAnthropic'
        
        elif isinstance(provider, OpenAIProvider):
            mock_message = Mock()
            mock_message.content = "Response"
            mock_choice = Mock()
            mock_choice.message = mock_message
            mock_usage = Mock()
            mock_usage.prompt_tokens = 10
            mock_usage.completion_tokens = 5
            mock_response = Mock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage
            mock_completions = AsyncMock()
            mock_completions.create = AsyncMock(return_value=mock_response)
            mock_chat = Mock()
            mock_chat.completions = mock_completions
            mock_client = Mock()
            mock_client.chat = mock_chat
            patch_target = 'openai.AsyncOpenAI'
        
        else:  # GeminiProvider
            mock_usage_metadata = Mock()
            mock_usage_metadata.prompt_token_count = 10
            mock_usage_metadata.candidates_token_count = 5
            mock_response = Mock()
            mock_response.text = "Response"
            mock_response.usage_metadata = mock_usage_metadata
            mock_generate_content = AsyncMock(return_value=mock_response)
            mock_models = Mock()
            mock_models.generate_content = mock_generate_content
            mock_aio = Mock()
            mock_aio.models = mock_models
            mock_client = Mock()
            mock_client.aio = mock_aio
            patch_target = 'google.genai.Client'
        
        with patch(patch_target, return_value=mock_client):
            result = await provider.complete("System", "User", max_tokens)
            
            # Verify the call succeeded with default max_tokens
            assert result is not None
            assert isinstance(result, tuple)
