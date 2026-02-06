"""Abstract base class for LLM clients."""

<<<<<<< HEAD
<<<<<<< HEAD
import json
import logging
import time
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Callable

from botocore.exceptions import ClientError

from .diff import generate_diff
from .prompt import DEFAULT_PROMPT, get_prompt_hash, get_system_prompt, validate_prompt_version
=======
=======
import json
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
import logging
import time
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Callable

<<<<<<< HEAD
from .prompt import SYSTEM_PROMPT, get_prompt_hash
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
from botocore.exceptions import ClientError

from .diff import generate_diff
from .prompt import DEFAULT_PROMPT, get_prompt_hash, get_system_prompt, validate_prompt_version
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
from .response import LLMResponse

logger = logging.getLogger(__name__)


<<<<<<< HEAD
<<<<<<< HEAD
# =============================================================================
# Retry Logic
# =============================================================================


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_errors: tuple = ("ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"),
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
# Base Client
# =============================================================================


class BaseLLMClient(ABC):
    """Abstract base class for AWS Bedrock LLM clients.

    Provides common functionality for all Bedrock model clients:
    - Boto3 client initialization
    - Retry logic with exponential backoff
    - Empty text handling
    - Response building

    Subclasses only need to implement:
    - MODEL_IDS: Dict mapping short names to full model IDs
    - _build_request_body(): Model-specific request format
    - _parse_response(): Model-specific response parsing
    """

    # Subclasses must define this
    MODEL_IDS: dict[str, str] = {}

    def __init__(
        self,
        model: str,
        region: str | None = None,
        prompt_version: str = DEFAULT_PROMPT,
    ):
        """Initialize Bedrock client.

        Args:
            model: Model shortname from MODEL_IDS.
            region: AWS region. If None, uses default from settings.
            prompt_version: Prompt variant to use (v1, v2, v3).
        """
        import boto3

        from ..config import settings

        self._prompt_version = validate_prompt_version(prompt_version)
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

    def get_system_prompt(self) -> str:
        """Get the system prompt text for this client's version."""
        return get_system_prompt(self._prompt_version)

    def get_prompt_hash(self) -> str:
        """Get a hash of the system prompt for versioning."""
        return get_prompt_hash(self._prompt_version)

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

    def _empty_response(self, ocr_text: str) -> LLMResponse:
        """Create response for empty input text."""
        return LLMResponse(
            original_text=ocr_text,
            corrected_text=ocr_text,
            model=self._model,
            prompt_version=self.get_prompt_hash(),
            input_tokens=0,
            output_tokens=0,
            diff_summary="(no changes)",
        )

    @abstractmethod
    def _build_request_body(self, ocr_text: str) -> dict:
        """Build model-specific request body.

        Args:
            ocr_text: The OCR text to correct.

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
            Tuple of (corrected_text, input_tokens, output_tokens).
        """
        pass

=======
class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.
=======
# =============================================================================
# Retry Logic
# =============================================================================
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_errors: tuple = ("ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"),
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
# Base Client
# =============================================================================


class BaseLLMClient(ABC):
    """Abstract base class for AWS Bedrock LLM clients.

    Provides common functionality for all Bedrock model clients:
    - Boto3 client initialization
    - Retry logic with exponential backoff
    - Empty text handling
    - Response building

    Subclasses only need to implement:
    - MODEL_IDS: Dict mapping short names to full model IDs
    - _build_request_body(): Model-specific request format
    - _parse_response(): Model-specific response parsing
    """

    # Subclasses must define this
    MODEL_IDS: dict[str, str] = {}

    def __init__(
        self,
        model: str,
        region: str | None = None,
        prompt_version: str = DEFAULT_PROMPT,
    ):
        """Initialize Bedrock client.

        Args:
            model: Model shortname from MODEL_IDS.
            region: AWS region. If None, uses default from settings.
            prompt_version: Prompt variant to use (v1, v2, v3).
        """
        import boto3

        from ..config import settings

        self._prompt_version = validate_prompt_version(prompt_version)
        self._model = model
        self._model_id = self.MODEL_IDS.get(model, model)
        self._region = region or settings.AWS_REGION

        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self._region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN,
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

    def get_system_prompt(self) -> str:
        """Get the system prompt text for this client's version."""
        return get_system_prompt(self._prompt_version)

    def get_prompt_hash(self) -> str:
        """Get a hash of the system prompt for versioning."""
        return get_prompt_hash(self._prompt_version)

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

    def _empty_response(self, ocr_text: str) -> LLMResponse:
        """Create response for empty input text."""
        return LLMResponse(
            original_text=ocr_text,
            corrected_text=ocr_text,
            model=self._model,
            prompt_version=self.get_prompt_hash(),
            input_tokens=0,
            output_tokens=0,
            diff_summary="(no changes)",
        )

    @abstractmethod
<<<<<<< HEAD
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
    def _build_request_body(self, ocr_text: str) -> dict:
        """Build model-specific request body.

        Args:
            ocr_text: The OCR text to correct.

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
            Tuple of (corrected_text, input_tokens, output_tokens).
        """
        pass

>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
    def correct_ocr_text(self, ocr_text: str) -> LLMResponse:
        """Correct OCR errors in the given text.

        Args:
            ocr_text: Raw OCR output text to correct.

        Returns:
            LLMResponse with original and corrected text.
        """
<<<<<<< HEAD
<<<<<<< HEAD
        if not ocr_text.strip():
            return self._empty_response(ocr_text)

        request_body = self._build_request_body(ocr_text)
        response_body = self._invoke_model(request_body)
        corrected_text, input_tokens, output_tokens = self._parse_response(response_body)

        return LLMResponse(
            original_text=ocr_text,
            corrected_text=corrected_text,
            model=self._model,
            prompt_version=self.get_prompt_hash(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            diff_summary=generate_diff(ocr_text, corrected_text),
        )
=======
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        pass
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
        if not ocr_text.strip():
            return self._empty_response(ocr_text)

        request_body = self._build_request_body(ocr_text)
        response_body = self._invoke_model(request_body)
        corrected_text, input_tokens, output_tokens = self._parse_response(response_body)

        return LLMResponse(
            original_text=ocr_text,
            corrected_text=corrected_text,
            model=self._model,
            prompt_version=self.get_prompt_hash(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            diff_summary=generate_diff(ocr_text, corrected_text),
        )
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
