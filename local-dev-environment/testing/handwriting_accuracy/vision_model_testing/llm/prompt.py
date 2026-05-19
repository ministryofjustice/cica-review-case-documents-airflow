"""Vision model prompts for handwriting extraction.

Prompt variants are defined here. The prompt version is passed through
the client constructor rather than using global state.

All prompts exclude crossed-out or struck-through text by default.

Prompt versions:
    v1.5         — direct vision, handwriting only, form chrome suppressed
    v1.5-mm      — multimodal flat OCR hint (best evaluated, avg WER 0.1522)
    v1.5-mm-struct2  — multimodal structured OCR table, all words as context
"""

import hashlib

VISION_PROMPTS = {
    # v1.5: Direct vision — handwriting only, suppress printed form chrome
    "v1.5": (
        "Transcribe ONLY the handwritten text from this clinical document image exactly as written. "
        "This document is a structured form with pre-printed labels, column headers, field names, "
        "Yes/No checkboxes, time-slot row labels, and page numbers — do NOT include any of these. "
        "Output only the handwritten entries that someone has written into the form. "
        "Do NOT include any text that has been crossed out or struck through — if a word or line "
        "has a horizontal line drawn through it, omit it entirely. "
        "Do NOT correct spelling, grammar, or abbreviations. "
        "For illegible words, make your best single-word guess — do NOT skip them. "
        "For dates and times, use forward slashes as separators (e.g. 15/01/2020), not pipe symbols. "
        "For letters inside a circle (e.g. circled R or circled L), output just the letter (R or L), "
        "not a special character such as a copyright or registered symbol. "
        "Preserve line structure of the handwritten entries. "
        "Return ONLY the transcribed handwritten text."
    ),
    # v1.5-mm: Multimodal flat OCR hint (best evaluated approach)
    "v1.5-mm": (
        "You are given a clinical document image and a reference OCR transcription of it. "
        "Use the OCR as a guide for the overall structure and word order, but prioritise what you "
        "can see in the image — correct any OCR character misrecognitions or spacing errors using "
        "the visual content. "
        "Transcribe ONLY the handwritten text from the image exactly as written. "
        "Do NOT include pre-printed labels, column headers, field names, Yes/No checkboxes, "
        "time-slot row labels, or page numbers. "
        "Do NOT include any text that has been crossed out or struck through — if a word or line "
        "has a horizontal line drawn through it, omit it entirely. "
        "Do NOT correct spelling, grammar, or abbreviations in the handwriting. "
        "For illegible words, make your best single-word guess — do NOT skip them. "
        "For dates and times, use forward slashes as separators (e.g. 15/01/2020), not pipe symbols. "
        "For letters inside a circle (e.g. circled R or circled L), output just the letter (R or L), "
        "not a special character such as a copyright or registered symbol. "
        "Preserve line structure exactly as it appears. "
        "Return ONLY the transcribed handwritten text."
    ),
    # v1.5-mm-struct2: Multimodal structured OCR — all words as full page context
    "v1.5-mm-struct2": (
        "You are given a clinical document image and a structured OCR word list from Textract. "
        "Each line of the word list is: top left text type confidence — where top/left are "
        "fractional page positions (0.0=top/left edge, 1.0=bottom/right edge), type is PRINTED "
        "or HANDWRITING, and confidence is 0-100. "
        "The word list contains ALL detected words on the page — both printed form labels and "
        "handwritten entries — giving you the complete spatial layout and reading order. "
        "Use the full word list to understand the page structure: PRINTED words tell you where "
        "form fields, column headers, and labels are; HANDWRITING words are the entries to transcribe. "
        "Transcribe ONLY the handwritten entries from the image. "
        "Do NOT include pre-printed form labels, column headers, checkbox labels, row headings, or page numbers. "
        "Do NOT include any text that has been crossed out or struck through — if a word or line "
        "has a horizontal line drawn through it, omit it entirely. "
        "For words with low confidence (below 80), look closely at the image to determine the correct word — "
        "do NOT skip them. "
        "Do NOT correct spelling, grammar, or abbreviations. "
        "For dates and times, use forward slashes as separators (e.g. 15/01/2020), not pipe symbols. "
        "For letters inside a circle (e.g. circled R or circled L), output just the letter (R or L), "
        "not a special character such as a copyright or registered symbol. "
        "Preserve the spatial line structure of the handwritten entries. "
        "Return ONLY the transcribed handwritten text."
    ),
}

# Default prompt version
DEFAULT_VISION_PROMPT = "v1.5"


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
