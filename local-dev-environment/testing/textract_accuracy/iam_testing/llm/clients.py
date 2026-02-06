"""AWS Bedrock LLM clients for OCR correction.

All Bedrock model implementations live here for easy extension.
To add a new model:
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
1. Create a subclass of BaseLLMClient
2. Define MODEL_IDS dict
3. Implement _build_request_body() and _parse_response()
4. Update SUPPORTED_MODELS and get_llm_client() in __init__.py
<<<<<<< HEAD
"""

from .base import BaseLLMClient

# User prompt template - shared across all models
USER_PROMPT = "Correct any OCR errors in this handwritten text:\n\n{ocr_text}"
=======
1. Add model IDs to the appropriate MODEL_IDS dict
2. If it uses a new API format, create a new client class
3. Update SUPPORTED_MODELS and get_llm_client() in __init__.py
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
"""

from .base import BaseLLMClient

<<<<<<< HEAD
logger = logging.getLogger(__name__)
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
# User prompt template - shared across all models
USER_PROMPT = "Correct any OCR errors in this handwritten text:\n\n{ocr_text}"
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)


# =============================================================================
# Amazon Nova Client
# =============================================================================


class BedrockNovaClient(BaseLLMClient):
    """AWS Bedrock Nova client for OCR correction.

    Uses Amazon Nova models via AWS Bedrock. These are auto-enabled
    and don't require marketplace subscription.
    """

    MODEL_IDS = {
        "nova-micro": "amazon.nova-micro-v1:0",
        "nova-lite": "amazon.nova-lite-v1:0",
        "nova-pro": "amazon.nova-pro-v1:0",
    }

<<<<<<< HEAD
<<<<<<< HEAD
    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Nova API request body."""
        return {
            "inferenceConfig": {"maxTokens": 4096},
            "system": [{"text": self.get_system_prompt()}],
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": USER_PROMPT.format(ocr_text=ocr_text)}],
=======
    def __init__(self, model: str = "nova-lite", region: str | None = None):
        """Initialize Bedrock Nova client.

        Args:
            model: Model shortname (nova-micro, nova-lite, nova-pro)
            region: AWS region. If None, uses default from settings.
        """
        import boto3

        from ..config import settings

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
        logger.info("Initialized Bedrock Nova client: %s in %s", self._model_id, self._region)

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        return self._model

    def correct_ocr_text(self, ocr_text: str) -> LLMResponse:
        """Correct OCR errors using Nova via Bedrock."""
        if not ocr_text.strip():
            return LLMResponse(
                original_text=ocr_text,
                corrected_text=ocr_text,
                model=self._model,
                prompt_version=self.get_prompt_hash(),
                input_tokens=0,
                output_tokens=0,
                diff_summary="(no changes)",
            )

        # Nova API format
        request_body = {
=======
    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Nova API request body."""
        return {
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
            "inferenceConfig": {"maxTokens": 4096},
            "system": [{"text": self.get_system_prompt()}],
            "messages": [
                {
                    "role": "user",
<<<<<<< HEAD
                    "content": [{"text": f"Correct any OCR errors in this handwritten text:\n\n{ocr_text}"}],
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
                    "content": [{"text": USER_PROMPT.format(ocr_text=ocr_text)}],
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
                }
            ],
        }

<<<<<<< HEAD
<<<<<<< HEAD
    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Nova API response."""
        corrected_text = response_body["output"]["message"]["content"][0]["text"]
        usage = response_body.get("usage", {})
        return corrected_text, usage.get("inputTokens", 0), usage.get("outputTokens", 0)
=======
        response = self._client.invoke_model(
            modelId=self._model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())
        corrected_text = response_body["output"]["message"]["content"][0]["text"]
        usage = response_body.get("usage", {})

        return LLMResponse(
            original_text=ocr_text,
            corrected_text=corrected_text,
            model=self._model,
            prompt_version=self.get_prompt_hash(),
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            diff_summary=generate_diff(ocr_text, corrected_text),
        )
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Nova API response."""
        corrected_text = response_body["output"]["message"]["content"][0]["text"]
        usage = response_body.get("usage", {})
        return corrected_text, usage.get("inputTokens", 0), usage.get("outputTokens", 0)
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)


# =============================================================================
# Anthropic Claude Client
# =============================================================================


class BedrockClaudeClient(BaseLLMClient):
    """AWS Bedrock Claude client for OCR correction.

    Uses Claude models via AWS Bedrock for secure, no-data-retention processing.
    Requires Bedrock model access to be enabled in the AWS console.
    """

    MODEL_IDS = {
        "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
        "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
        "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "claude-3-5-haiku": "anthropic.claude-3-5-haiku-20241022-v1:0",
    }

<<<<<<< HEAD
<<<<<<< HEAD
    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Claude API request body."""
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": self.get_system_prompt(),
            "messages": [
                {
                    "role": "user",
                    "content": USER_PROMPT.format(ocr_text=ocr_text),
=======
    def __init__(self, model: str = "claude-3-haiku", region: str | None = None):
        """Initialize Bedrock Claude client.

        Args:
            model: Model shortname (claude-3-haiku, claude-3-sonnet, etc.)
            region: AWS region. If None, uses default from settings.
        """
        import boto3

        from ..config import settings

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
        logger.info("Initialized Bedrock Claude client: %s in %s", self._model_id, self._region)

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        return self._model

    def correct_ocr_text(self, ocr_text: str) -> LLMResponse:
        """Correct OCR errors using Claude via Bedrock."""
        if not ocr_text.strip():
            return LLMResponse(
                original_text=ocr_text,
                corrected_text=ocr_text,
                model=self._model,
                prompt_version=self.get_prompt_hash(),
                input_tokens=0,
                output_tokens=0,
                diff_summary="(no changes)",
            )

        # Claude API format
        request_body = {
=======
    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Claude API request body."""
        return {
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": self.get_system_prompt(),
            "messages": [
                {
                    "role": "user",
<<<<<<< HEAD
                    "content": f"Correct any OCR errors in this handwritten text:\n\n{ocr_text}",
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
                    "content": USER_PROMPT.format(ocr_text=ocr_text),
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
                }
            ],
        }

<<<<<<< HEAD
<<<<<<< HEAD
    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Claude API response."""
        corrected_text = response_body["content"][0]["text"]
        usage = response_body.get("usage", {})
        return corrected_text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


# =============================================================================
# Meta Llama Client
# =============================================================================


class BedrockLlamaClient(BaseLLMClient):
    """AWS Bedrock Llama client for OCR correction.

    Uses Meta Llama models via AWS Bedrock. These are typically auto-enabled
    and don't require marketplace subscription.
    """

    MODEL_IDS = {
        "llama-3-8b": "meta.llama3-8b-instruct-v1:0",
        "llama-3-70b": "meta.llama3-70b-instruct-v1:0",
        "llama-3-1-8b": "meta.llama3-1-8b-instruct-v1:0",
        "llama-3-1-70b": "meta.llama3-1-70b-instruct-v1:0",
    }

    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Llama API request body."""
        # Llama concatenates system + user in prompt
        prompt = f"{self.get_system_prompt()}\n\n{USER_PROMPT.format(ocr_text=ocr_text)}"
        return {
            "prompt": prompt,
            "max_gen_len": 4096,
            "temperature": 0.1,
        }

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Llama API response."""
        corrected_text = response_body.get("generation", "").strip()
        input_tokens = response_body.get("prompt_token_count", 0)
        output_tokens = response_body.get("generation_token_count", 0)
        return corrected_text, input_tokens, output_tokens


# =============================================================================
# Mistral Client
# =============================================================================


class BedrockMistralClient(BaseLLMClient):
    """AWS Bedrock Mistral client for OCR correction.

    Uses Mistral models via AWS Bedrock.
    """

    MODEL_IDS = {
        "mistral-7b": "mistral.mistral-7b-instruct-v0:2",
        "mixtral-8x7b": "mistral.mixtral-8x7b-instruct-v0:1",
        "mistral-large": "mistral.mistral-large-2402-v1:0",
    }

    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Mistral API request body."""
        # Mistral uses [INST] tags
        prompt = f"<s>[INST] {self.get_system_prompt()}\n\n{USER_PROMPT.format(ocr_text=ocr_text)} [/INST]"
        return {
            "prompt": prompt,
            "max_tokens": 4096,
            "temperature": 0.1,
        }

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Mistral API response."""
        outputs = response_body.get("outputs", [{}])
        corrected_text = outputs[0].get("text", "").strip() if outputs else ""
        # Mistral doesn't return token counts in this format
        return corrected_text, 0, 0
=======
        response = self._client.invoke_model(
            modelId=self._model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())
=======
    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Claude API response."""
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
        corrected_text = response_body["content"][0]["text"]
        usage = response_body.get("usage", {})
        return corrected_text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


# =============================================================================
# Meta Llama Client
# =============================================================================
<<<<<<< HEAD
# Example: Meta Llama, Mistral, etc.
#
# class BedrockLlamaClient(BaseLLMClient):
#     MODEL_IDS = {
#         "llama-3-8b": "meta.llama3-8b-instruct-v1:0",
#         "llama-3-70b": "meta.llama3-70b-instruct-v1:0",
#     }
#     ...
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======


class BedrockLlamaClient(BaseLLMClient):
    """AWS Bedrock Llama client for OCR correction.

    Uses Meta Llama models via AWS Bedrock. These are typically auto-enabled
    and don't require marketplace subscription.
    """

    MODEL_IDS = {
        "llama-3-8b": "meta.llama3-8b-instruct-v1:0",
        "llama-3-70b": "meta.llama3-70b-instruct-v1:0",
        "llama-3-1-8b": "meta.llama3-1-8b-instruct-v1:0",
        "llama-3-1-70b": "meta.llama3-1-70b-instruct-v1:0",
    }

    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Llama API request body."""
        # Llama concatenates system + user in prompt
        prompt = f"{self.get_system_prompt()}\n\n{USER_PROMPT.format(ocr_text=ocr_text)}"
        return {
            "prompt": prompt,
            "max_gen_len": 4096,
            "temperature": 0.1,
        }

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Llama API response."""
        corrected_text = response_body.get("generation", "").strip()
        input_tokens = response_body.get("prompt_token_count", 0)
        output_tokens = response_body.get("generation_token_count", 0)
        return corrected_text, input_tokens, output_tokens


# =============================================================================
# Mistral Client
# =============================================================================


class BedrockMistralClient(BaseLLMClient):
    """AWS Bedrock Mistral client for OCR correction.

    Uses Mistral models via AWS Bedrock.
    """

    MODEL_IDS = {
        "mistral-7b": "mistral.mistral-7b-instruct-v0:2",
        "mixtral-8x7b": "mistral.mixtral-8x7b-instruct-v0:1",
        "mistral-large": "mistral.mistral-large-2402-v1:0",
    }

    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Mistral API request body."""
        # Mistral uses [INST] tags
        prompt = f"<s>[INST] {self.get_system_prompt()}\n\n{USER_PROMPT.format(ocr_text=ocr_text)} [/INST]"
        return {
            "prompt": prompt,
            "max_tokens": 4096,
            "temperature": 0.1,
        }

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Mistral API response."""
        outputs = response_body.get("outputs", [{}])
        corrected_text = outputs[0].get("text", "").strip() if outputs else ""
        # Mistral doesn't return token counts in this format
        return corrected_text, 0, 0
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
