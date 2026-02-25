"""Vision LLM client package for direct image-to-text extraction.

Provides secure vision model access via AWS Bedrock with no data retention.
All prompts are versioned for reproducibility.

Usage:
    from vision_model_testing.llm import get_vision_client, VisionResponse

    client = get_vision_client(model="nova-pro")
    response = client.extract_text_from_image(Path("image.png"))
    print(response.extracted_text)

Available models:
    Amazon Nova (multimodal, auto-enabled):
    - nova-lite, nova-pro

    Anthropic Claude (multimodal, requires Bedrock access):
    - claude-3-5-sonnet
"""

import logging

from .base import BaseVisionClient
from .clients import ClaudeVisionClient, NovaVisionClient
from .prompt import DEFAULT_VISION_PROMPT
from .response import VisionResponse

logger = logging.getLogger(__name__)

# Build client registry from MODEL_IDS defined in each client class
_VISION_CLIENT_CLASSES = [NovaVisionClient, ClaudeVisionClient]
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
    "SUPPORTED_VISION_MODELS",
    "VISION_CLIENT_REGISTRY",
]
