"""Porter2 stemmed keyword matching."""

import re

import snowballstemmer

_stemmer = snowballstemmer.stemmer("english")


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _stem_words(text: str) -> set[str]:
    return set(_stemmer.stemWords(_normalize(text).split()))


def score_keyword_recall_stemmed(keywords: list[str], ocr_text: str) -> tuple[float, list[str], list[str]]:
    """Calculate keyword recall using Porter2 stemming.

    Matches if the stem of any keyword word appears in stemmed OCR text.
    """
    if not keywords:
        return 1.0, [], []

    ocr_stems = _stem_words(ocr_text)
    found, missing = [], []

    for kw in keywords:
        kw_stems = _stem_words(kw)
        if kw_stems & ocr_stems:
            found.append(kw)
        else:
            missing.append(kw)

    return len(found) / len(keywords), found, missing
