"""Vision model response dataclass."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VisionResponse:
    """Response from vision model image-to-text extraction.

    Attributes:
        extracted_text: The text extracted from the image.
        model: Model identifier used for extraction.
        prompt_version: Hash of the prompt used for reproducibility.
        input_tokens: Number of input tokens (including image).
        output_tokens: Number of output tokens generated.
        image_path: Path to the source image file.
    """

    extracted_text: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    image_path: str
