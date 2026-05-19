"""Vision model prompts for production document processing.

These prompts are intended for use in the live pipeline, where model inputs
are chunks of document pages that contain some handwriting alongside pre-printed
form content.  Unlike the evaluation prompts (prompt.py), these prompts ask the
model to transcribe *all* visible text — printed and handwritten — rather than
handwriting only.

Prompt versioning follows the same conventions as prompt.py.
"""

import hashlib

# =============================================================================
# Production Prompt Variants
# =============================================================================

PRODUCTION_PROMPTS = {
    # v1.0-prod: Full-page transcription with selective spelling inference
    "v1.0-prod": (
        "Transcribe ALL text visible in this document image — both pre-printed labels, "
        "headings, and field names, and any handwritten entries. "
        "Do NOT omit, paraphrase, or add any content. "
        "Do NOT correct grammar, punctuation, or abbreviations. "
        "Do NOT reformat or restructure the content. "
        "For handwritten words that are clearly legible, preserve the exact spelling as written, "
        "even if it is misspelt. "
        "For handwritten words that are genuinely illegible or ambiguous, output the most likely "
        "correctly-spelled word — do NOT skip them or mark them as unreadable. "
        "Preserve the line structure and layout of the original document as closely as possible. "
        "Return ONLY the transcribed text."
    ),
}

# Default prompt version
DEFAULT_PRODUCTION_PROMPT = "v1.0-prod"


def validate_production_prompt_version(version: str) -> str:
    """Validate and return the production prompt version.

    Args:
        version: Prompt version string.

    Returns:
        Validated version string.

    Raises:
        ValueError: If version is not recognised.
    """
    if version not in PRODUCTION_PROMPTS:
        raise ValueError(
            f"Unknown production prompt version: {version}. Valid versions: {list(PRODUCTION_PROMPTS.keys())}"
        )
    return version


def get_production_prompt(version: str = DEFAULT_PRODUCTION_PROMPT) -> str:
    """Get the production prompt text for a given version.

    Args:
        version: Prompt version to retrieve.

    Returns:
        The prompt text.
    """
    return PRODUCTION_PROMPTS.get(version, PRODUCTION_PROMPTS[DEFAULT_PRODUCTION_PROMPT])


def get_production_prompt_hash(version: str = DEFAULT_PRODUCTION_PROMPT) -> str:
    """Get a short hash of the production prompt for reproducibility tracking.

    Args:
        version: Prompt version.

    Returns:
        Version string with short SHA-256 suffix.
    """
    prompt_bytes = get_production_prompt(version).encode("utf-8")
    return f"{version}_{hashlib.sha256(prompt_bytes).hexdigest()[:8]}"
