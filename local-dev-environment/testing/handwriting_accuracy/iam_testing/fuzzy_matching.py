"""Fuzzy keyword matching using Levenshtein similarity."""

import re

from rapidfuzz import fuzz

SIMILARITY_THRESHOLD = 85  # 85% similarity required


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _get_words(text: str) -> list[str]:
    return _normalize(text).split()


def score_keyword_recall_fuzzy(
    keywords: list[str], ocr_text: str, threshold: int = SIMILARITY_THRESHOLD
) -> tuple[float, list[str], list[str]]:
    """Calculate keyword recall using fuzzy matching.

    Matches if any OCR word has ≥threshold% Levenshtein similarity to keyword.
    """
    if not keywords:
        return 1.0, [], []

    ocr_words = _get_words(ocr_text)
    found, missing = [], []

    for kw in keywords:
        kw_norm = _normalize(kw)
        matched = any(fuzz.ratio(kw_norm, w) >= threshold for w in ocr_words)
        (found if matched else missing).append(kw)

    return len(found) / len(keywords), found, missing
