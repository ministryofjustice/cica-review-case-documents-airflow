"""LLM client package for OCR text augmentation using AWS Bedrock.

Provides secure LLM access with no data storage/retention.
All prompts are versioned for reproducibility.

Usage:
    from iam_testing.llm import get_llm_client, LLMResponse

    client = get_llm_client(model="nova-lite")
    response = client.correct_ocr_text(ocr_text)
    print(response.corrected_text)
    print(response.diff_summary)

Available models:
    Amazon Nova (auto-enabled, no subscription needed):
    - nova-micro: Fastest, cheapest
    - nova-lite: Good balance of speed/quality (default)
    - nova-pro: Best Nova quality

    Anthropic Claude (requires Bedrock model access):
    - claude-3-haiku: Fast, cheap
    - claude-3-5-haiku: Improved haiku
    - claude-3-sonnet: Better quality
    - claude-3-5-sonnet: Best quality
"""

import logging

from .base import BaseLLMClient
from .clients import BedrockClaudeClient, BedrockNovaClient
from .response import LLMResponse

logger = logging.getLogger(__name__)

# Models grouped by API format
NOVA_MODELS = {"nova-micro", "nova-lite", "nova-pro"}
CLAUDE_MODELS = {"claude-3-haiku", "claude-3-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku"}

# All supported models
SUPPORTED_MODELS = NOVA_MODELS | CLAUDE_MODELS


def get_llm_client(model: str | None = None) -> BaseLLMClient:
    """Get a Bedrock LLM client for OCR correction.

    Args:
        model: Model name. If None, uses 'nova-lite' (auto-enabled, fast).

    Returns:
        Configured BedrockNovaClient or BedrockClaudeClient.

    Raises:
        ValueError: If model is not recognized.
    """
    model = model or "nova-lite"

    if model in NOVA_MODELS:
        return BedrockNovaClient(model=model)
    elif model in CLAUDE_MODELS:
        return BedrockClaudeClient(model=model)
    else:
        logger.warning("Unknown model '%s', trying as Nova model ID", model)
        return BedrockNovaClient(model=model)


__all__ = [
    "get_llm_client",
    "LLMResponse",
    "BaseLLMClient",
    "BedrockNovaClient",
    "BedrockClaudeClient",
    "SUPPORTED_MODELS",
    "NOVA_MODELS",
    "CLAUDE_MODELS",
]
