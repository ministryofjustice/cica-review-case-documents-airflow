"""Abstract base class for vision LLM clients."""

import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from botocore.exceptions import ClientError

from .prompt import (
    DEFAULT_VISION_PROMPT,
    get_vision_prompt,
    get_vision_prompt_hash,
    validate_vision_prompt_version,
)
from .response import VisionResponse

logger = logging.getLogger(__name__)

# Supported image formats and their media types
IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


# =============================================================================
# Retry Logic
# =============================================================================


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_errors: tuple = (
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelTimeoutException",
    ),
) -> Callable:
    """Decorator for retrying AWS API calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        exponential_base: Base for exponential backoff calculation.
        retryable_errors: AWS error codes that should trigger a retry.

    Returns:
        Decorated function with retry logic.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")

                    if error_code not in retryable_errors:
                        raise

                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base**attempt), max_delay)
                        logger.warning(
                            "AWS API call failed with %s, retrying in %.1fs (attempt %d/%d)",
                            error_code,
                            delay,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(delay)

            raise last_exception  # type: ignore

        return wrapper

    return decorator


# =============================================================================
# Base Vision Client
# =============================================================================


class BaseVisionClient(ABC):
    """Abstract base class for AWS Bedrock vision clients.

    Provides common functionality for all Bedrock vision model clients:
    - Boto3 client initialization
    - Retry logic with exponential backoff
    - Image encoding and media type detection
    - Response building

    Subclasses only need to implement:
    - MODEL_IDS: Dict mapping short names to full model IDs
    - _build_vision_request_body(): Model-specific request format
    - _parse_response(): Model-specific response parsing
    """

    # Subclasses must define this
    MODEL_IDS: dict[str, str] = {}

    def __init__(
        self,
        model: str,
        region: str | None = None,
        prompt_version: str = DEFAULT_VISION_PROMPT,
    ):
        """Initialize Bedrock vision client.

        Args:
            model: Model shortname from MODEL_IDS.
            region: AWS region. If None, uses default from settings.
            prompt_version: Prompt variant to use.
        """
        import boto3

        from ..config import settings

        self._prompt_version = validate_vision_prompt_version(prompt_version)
        self._model = model
        self._model_id = self.MODEL_IDS.get(model, model)
        self._region = region or settings.AWS_REGION

        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self._region,
            aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_MOD_PLATFORM_SESSION_TOKEN,
        )
        logger.info(
            "Initialized %s client: %s in %s (prompt: %s)",
            self.__class__.__name__,
            self._model_id,
            self._region,
            prompt_version,
        )

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        return self._model

    @property
    def prompt_version(self) -> str:
        """Return the prompt version being used."""
        return self._prompt_version

    def get_prompt(self) -> str:
        """Get the prompt text for this client's version."""
        return get_vision_prompt(self._prompt_version)

    def get_prompt_hash(self) -> str:
        """Get a hash of the prompt for versioning."""
        return get_vision_prompt_hash(self._prompt_version)

    @staticmethod
    def _encode_image(image_path: Path) -> tuple[str, str]:
        """Read and base64-encode an image file.

        Args:
            image_path: Path to the image file.

        Returns:
            Tuple of (base64_encoded_data, media_type).

        Raises:
            FileNotFoundError: If image file doesn't exist.
            ValueError: If image format is not supported.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        suffix = image_path.suffix.lower()
        media_type = IMAGE_MEDIA_TYPES.get(suffix)
        if media_type is None:
            raise ValueError(f"Unsupported image format: {suffix}. Supported formats: {list(IMAGE_MEDIA_TYPES.keys())}")

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        return base64.standard_b64encode(image_bytes).decode("utf-8"), media_type

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _invoke_model(self, request_body: dict) -> dict:
        """Invoke the model with retry logic."""
        response = self._client.invoke_model(
            modelId=self._model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(response["body"].read())

    @abstractmethod
    def _build_vision_request_body(self, image_data: str, media_type: str, prompt: str) -> dict:
        """Build model-specific request body for vision inference.

        Args:
            image_data: Base64-encoded image data.
            media_type: MIME type of the image.
            prompt: The extraction prompt.

        Returns:
            Request body dict for the model's API format.
        """
        pass

    @abstractmethod
    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse model-specific response.

        Args:
            response_body: Raw response from the model.

        Returns:
            Tuple of (extracted_text, input_tokens, output_tokens).
        """
        pass

    def extract_text_from_image(self, image_path: Path) -> VisionResponse:
        """Extract text from an image using vision model.

        Args:
            image_path: Path to the image file.

        Returns:
            VisionResponse with extracted text and metadata.
        """
        image_data, media_type = self._encode_image(image_path)
        prompt = self.get_prompt()

        request_body = self._build_vision_request_body(image_data, media_type, prompt)
        response_body = self._invoke_model(request_body)
        extracted_text, input_tokens, output_tokens = self._parse_response(response_body)

        return VisionResponse(
            extracted_text=extracted_text.strip(),
            model=self._model,
            prompt_version=self.get_prompt_hash(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_path=str(image_path),
        )
