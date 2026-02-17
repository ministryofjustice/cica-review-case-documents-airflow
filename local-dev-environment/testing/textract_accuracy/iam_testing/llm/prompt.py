"""System prompt and versioning for OCR correction.

Prompt variants are defined here. The prompt version is passed through
the client constructor rather than using global state.
"""

import hashlib

# =============================================================================
# Prompt Variants
# =============================================================================

PROMPTS = {
    # v2: Concise prompt - minimal instructions
    "v2": (
        "Fix OCR errors in the following handwritten text transcription. "
        "Correct character misrecognitions, spacing issues, and obvious typos. "
        "Preserve proper nouns (names, places) and short ambiguous words (in/is/on, we/he) exactly as written. "
        "Use British English (UK) spellings. "
        "Return ONLY the corrected text."
    ),
    # v2.1: Concise prompt with anti-insertion rules
    "v2.1": (
        "Fix OCR errors in the following handwritten text transcription. "
        "Correct character misrecognitions, spacing issues, and obvious typos. "
        "Do NOT add, remove, or rephrase words - only fix recognition errors. "
        "Keep compound words and place names intact (e.g., 'Bowstreet' stays as one word). "
        "Preserve proper nouns (names, places) and short ambiguous words (in/is/on, we/he) exactly. "
        "If the text appears correct, return it unchanged. "
        "Use British English (UK) spellings. "
        "Return ONLY the corrected text."
    ),
    # v2.2: More concise, allows well-known proper noun correction
    "v2.2": (
        "Fix OCR errors in handwritten text. Correct misrecognitions and spacing. "
        "Do NOT add or remove words. Keep compound words intact. "
        "Fix obvious proper noun misspellings but preserve ambiguous short words (in/is/on, we/he). "
        "Use British English. Return ONLY the corrected text."
    ),
    # v2.3: v2 + single anti-insertion constraint (minimal token increase)
    "v2.3": (
        "Fix OCR errors in the following handwritten text transcription. "
        "Correct character misrecognitions, spacing issues, and obvious typos. "
        "Do NOT add or remove words. "
        "Preserve proper nouns (names, places) and short ambiguous words (in/is/on, we/he) exactly as written. "
        "Use British English (UK) spellings. "
        "Return ONLY the corrected text."
    ),
    # v2.4: Domain-specific for clinical/mental health notes (CICA documents)
    "v2.4": (
        "Fix OCR errors in handwritten clinical/mental health notes. "
        "Correct character misrecognitions, spacing issues, and obvious typos. "
        "Do NOT add or remove words. "
        "Use British English (UK) spellings. "
        "Return ONLY the corrected text."
    ),
    # v2.5: Clinical domain + fragmented note structure + strict preservation
    "v2.5": (
        "Fix OCR errors in handwritten clinical/mental health notes. "
        "These are often fragmented notes, not full sentences - preserve the original structure. "
        "Correct character misrecognitions and spacing issues only. "
        "Do NOT add, remove, or rearrange words. Do NOT add punctuation. "
        "Preserve dates, times, and abbreviations exactly as written. "
        "Use British English. Return ONLY the corrected text."
    ),
    # v2.6: Clinical domain + no multi-word deletions, best-guess unrecognisable words
    "v2.6": (
        "Fix OCR errors in handwritten clinical/mental health notes. "
        "Correct character misrecognitions and spacing issues only. "
        "Do NOT delete multiple words or replace a sequence of words with fewer words. "
        "If a word is unrecognisable, make your best single-word guess - do NOT skip it. "
        "Preserve dates (e.g., 15/05/2020), times (e.g., 23.20hr), and abbreviations exactly. "
        "Use British English (UK) spellings. "
        "Return ONLY the corrected text."
    ),
}

# Default prompt version
DEFAULT_PROMPT = "v2"

# For backwards compatibility
SYSTEM_PROMPT = PROMPTS[DEFAULT_PROMPT]


def validate_prompt_version(version: str) -> str:
    """Validate and return the prompt version."""
    if version not in PROMPTS:
        raise ValueError(f"Unknown prompt version: {version}. Valid: {list(PROMPTS.keys())}")
    return version


def get_system_prompt(version: str = DEFAULT_PROMPT) -> str:
    """Get the system prompt text for a given version."""
    return PROMPTS.get(version, PROMPTS[DEFAULT_PROMPT])


def get_prompt_hash(version: str = DEFAULT_PROMPT) -> str:
    """Get a hash of the system prompt for versioning."""
    prompt_bytes = get_system_prompt(version).encode("utf-8")
    return f"{version}_{hashlib.sha256(prompt_bytes).hexdigest()[:8]}"
