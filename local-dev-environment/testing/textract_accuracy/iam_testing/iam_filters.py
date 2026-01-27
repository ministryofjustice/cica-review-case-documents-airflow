"""IAM dataset-specific filters for OCR post-processing.

The IAM handwriting dataset has a specific format with printed headers/footers
that need to be filtered out when comparing handwriting OCR results.
"""

import logging
import re

from .schemas import WordBlock

logger = logging.getLogger(__name__)

# IAM dataset header patterns to filter from printed text
IAM_HEADER_PATTERNS = [
    r"^Sentence$",  # "Sentence" word from header
    r"^Database$",  # "Database" word from header
    r"^[A-Z]\d{2}-\d{3}[a-z]?$",  # Form ID pattern like "A01-000u" or "A01-000"
]

# IAM dataset footer patterns to filter from printed text
IAM_FOOTER_PATTERNS = [
    r"^Name:$",  # "Name:" label at bottom of form
]

# Threshold for header region (top 15% of page)
HEADER_THRESHOLD = 0.15

# Threshold for footer region (words below this are considered footer)
FOOTER_THRESHOLD = 0.75

# Tolerance for signature detection near Name: label
SIGNATURE_TOLERANCE = 0.05


def filter_iam_header_footer(
    words: list[WordBlock],
) -> tuple[list[WordBlock], float | None]:
    """Filter IAM dataset header and footer words from printed text.

    The IAM dataset images contain:
    - A printed header with "Sentence Database" and form ID (e.g., "A01-000u")
    - A printed footer with "Name:" label

    Args:
        words: List of WordBlock objects (printed words only).

    Returns:
        Tuple of (filtered list with header/footer words removed,
                  vertical position of "Name:" footer if found).
    """
    if not words:
        return words, None

    filtered = []
    name_label_top: float | None = None

    for word in words:
        # Skip words in header region that match header patterns
        if word.bbox_top < HEADER_THRESHOLD:
            is_header = any(re.match(pattern, word.text, re.IGNORECASE) for pattern in IAM_HEADER_PATTERNS)
            if is_header:
                logger.debug("Filtered header word: %s", word.text)
                continue

        # Skip words in footer region that match footer patterns
        if word.bbox_top > FOOTER_THRESHOLD:
            is_footer = any(re.match(pattern, word.text, re.IGNORECASE) for pattern in IAM_FOOTER_PATTERNS)
            if is_footer:
                logger.debug("Filtered footer word: %s at top=%.4f", word.text, word.bbox_top)
                name_label_top = word.bbox_top
                continue

        filtered.append(word)

    return filtered, name_label_top


def filter_iam_signature(words: list[WordBlock], name_label_top: float | None) -> list[WordBlock]:
    """Filter handwritten signature text near the Name: label.

    Removes handwriting at similar vertical position to the "Name:" label,
    which is typically a signature and not part of the ground truth.

    Args:
        words: List of WordBlock objects (handwriting words only).
        name_label_top: Vertical position of "Name:" label, or None if not found.

    Returns:
        Filtered list with signature words removed.
    """
    if not words or name_label_top is None:
        return words

    # Filter handwriting within a small vertical range of the Name: label
    signature_min = name_label_top - SIGNATURE_TOLERANCE
    signature_max = name_label_top + SIGNATURE_TOLERANCE

    filtered = []
    for word in words:
        if signature_min <= word.bbox_top <= signature_max:
            logger.debug(
                "Filtered signature word: %s at top=%.4f (near Name: at %.4f)",
                word.text,
                word.bbox_top,
                name_label_top,
            )
            continue
        filtered.append(word)

    return filtered


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Applies standard normalization:
    - Collapse multiple spaces to single space
    - Strip leading/trailing whitespace

    Args:
        text: Input text.

    Returns:
        Normalized text.
    """
    return " ".join(text.split())
