# === LLM Provider Abstraction (src_advocate_provider) v1 ===
#  Dependencies: abc, time, advocate.models, anthropic, openai, google.genai, transmogrifier.core
# Provides a unified interface for multiple LLM providers (Anthropic, OpenAI, Gemini) with cost estimation and optional prompt register normalization via transmogrifier.

# Module invariants:
#   - _PRICING contains approximate USD pricing per 1M tokens for known models as (input_price, output_price) tuples
#   - _DEFAULTS maps provider names to (provider_class, default_model) tuples for 'anthropic', 'openai', and 'gemini'
#   - All complete() methods return tuple of (str, int, int) representing (response_text, input_tokens, output_tokens)
#   - Default max_tokens is 4096 across all provider implementations
#   - Fallback pricing is 3.0 for input and 15.0 for output per 1M tokens when model not found in _PRICING

class LLMProvider:
    """Abstract base class for LLM provider implementations. Stores model identifier and defines interface for completion and provider_name."""
    model: str                               # required, Model identifier set during initialization

class AnthropicProvider:
    """Concrete LLMProvider implementation for Anthropic Claude models using anthropic.AsyncAnthropic client."""
    model: str                               # required, Anthropic model identifier (e.g., 'claude-sonnet-4-20250514')

class OpenAIProvider:
    """Concrete LLMProvider implementation for OpenAI models using openai.AsyncOpenAI client."""
    model: str                               # required, OpenAI model identifier (e.g., 'gpt-4o')

class GeminiProvider:
    """Concrete LLMProvider implementation for Google Gemini models using google.genai.Client."""
    model: str                               # required, Gemini model identifier (e.g., 'gemini-2.5-flash')

def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Calculate estimated cost in USD for a given model based on input and output token counts using approximate pricing data. Returns default pricing (3.0/15.0 per 1M tokens) if model not recognized.

    Postconditions:
      - Returns non-negative float representing estimated USD cost
      - Uses fuzzy prefix matching against _PRICING dictionary keys
      - Falls back to default pricing (3.0 input, 15.0 output per 1M tokens) if no match

    Side effects: none
    Idempotent: no
    """
    ...

def create_provider(
    provider: str = "anthropic",
    model: str | None = None,
) -> LLMProvider:
    """
    Factory function to instantiate an LLMProvider based on provider name. Uses default models from _DEFAULTS if model not specified.

    Preconditions:
      - provider must be one of: 'anthropic', 'openai', 'gemini'

    Postconditions:
      - Returns instance of AnthropicProvider, OpenAIProvider, or GeminiProvider
      - Uses provided model or falls back to default model for the provider

    Errors:
      - unknown_provider (ValueError): provider not in _DEFAULTS
          message: Unknown provider: {provider}. Choose from: {list(_DEFAULTS)}

    Side effects: none
    Idempotent: no
    """
    ...

async def transmogrify(
    text: str,
    model: str,
) -> str:
    """
    Attempt to normalize prompt register via Transmogrifier if available. Returns original text on any import or runtime error.

    Postconditions:
      - Returns transmogrified text if transmogrifier.core.Transmogrifier is available
      - Returns original text unchanged on ImportError or any other exception

    Side effects: May attempt to import transmogrifier.core.Transmogrifier
    Idempotent: no
    """
    ...

def LLMProvider.__init__(
    self: LLMProvider,
    model: str,
) -> None:
    """
    Initialize abstract LLMProvider with model identifier. Stores model name for use in complete().

    Postconditions:
      - self.model is set to provided model string

    Side effects: Sets self.model attribute
    Idempotent: no
    """
    ...

async def LLMProvider.complete(
    self: LLMProvider,
    system: str,
    user: str,
    max_tokens: int = 4096,
) -> tuple[str, int, int]:
    """
    Abstract method that must be implemented by subclasses to perform LLM completion with system and user prompts.

    Postconditions:
      - Returns (response_text, input_tokens, output_tokens)

    Errors:
      - not_implemented (NotImplementedError): Called on abstract base class

    Side effects: none
    Idempotent: no
    """
    ...

def LLMProvider.provider_name(
    self: LLMProvider,
) -> str:
    """
    Abstract property that must be implemented by subclasses to return provider identifier string.

    Postconditions:
      - Returns provider name identifier

    Errors:
      - not_implemented (NotImplementedError): Called on abstract base class

    Side effects: none
    Idempotent: no
    """
    ...

def AnthropicProvider.provider_name(
    self: AnthropicProvider,
) -> str:
    """
    Returns 'anthropic' as the provider identifier.

    Postconditions:
      - Returns 'anthropic'

    Side effects: none
    Idempotent: no
    """
    ...

async def AnthropicProvider.complete(
    self: AnthropicProvider,
    system: str,
    user: str,
    max_tokens: int = 4096,
) -> tuple[str, int, int]:
    """
    Perform completion using Anthropic's AsyncAnthropic client. Creates client, sends system/user messages, extracts text and token usage.

    Postconditions:
      - Returns (response.content[0].text, input_tokens, output_tokens)

    Errors:
      - anthropic_api_error (Exception): Anthropic API call fails or returns unexpected format
          source: anthropic.AsyncAnthropic
      - index_error (IndexError): response.content is empty

    Side effects: Imports anthropic module, Creates anthropic.AsyncAnthropic client (may read API key from environment), Makes async API call to Anthropic
    Idempotent: no
    """
    ...

def OpenAIProvider.provider_name(
    self: OpenAIProvider,
) -> str:
    """
    Returns 'openai' as the provider identifier.

    Postconditions:
      - Returns 'openai'

    Side effects: none
    Idempotent: no
    """
    ...

async def OpenAIProvider.complete(
    self: OpenAIProvider,
    system: str,
    user: str,
    max_tokens: int = 4096,
) -> tuple[str, int, int]:
    """
    Perform completion using OpenAI's AsyncOpenAI client. Creates client, sends system/user messages, extracts text and token usage with fallback to empty string and 0 tokens.

    Postconditions:
      - Returns (message.content or '', prompt_tokens or 0, completion_tokens or 0)
      - Handles None values gracefully with fallbacks

    Errors:
      - openai_api_error (Exception): OpenAI API call fails
          source: openai.AsyncOpenAI

    Side effects: Imports openai.AsyncOpenAI, Creates AsyncOpenAI client (may read API key from environment), Makes async API call to OpenAI
    Idempotent: no
    """
    ...

def GeminiProvider.provider_name(
    self: GeminiProvider,
) -> str:
    """
    Returns 'gemini' as the provider identifier.

    Postconditions:
      - Returns 'gemini'

    Side effects: none
    Idempotent: no
    """
    ...

async def GeminiProvider.complete(
    self: GeminiProvider,
    system: str,
    user: str,
    max_tokens: int = 4096,
) -> tuple[str, int, int]:
    """
    Perform completion using Google's genai client. Creates client, sends user message with system instruction config, extracts text and token usage with fallback to empty string and 0 tokens.

    Postconditions:
      - Returns (response.text or '', prompt_token_count or 0, candidates_token_count or 0)
      - Handles None values gracefully with fallbacks

    Errors:
      - gemini_api_error (Exception): Gemini API call fails
          source: google.genai.Client

    Side effects: Imports google.genai, Creates genai.Client (may read API key from environment), Makes async API call to Gemini
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['LLMProvider', 'AnthropicProvider', 'OpenAIProvider', 'GeminiProvider', 'estimate_cost', 'create_provider', 'transmogrify']
