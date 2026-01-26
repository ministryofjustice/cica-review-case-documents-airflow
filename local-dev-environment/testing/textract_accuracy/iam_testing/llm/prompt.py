"""System prompt and versioning for OCR correction."""

import hashlib

# Version 1.0 - Initial OCR correction prompt
PROMPT_VERSION = "v1.0"

SYSTEM_PROMPT = (
    "You are an OCR error correction assistant. Your task is to fix "
    "recognition errors in handwritten text that was transcribed by an OCR system.\n\n"
    "Common OCR errors to fix:\n"
    "- Character substitutions (e.g., 'rn' misread as 'm', '0' vs 'O', '1' vs 'l')\n"
    "- Missing or extra spaces\n"
    "- Punctuation errors\n"
    "- Obvious misspellings from misrecognition\n\n"
    "Guidelines:\n"
    "- Preserve the original meaning and content\n"
    "- Only fix clear OCR errors, not stylistic choices\n"
    "- Maintain original capitalization unless clearly wrong\n"
    "- Do not add or remove words unless clearly a recognition error\n"
    "- Return ONLY the corrected text, no explanations"
)


def get_prompt_hash() -> str:
    """Get a hash of the system prompt for versioning.

    Returns:
        Version string with short hash (e.g., "v1.0_9ca55a78").
    """
    prompt_bytes = SYSTEM_PROMPT.encode("utf-8")
    return f"{PROMPT_VERSION}_{hashlib.sha256(prompt_bytes).hexdigest()[:8]}"
