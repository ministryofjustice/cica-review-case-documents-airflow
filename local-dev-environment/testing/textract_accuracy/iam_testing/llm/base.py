"""Abstract base class for LLM clients."""

import logging
from abc import ABC, abstractmethod

from .prompt import SYSTEM_PROMPT, get_prompt_hash
from .response import LLMResponse

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.

    All LLM clients share the same system prompt and versioning logic.
    Subclasses implement the actual API calls for different providers.
    """

    # Shared prompt (use functions from prompt.py)
    SYSTEM_PROMPT = SYSTEM_PROMPT

    @classmethod
    def get_prompt_hash(cls) -> str:
        """Get a hash of the system prompt for versioning."""
        return get_prompt_hash()

    @abstractmethod
    def correct_ocr_text(self, ocr_text: str) -> LLMResponse:
        """Correct OCR errors in the given text.

        Args:
            ocr_text: Raw OCR output text to correct.

        Returns:
            LLMResponse with original and corrected text.
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        pass
