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
    - nova-micro, nova-lite, nova-pro

    Meta Llama (typically auto-enabled):
    - llama-3-8b, llama-3-70b, llama-3-1-8b, llama-3-1-70b

    Mistral (typically auto-enabled):
    - mistral-7b, mixtral-8x7b, mistral-large

    Anthropic Claude (requires Bedrock model access):
    - claude-3-haiku, claude-3-5-haiku, claude-3-sonnet, claude-3-5-sonnet
"""

import logging

from .base import BaseLLMClient
from .clients import (
    BedrockClaudeClient,
    BedrockLlamaClient,
    BedrockMistralClient,
    BedrockNovaClient,
)
from .prompt import DEFAULT_PROMPT
from .response import LLMResponse

logger = logging.getLogger(__name__)

# Build client registry from MODEL_IDS defined in each client class
_CLIENT_CLASSES = [BedrockNovaClient, BedrockClaudeClient, BedrockLlamaClient, BedrockMistralClient]
CLIENT_REGISTRY: dict[str, type[BaseLLMClient]] = {model: cls for cls in _CLIENT_CLASSES for model in cls.MODEL_IDS}

# Export model sets for external use
SUPPORTED_MODELS = set(CLIENT_REGISTRY.keys())


def get_llm_client(
    model: str | None = None,
    prompt_version: str = DEFAULT_PROMPT,
) -> BaseLLMClient:
    """Get a Bedrock LLM client for OCR correction.

    Args:
        model: Model name. If None, uses 'nova-lite' (auto-enabled, fast).
        prompt_version: Prompt variant to use (v1, v2, v3). Defaults to v1.

    Returns:
        Configured LLM client for the specified model.
    """
    model = model or "nova-lite"
    client_class = CLIENT_REGISTRY.get(model, BedrockNovaClient)
    return client_class(model=model, prompt_version=prompt_version)


__all__ = [
    "get_llm_client",
    "LLMResponse",
    "BaseLLMClient",
    "BedrockNovaClient",
    "BedrockLlamaClient",
    "BedrockMistralClient",
    "BedrockClaudeClient",
    "SUPPORTED_MODELS",
    "CLIENT_REGISTRY",
]
