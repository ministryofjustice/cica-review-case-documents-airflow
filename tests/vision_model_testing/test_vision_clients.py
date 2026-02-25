"""Tests for vision model clients."""

import pytest
from vision_model_testing.llm.base import IMAGE_MEDIA_TYPES
from vision_model_testing.llm.clients import ClaudeVisionClient, NovaVisionClient
from vision_model_testing.llm.response import VisionResponse


class TestImageMediaTypes:
    """Test image media type detection."""

    def test_png_media_type(self):
        """PNG files should map to image/png."""
        assert IMAGE_MEDIA_TYPES[".png"] == "image/png"

    def test_jpg_media_type(self):
        """JPG files should map to image/jpeg."""
        assert IMAGE_MEDIA_TYPES[".jpg"] == "image/jpeg"
        assert IMAGE_MEDIA_TYPES[".jpeg"] == "image/jpeg"

    def test_webp_media_type(self):
        """WEBP files should map to image/webp."""
        assert IMAGE_MEDIA_TYPES[".webp"] == "image/webp"

    def test_gif_media_type(self):
        """GIF files should map to image/gif."""
        assert IMAGE_MEDIA_TYPES[".gif"] == "image/gif"


class TestNovaVisionClient:
    """Test Nova vision client implementation."""

    def test_model_ids_defined(self):
        """Nova client should define model IDs."""
        assert "nova-pro" in NovaVisionClient.MODEL_IDS
        assert "nova-lite" in NovaVisionClient.MODEL_IDS

    def test_model_ids_are_valid_bedrock_ids(self):
        """Model IDs should be valid Bedrock format."""
        for short_name, full_id in NovaVisionClient.MODEL_IDS.items():
            assert "amazon.nova" in full_id
            assert "-v1:0" in full_id

    def test_build_vision_request_body_structure(self):
        """Nova request body should have correct structure."""
        # Create client instance without initializing boto3
        client = NovaVisionClient.__new__(NovaVisionClient)
        client._prompt_version = "v1"
        client._model = "nova-pro"
        client._model_id = "amazon.nova-pro-v1:0"

        request_body = client._build_vision_request_body(
            image_data="base64data",
            media_type="image/png",
            prompt="Extract text from this image.",
        )

        # Check structure
        assert "messages" in request_body
        assert "inferenceConfig" in request_body
        assert request_body["inferenceConfig"]["maxTokens"] == 4096

        # Check message structure
        message = request_body["messages"][0]
        assert message["role"] == "user"
        assert len(message["content"]) == 2

        # Check image content
        image_content = message["content"][0]
        assert "image" in image_content
        assert image_content["image"]["format"] == "png"
        assert image_content["image"]["source"]["bytes"] == "base64data"

        # Check text content
        text_content = message["content"][1]
        assert "text" in text_content
        assert text_content["text"] == "Extract text from this image."

    def test_parse_response(self):
        """Nova response parsing should extract text and tokens."""
        client = NovaVisionClient.__new__(NovaVisionClient)

        response_body = {
            "output": {"message": {"content": [{"text": "Extracted handwritten text here"}]}},
            "usage": {
                "inputTokens": 1000,
                "outputTokens": 50,
            },
        }

        text, input_tokens, output_tokens = client._parse_response(response_body)

        assert text == "Extracted handwritten text here"
        assert input_tokens == 1000
        assert output_tokens == 50


class TestClaudeVisionClient:
    """Test Claude vision client implementation."""

    def test_model_ids_defined(self):
        """Claude client should define model IDs."""
        assert "claude-3-5-sonnet" in ClaudeVisionClient.MODEL_IDS
        assert "claude-3-5-haiku" in ClaudeVisionClient.MODEL_IDS

    def test_model_ids_are_valid_bedrock_ids(self):
        """Model IDs should be valid Bedrock format."""
        for short_name, full_id in ClaudeVisionClient.MODEL_IDS.items():
            assert "anthropic.claude" in full_id

    def test_build_vision_request_body_structure(self):
        """Claude request body should have correct structure."""
        # Create client instance without initializing boto3
        client = ClaudeVisionClient.__new__(ClaudeVisionClient)
        client._prompt_version = "v1"
        client._model = "claude-3-5-sonnet"
        client._model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

        request_body = client._build_vision_request_body(
            image_data="base64data",
            media_type="image/jpeg",
            prompt="Extract text from this image.",
        )

        # Check structure
        assert "messages" in request_body
        assert "anthropic_version" in request_body
        assert request_body["max_tokens"] == 4096

        # Check message structure
        message = request_body["messages"][0]
        assert message["role"] == "user"
        assert len(message["content"]) == 2

        # Check image content
        image_content = message["content"][0]
        assert image_content["type"] == "image"
        assert image_content["source"]["type"] == "base64"
        assert image_content["source"]["media_type"] == "image/jpeg"
        assert image_content["source"]["data"] == "base64data"

        # Check text content
        text_content = message["content"][1]
        assert text_content["type"] == "text"
        assert text_content["text"] == "Extract text from this image."

    def test_parse_response(self):
        """Claude response parsing should extract text and tokens."""
        client = ClaudeVisionClient.__new__(ClaudeVisionClient)

        response_body = {
            "content": [{"text": "Extracted handwritten text here"}],
            "usage": {
                "input_tokens": 1500,
                "output_tokens": 75,
            },
        }

        text, input_tokens, output_tokens = client._parse_response(response_body)

        assert text == "Extracted handwritten text here"
        assert input_tokens == 1500
        assert output_tokens == 75


class TestVisionResponse:
    """Test VisionResponse dataclass."""

    def test_response_creation(self):
        """VisionResponse should be created with all fields."""
        response = VisionResponse(
            extracted_text="Hello world",
            model="nova-pro",
            prompt_version="v1_abc12345",
            input_tokens=100,
            output_tokens=10,
            image_path="/path/to/image.png",
        )

        assert response.extracted_text == "Hello world"
        assert response.model == "nova-pro"
        assert response.prompt_version == "v1_abc12345"
        assert response.input_tokens == 100
        assert response.output_tokens == 10
        assert response.image_path == "/path/to/image.png"

    def test_response_is_frozen(self):
        """VisionResponse should be immutable."""
        response = VisionResponse(
            extracted_text="Hello",
            model="nova-pro",
            prompt_version="v1",
            input_tokens=100,
            output_tokens=10,
            image_path="/path/to/image.png",
        )

        with pytest.raises(AttributeError):
            response.extracted_text = "Modified"


class TestClientRegistry:
    """Test vision client registry."""

    def test_registry_contains_nova_models(self):
        """Registry should contain Nova models."""
        from vision_model_testing.llm import SUPPORTED_VISION_MODELS

        assert "nova-pro" in SUPPORTED_VISION_MODELS
        assert "nova-lite" in SUPPORTED_VISION_MODELS

    def test_registry_contains_claude_models(self):
        """Registry should contain Claude models."""
        from vision_model_testing.llm import SUPPORTED_VISION_MODELS

        assert "claude-3-5-sonnet" in SUPPORTED_VISION_MODELS

    def test_get_vision_client_unknown_model(self):
        """get_vision_client should raise for unknown models."""
        from vision_model_testing.llm import get_vision_client

        with pytest.raises(ValueError, match="Unknown vision model"):
            get_vision_client(model="unknown-model")
