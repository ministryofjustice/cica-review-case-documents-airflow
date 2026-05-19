"""LLM clients for OCR correction.

All model implementations live here for easy extension.
To add a new model:
1. Create a subclass of BaseLLMClient
2. Define MODEL_IDS dict
3. Implement _build_request_body() and _parse_response()
4. Update SUPPORTED_MODELS and get_llm_client() in __init__.py
"""

import logging
import os

from iam_testing.llm.base import BaseLLMClient
from iam_testing.llm.diff import generate_diff
from iam_testing.llm.prompt import DEFAULT_PROMPT, get_prompt_hash, get_system_prompt, validate_prompt_version
from iam_testing.llm.response import LLMResponse

# User prompt template - shared across all models
USER_PROMPT = "Correct any OCR errors in this handwritten text:\n\n{ocr_text}"


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

    def _build_request_body(self, ocr_text: str) -> dict:
        """Build Nova API request body."""
        return {
            "inferenceConfig": {"maxTokens": 4096},
            "system": [{"text": self.get_system_prompt()}],
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": USER_PROMPT.format(ocr_text=ocr_text)}],
                }
            ],
        }

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Parse Nova API response."""
        corrected_text = response_body["output"]["message"]["content"][0]["text"]
        usage = response_body.get("usage", {})
        return corrected_text, usage.get("inputTokens", 0), usage.get("outputTokens", 0)


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
                }
            ],
        }

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


# =============================================================================
# LiteLLM Gateway Client (OpenAI-compatible)
# =============================================================================

LITELLM_BASE_URL = "https://llm-gateway.development.data-platform.service.justice.gov.uk"

logger = logging.getLogger(__name__)


class LiteLLMClient(BaseLLMClient):
    """OCR correction client using the MoJ LiteLLM proxy gateway.

    Uses the OpenAI SDK to call models via the LiteLLM proxy.
    Requires OPENAI_KEY environment variable to be set.
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
        prompt_version: str = DEFAULT_PROMPT,
    ):
        """Initialize LiteLLM gateway client.

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

        self._prompt_version = validate_prompt_version(prompt_version)
        self._model = model
        self._model_id = self.MODEL_IDS.get(model, model)

        import openai

        self._openai_client = openai.OpenAI(
            api_key=api_key,
            base_url=LITELLM_BASE_URL,
        )
        logger.info(
            "Initialized LiteLLMClient: %s (prompt: %s)",
            self._model_id,
            prompt_version,
        )

    def _build_request_body(self, ocr_text: str) -> dict:
        """Not used — correct_ocr_text is overridden."""
        raise NotImplementedError("LiteLLMClient uses the OpenAI SDK directly")

    def _parse_response(self, response_body: dict) -> tuple[str, int, int]:
        """Not used — correct_ocr_text is overridden."""
        raise NotImplementedError("LiteLLMClient uses the OpenAI SDK directly")

    def correct_ocr_text(self, ocr_text: str) -> LLMResponse:
        """Correct OCR errors using the LiteLLM gateway.

        Args:
            ocr_text: Raw OCR output text to correct.

        Returns:
            LLMResponse with original and corrected text.
        """
        if not ocr_text.strip():
            return LLMResponse(
                original_text=ocr_text,
                corrected_text=ocr_text,
                model=self._model,
                prompt_version=get_prompt_hash(self._prompt_version),
                input_tokens=0,
                output_tokens=0,
                diff_summary="(no changes)",
            )

        user_prompt = USER_PROMPT.format(ocr_text=ocr_text)
        system_prompt = get_system_prompt(self._prompt_version)

        response = self._openai_client.chat.completions.create(
            model=self._model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4096,
        )

        corrected_text = (response.choices[0].message.content or "").strip()
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return LLMResponse(
            original_text=ocr_text,
            corrected_text=corrected_text,
            model=self._model,
            prompt_version=get_prompt_hash(self._prompt_version),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            diff_summary=generate_diff(ocr_text, corrected_text),
        )
