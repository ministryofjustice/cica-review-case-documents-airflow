"""Vision client implementations.

All vision model implementations live here for easy extension.
To add a new model:
1. Create a subclass of BaseVisionClient
2. Define MODEL_IDS dict
3. Implement _build_vision_request_body() and _parse_response()
4. Update VISION_CLIENT_REGISTRY in __init__.py
"""

import logging
import os
from pathlib import Path

from .base import BaseVisionClient
from .prompt import DEFAULT_VISION_PROMPT, get_vision_prompt, get_vision_prompt_hash, validate_vision_prompt_version
from .response import VisionResponse

logger = logging.getLogger(__name__)

# =============================================================================
# Amazon Nova Vision Client
# =============================================================================


class NovaVisionClient(BaseVisionClient):
    """AWS Bedrock Nova vision client for image-to-text extraction.

    Uses Amazon Nova multimodal models via AWS Bedrock. These are auto-enabled
    and don't require marketplace subscription.

    Supports: nova-lite (fast), nova-pro (best quality)
    """

    MODEL_IDS = {
        "nova-lite": "amazon.nova-lite-v1:0",
        "nova-pro": "amazon.nova-pro-v1:0",
    }

    def _build_vision_request_body(self, image_data: str, media_type: str, prompt: str) -> dict:
        """Build Nova API request body for vision inference.

        Nova uses a different format for images:
        - format: "png", "jpeg", "gif", or "webp" (without image/ prefix)
        - source.bytes: base64-encoded image data
        """
        # Extract format from media type (e.g., "image/png" -> "png")
        image_format = media_type.split("/")[-1]

        return {
            "inferenceConfig": {"maxTokens": 4096},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": image_format,
                                "source": {"bytes": image_data},
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ],
        }

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Nova API response."""
        extracted_text = response_body["output"]["message"]["content"][0]["text"]
        usage = response_body.get("usage", {})
        return (
            extracted_text,
            usage.get("inputTokens", 0),
            usage.get("outputTokens", 0),
        )


# =============================================================================
# Anthropic Claude Vision Client
# =============================================================================


class ClaudeVisionClient(BaseVisionClient):
    """AWS Bedrock Claude vision client for image-to-text extraction.

    Uses Claude multimodal models via AWS Bedrock for secure processing.
    Requires Bedrock model access to be enabled in the AWS console.

    Supports: claude-3-5-sonnet (best quality)
    """

    MODEL_IDS = {
        "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "claude-3-5-haiku": "anthropic.claude-3-5-haiku-20241022-v1:0",
        "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
        "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
    }

    def _build_vision_request_body(self, image_data: str, media_type: str, prompt: str) -> dict:
        """Build Claude API request body for vision inference.

        Claude uses the Messages API format with image content blocks.
        """
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        }

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Claude API response."""
        extracted_text = response_body["content"][0]["text"]
        usage = response_body.get("usage", {})
        return (
            extracted_text,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )


# =============================================================================
# LiteLLM Gateway Vision Client (OpenAI-compatible)
# =============================================================================

LITELLM_BASE_URL = "https://llm-gateway.development.data-platform.service.justice.gov.uk"


