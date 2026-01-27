"""LLM response data structure."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Response from LLM text correction.

    Attributes:
        original_text: The input OCR text.
        corrected_text: The LLM-corrected text.
        model: Model identifier (e.g., "nova-lite").
        prompt_version: Hash of system prompt for reproducibility.
        input_tokens: Number of input tokens used.
        output_tokens: Number of output tokens generated.
        diff_summary: Human-readable summary of changes made.
    """

    original_text: str
    corrected_text: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    diff_summary: str
