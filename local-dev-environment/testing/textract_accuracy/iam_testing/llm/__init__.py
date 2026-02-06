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
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
    - nova-micro, nova-lite, nova-pro

    Meta Llama (typically auto-enabled):
    - llama-3-8b, llama-3-70b, llama-3-1-8b, llama-3-1-70b

    Mistral (typically auto-enabled):
    - mistral-7b, mixtral-8x7b, mistral-large
<<<<<<< HEAD

    Anthropic Claude (requires Bedrock model access):
    - claude-3-haiku, claude-3-5-haiku, claude-3-sonnet, claude-3-5-sonnet
=======
    - nova-micro: Fastest, cheapest
    - nova-lite: Good balance of speed/quality (default)
    - nova-pro: Best Nova quality

    Anthropic Claude (requires Bedrock model access):
    - claude-3-haiku: Fast, cheap
    - claude-3-5-haiku: Improved haiku
    - claude-3-sonnet: Better quality
    - claude-3-5-sonnet: Best quality
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======

    Anthropic Claude (requires Bedrock model access):
    - claude-3-haiku, claude-3-5-haiku, claude-3-sonnet, claude-3-5-sonnet
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
"""

import logging

from .base import BaseLLMClient
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
from .clients import (
    BedrockClaudeClient,
    BedrockLlamaClient,
    BedrockMistralClient,
    BedrockNovaClient,
)
from .prompt import DEFAULT_PROMPT
<<<<<<< HEAD
=======
from .clients import BedrockClaudeClient, BedrockNovaClient
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
from .response import LLMResponse

logger = logging.getLogger(__name__)

<<<<<<< HEAD
<<<<<<< HEAD
# Build client registry from MODEL_IDS defined in each client class
_CLIENT_CLASSES = [BedrockNovaClient, BedrockClaudeClient, BedrockLlamaClient, BedrockMistralClient]
CLIENT_REGISTRY: dict[str, type[BaseLLMClient]] = {model: cls for cls in _CLIENT_CLASSES for model in cls.MODEL_IDS}

# Export model sets for external use
SUPPORTED_MODELS = set(CLIENT_REGISTRY.keys())


def get_llm_client(
    model: str | None = None,
    prompt_version: str = DEFAULT_PROMPT,
) -> BaseLLMClient:
=======
# Models grouped by API format
NOVA_MODELS = {"nova-micro", "nova-lite", "nova-pro"}
CLAUDE_MODELS = {"claude-3-haiku", "claude-3-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku"}
=======
# Build client registry from MODEL_IDS defined in each client class
_CLIENT_CLASSES = [BedrockNovaClient, BedrockClaudeClient, BedrockLlamaClient, BedrockMistralClient]
CLIENT_REGISTRY: dict[str, type[BaseLLMClient]] = {model: cls for cls in _CLIENT_CLASSES for model in cls.MODEL_IDS}
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

# Export model sets for external use
SUPPORTED_MODELS = set(CLIENT_REGISTRY.keys())


<<<<<<< HEAD
def get_llm_client(model: str | None = None) -> BaseLLMClient:
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
def get_llm_client(
    model: str | None = None,
    prompt_version: str = DEFAULT_PROMPT,
) -> BaseLLMClient:
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
    """Get a Bedrock LLM client for OCR correction.

    Args:
        model: Model name. If None, uses 'nova-lite' (auto-enabled, fast).
<<<<<<< HEAD
<<<<<<< HEAD
        prompt_version: Prompt variant to use (v1, v2, v3). Defaults to v1.

    Returns:
        Configured LLM client for the specified model.
    """
    model = model or "nova-lite"
    client_class = CLIENT_REGISTRY.get(model, BedrockNovaClient)
    return client_class(model=model, prompt_version=prompt_version)
=======
=======
        prompt_version: Prompt variant to use (v1, v2, v3). Defaults to v1.
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

    Returns:
        Configured LLM client for the specified model.
    """
    model = model or "nova-lite"
<<<<<<< HEAD

    if model in NOVA_MODELS:
        return BedrockNovaClient(model=model)
    elif model in CLAUDE_MODELS:
        return BedrockClaudeClient(model=model)
    else:
        logger.warning("Unknown model '%s', trying as Nova model ID", model)
        return BedrockNovaClient(model=model)
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
    client_class = CLIENT_REGISTRY.get(model, BedrockNovaClient)
    return client_class(model=model, prompt_version=prompt_version)
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)


__all__ = [
    "get_llm_client",
    "LLMResponse",
    "BaseLLMClient",
    "BedrockNovaClient",
<<<<<<< HEAD
<<<<<<< HEAD
    "BedrockLlamaClient",
    "BedrockMistralClient",
    "BedrockClaudeClient",
    "SUPPORTED_MODELS",
    "CLIENT_REGISTRY",
=======
    "BedrockClaudeClient",
    "SUPPORTED_MODELS",
    "NOVA_MODELS",
    "CLAUDE_MODELS",
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
    "BedrockLlamaClient",
    "BedrockMistralClient",
    "BedrockClaudeClient",
    "SUPPORTED_MODELS",
    "CLIENT_REGISTRY",
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
]
