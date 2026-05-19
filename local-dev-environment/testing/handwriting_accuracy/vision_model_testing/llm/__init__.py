"""Vision LLM client package for direct image-to-text extraction.

Provides secure vision model access via the MoJ LiteLLM gateway (recommended)
or directly via AWS Bedrock. All prompts are versioned for reproducibility.

Quick start (LiteLLM gateway — recommended):
    from vision_model_testing.llm import get_vision_client
    from pathlib import Path

    # Image only
    client = get_vision_client(model="bedrock-claude-opus-4-6", prompt_version="v1.5")
    response = client.extract_text_from_image(Path("page.png"))

    # Image + flat OCR hint (best evaluated approach)
    client = get_vision_client(model="bedrock-claude-opus-4-6", prompt_version="v1.5-mm")
    response = client.extract_text_with_ocr_hint(Path("page.png"), ocr_text=ocr_text)

    # Image + structured Textract word table
    client = get_vision_client(model="bedrock-claude-opus-4-6", prompt_version="v1.5-mm-struct2")
    response = client.extract_text_with_structured_ocr(Path("page.png"), word_blocks=word_blocks)

Recommended models:
    LiteLLM gateway (requires OPENAI_KEY):
    - bedrock-claude-opus-4-6  (best quality, used in evaluation)
    - bedrock-claude-sonnet-4-6  (faster, lower cost)

    Direct Bedrock (requires AWS_* env vars):
    - nova-pro, nova-lite  (Amazon Nova, auto-enabled)
    - claude-3-5-sonnet    (requires Bedrock model access)

See README.md for full production pipeline integration guidance.
"""

import logging

from .base import BaseVisionClient
from .clients import ClaudeVisionClient, LiteLLMVisionClient, NovaVisionClient
from .prompt import DEFAULT_VISION_PROMPT
from .response import VisionResponse

logger = logging.getLogger(__name__)

# Build client registry from MODEL_IDS defined in each client class
_VISION_CLIENT_CLASSES = [NovaVisionClient, ClaudeVisionClient, LiteLLMVisionClient]
VISION_CLIENT_REGISTRY: dict[str, type[BaseVisionClient]] = {
    model: cls for cls in _VISION_CLIENT_CLASSES for model in cls.MODEL_IDS
}

# Export model sets for external use
SUPPORTED_VISION_MODELS = set(VISION_CLIENT_REGISTRY.keys())


def get_vision_client(
    model: str | None = None,
    prompt_version: str = DEFAULT_VISION_PROMPT,
) -> BaseVisionClient:
    """Get a Bedrock vision client for image-to-text extraction.

    Args:
        model: Model name. If None, uses 'nova-pro' (best quality).
        prompt_version: Prompt variant to use. Defaults to 'v1'.

    Returns:
        Configured vision client for the specified model.

    Raises:
        ValueError: If model is not supported.
    """
    model = model or "nova-pro"
    client_class = VISION_CLIENT_REGISTRY.get(model)
    if client_class is None:
        raise ValueError(f"Unknown vision model: {model}. Supported models: {sorted(SUPPORTED_VISION_MODELS)}")
    return client_class(model=model, prompt_version=prompt_version)


__all__ = [
    "get_vision_client",
    "VisionResponse",
    "BaseVisionClient",
    "NovaVisionClient",
    "ClaudeVisionClient",
    "LiteLLMVisionClient",
    "SUPPORTED_VISION_MODELS",
    "VISION_CLIENT_REGISTRY",
]
