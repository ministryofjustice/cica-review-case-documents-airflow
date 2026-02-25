"""Vision model prompts for handwriting extraction.

Prompt variants are defined here. The prompt version is passed through
the client constructor rather than using global state.
"""

import hashlib

# =============================================================================
# Vision Prompt Variants
# =============================================================================

VISION_PROMPTS = {
    # v1: Basic handwriting extraction
    "v1": (
        "Extract all handwritten text from this image. "
        "Return ONLY the transcribed text, preserving the original structure and line breaks. "
        "Use British English (UK) spellings. "
        "If no handwritten text is visible, return an empty response."
    ),
    # v1.1: Clinical/mental health context
    "v1.1": (
        "Extract all handwritten text from this clinical/mental health document image. "
        "Return ONLY the transcribed text, preserving the original structure. "
        "These are often fragmented notes, not full sentences - preserve abbreviations and formatting. "
        "Use British English (UK) spellings. "
        "If no handwritten text is visible, return an empty response."
    ),
    # v1.2: Strict preservation - no interpretation
    "v1.2": (
        "Transcribe ALL handwritten text from this image exactly as written. "
        "Do NOT correct spelling, grammar, or formatting. "
        "Do NOT interpret abbreviations or shorthand. "
        "Preserve dates, times, and numbers exactly as they appear. "
        "Return ONLY the transcribed text. "
        "If no handwritten text is visible, return an empty response."
    ),
    # v1.3: Focus on legibility with best-guess
    "v1.3": (
        "Extract all handwritten text from this image. "
        "For illegible words, make your best single-word guess - do NOT skip them. "
        "Preserve the original structure and line breaks. "
        "Use British English (UK) spellings for clearly recognisable words. "
        "Return ONLY the transcribed text."
    ),
}

# Default prompt version
DEFAULT_VISION_PROMPT = "v1"


def validate_vision_prompt_version(version: str) -> str:
    """Validate and return the prompt version.

    Args:
        version: Prompt version string.

    Returns:
        Validated version string.

    Raises:
        ValueError: If version is not valid.
    """
    if version not in VISION_PROMPTS:
        raise ValueError(f"Unknown vision prompt version: {version}. Valid versions: {list(VISION_PROMPTS.keys())}")
    return version


def get_vision_prompt(version: str = DEFAULT_VISION_PROMPT) -> str:
    """Get the vision prompt text for a given version.

    Args:
        version: Prompt version to retrieve.

    Returns:
        The prompt text.
    """
    return VISION_PROMPTS.get(version, VISION_PROMPTS[DEFAULT_VISION_PROMPT])


def get_vision_prompt_hash(version: str = DEFAULT_VISION_PROMPT) -> str:
    """Get a hash of the vision prompt for versioning.

    Args:
        version: Prompt version.

    Returns:
        Version string with short hash suffix for reproducibility.
    """
    prompt_bytes = get_vision_prompt(version).encode("utf-8")
    return f"{version}_{hashlib.sha256(prompt_bytes).hexdigest()[:8]}"
