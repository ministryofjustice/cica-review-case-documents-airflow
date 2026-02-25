"""AWS Bedrock vision client implementations.

All Bedrock vision model implementations live here for easy extension.
To add a new model:
1. Create a subclass of BaseVisionClient
2. Define MODEL_IDS dict
3. Implement _build_vision_request_body() and _parse_response()
4. Update VISION_CLIENT_REGISTRY in __init__.py
"""

from .base import BaseVisionClient

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