class LiteLLMVisionClient(BaseVisionClient):
    """Vision client using the MoJ LiteLLM proxy gateway (OpenAI-compatible).

    Uses the OpenAI SDK to call models via the LiteLLM proxy, which provides
    access to additional models not available directly through AWS Bedrock.

    Requires OPENAI_KEY environment variable to be set.

    Supports: bedrock-claude-opus-4-6, bedrock-claude-opus-4-5,
              bedrock-claude-sonnet-4-5, bedrock-claude-sonnet-4-6,
              bedrock-qwen-qwen3-coder-30b-a3b
    """

    MODEL_IDS = {
        "bedrock-claude-opus-4-6": "bedrock-claude-opus-4-6",
        "bedrock-claude-opus-4-5": "bedrock-claude-opus-4-5",
        "bedrock-claude-sonnet-4-5": "bedrock-claude-sonnet-4-5",
        "bedrock-claude-sonnet-4-6": "bedrock-claude-sonnet-4-6",
        "bedrock-qwen-qwen3-coder-30b-a3b": "bedrock-qwen-qwen3-coder-30b-a3b",
    }

    def __init__(
        self,
        model: str,
        region: str | None = None,
        prompt_version: str = DEFAULT_VISION_PROMPT,
    ):
        """Initialize LiteLLM gateway vision client.

        Args:
            model: Model shortname from MODEL_IDS.
            region: Unused, kept for interface compatibility.
            prompt_version: Prompt variant to use.

        Raises:
            ValueError: If OPENAI_KEY environment variable is not set.
        """
        api_key = os.environ.get("OPENAI_KEY")
        if not api_key:
            raise ValueError("OPENAI_KEY environment variable must be set to use LiteLLM gateway models")

        self._prompt_version = validate_vision_prompt_version(prompt_version)
        self._model = model
        self._model_id = self.MODEL_IDS.get(model, model)

        import openai

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=LITELLM_BASE_URL,
        )
        logger.info(
            "Initialized LiteLLMVisionClient: %s (prompt: %s)",
            self._model_id,
            prompt_version,
        )

    def _build_vision_request_body(self, image_data: str, media_type: str, prompt: str) -> dict:
        """Not used — extract_text_from_image is overridden."""
        raise NotImplementedError("LiteLLMVisionClient uses the OpenAI SDK directly")

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Not used — extract_text_from_image is overridden."""
        raise NotImplementedError("LiteLLMVisionClient uses the OpenAI SDK directly")

    def extract_text_from_image(self, image_path: Path) -> VisionResponse:
        """Extract text from an image using the LiteLLM gateway.

        Args:
            image_path: Path to the image file.

        Returns:
            VisionResponse with extracted text and metadata.
        """
        image_data, media_type = self._encode_image(image_path)
        prompt = get_vision_prompt(self._prompt_version)

        data_url = f"data:{media_type};base64,{image_data}"

        response = self._client.chat.completions.create(
            model=self._model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )

        extracted_text = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return VisionResponse(
            extracted_text=extracted_text.strip(),
            model=self._model,
            prompt_version=get_vision_prompt_hash(self._prompt_version),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_path=str(image_path),
        )

    def extract_text_with_ocr_hint(self, image_path: Path, ocr_text: str) -> VisionResponse:
        """Extract handwritten text using both the image and a Textract OCR hint.

        Sends the image alongside the Textract OCR output so the model can use
        OCR structure as a guide while correcting character errors from the image.

        Args:
            image_path: Path to the image file.
            ocr_text: Raw Textract OCR text to use as a structural reference.

        Returns:
            VisionResponse with extracted text and metadata.
        """
        image_data, media_type = self._encode_image(image_path)
        prompt = get_vision_prompt(self._prompt_version)
        data_url = f"data:{media_type};base64,{image_data}"

        response = self._client.chat.completions.create(
            model=self._model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": f"{prompt}\n\nTextract OCR reference:\n{ocr_text}",
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )

        extracted_text = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return VisionResponse(
            extracted_text=extracted_text.strip(),
            model=self._model,
            prompt_version=get_vision_prompt_hash(self._prompt_version),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_path=str(image_path),
        )

    def extract_text_with_structured_ocr(self, image_path: Path, word_blocks: list) -> VisionResponse:
        """Extract handwritten text using the image and a structured Textract word list.

        Builds a spatial word table (top left text type confidence) from Textract
        WordBlock objects and sends it alongside the image so the model can use
        per-word positions, PRINTED/HANDWRITING classification, and confidence
        scores as a layout guide.

        Args:
            image_path: Path to the image file.
            word_blocks: List of WordBlock dataclass instances from Textract,
                each with .bbox_top, .bbox_left, .text, .text_type, .confidence.

        Returns:
            VisionResponse with extracted text and metadata.
        """
        image_data, media_type = self._encode_image(image_path)
        prompt = get_vision_prompt(self._prompt_version)
        data_url = f"data:{media_type};base64,{image_data}"

        # Build structured word table: top left text type confidence
        lines = ["top    left   text                           type         conf"]
        for w in sorted(word_blocks, key=lambda b: (round(b.bbox_top, 2), b.bbox_left)):
            lines.append(f"{w.bbox_top:.3f}  {w.bbox_left:.3f}  {w.text:<30s}  {w.text_type:<11s}  {w.confidence:.1f}")
        structured_hint = "\n".join(lines)

        response = self._client.chat.completions.create(
            model=self._model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": f"{prompt}\n\nTextract structured word list:\n{structured_hint}",
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )

        extracted_text = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return VisionResponse(
            extracted_text=extracted_text.strip(),
            model=self._model,
            prompt_version=get_vision_prompt_hash(self._prompt_version),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_path=str(image_path),
        )
