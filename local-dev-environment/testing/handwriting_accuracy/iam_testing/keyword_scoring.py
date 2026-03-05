"""Keyword-based scoring for difficult-to-read handwritten documents.

For pages that are too degraded for full transcription, this module provides
keyword recall scoring: what percentage of identifiable keywords were found
in the OCR output.

Usage:
    from iam_testing.keyword_scoring import score_keyword_recall, load_keyword_ground_truth

    keywords = ["NHS", "2020", "assessment", "medication"]
    ocr_text = "nhs assessment for medication in 2020"
    score = score_keyword_recall(keywords, ocr_text)
    # Returns KeywordScore with recall, found_keywords, missing_keywords
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KeywordGroundTruth:
    """Ground truth record for keyword-based scoring."""

    page_id: str
    image_path: str
    keywords: list[str]


@dataclass(frozen=True, slots=True)
class KeywordScore:
    """Result of keyword recall scoring."""

    page_id: str
    keyword_recall: float  # 0.0 to 1.0
    keywords_found: int
    keywords_total: int
    found_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]


def normalize_for_matching(text: str) -> str:
    """Normalize text for keyword matching.

    Converts to lowercase, removes punctuation, and collapses whitespace.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def score_keyword_recall(
    keywords: list[str],
    ocr_text: str,
    *,
    case_sensitive: bool = False,
) -> tuple[float, list[str], list[str]]:
    """Calculate keyword recall from OCR output.

    Args:
        keywords: List of expected keywords to find.
        ocr_text: OCR output text to search.
        case_sensitive: Whether matching is case-sensitive.

    Returns:
        Tuple of (recall_score, found_keywords, missing_keywords).
        Recall is 0.0-1.0, representing percentage of keywords found.
    """
    if not keywords:
        return 1.0, [], []

    # Normalize for matching
    search_text = ocr_text if case_sensitive else normalize_for_matching(ocr_text)

    found = []
    missing = []

    for keyword in keywords:
        search_keyword = keyword if case_sensitive else normalize_for_matching(keyword)

        # Use word boundary matching to avoid partial matches
        # e.g., "at" shouldn't match "patient"
        pattern = rf"\b{re.escape(search_keyword)}\b"
        if re.search(pattern, search_text):
            found.append(keyword)
        else:
            missing.append(keyword)

    recall = len(found) / len(keywords)
    return recall, found, missing


def load_keyword_ground_truth(gt_path: Path) -> dict[str, KeywordGroundTruth]:
    """Load keyword ground truth from JSONL file.

    Expected format:
        {"page_id": "...", "image_path": "...", "keywords": ["word1", "word2", ...]}

    Args:
        gt_path: Path to keyword ground truth JSONL file.

    Returns:
        Dict mapping page_id to KeywordGroundTruth records.
    """
    if not gt_path.exists():
        raise FileNotFoundError(f"Keyword ground truth file not found: {gt_path}")

    records = {}
    with open(gt_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                page_id = data.get("page_id")
                image_path = data.get("image_path")
                keywords = data.get("keywords", [])

                if not page_id or not image_path:
                    logger.warning(
                        "Line %d missing required fields (page_id, image_path)",
                        line_num,
                    )
                    continue

                if not keywords:
                    logger.warning(
                        "Line %d (%s): No keywords defined, skipping",
                        line_num,
                        page_id,
                    )
                    continue

                records[page_id] = KeywordGroundTruth(
                    page_id=page_id,
                    image_path=image_path,
                    keywords=keywords,
                )
            except json.JSONDecodeError as e:
                logger.warning("Line %d: Invalid JSON: %s", line_num, e)
                continue

    logger.info("Loaded %d keyword ground truth records from %s", len(records), gt_path)
    return records


def score_page_keywords(
    page_id: str,
    ocr_text: str,
    gt: KeywordGroundTruth,
) -> KeywordScore:
    """Score a single page using keyword recall.

    Args:
        page_id: Page identifier.
        ocr_text: OCR output text.
        gt: Keyword ground truth record.

    Returns:
        KeywordScore with recall metrics.
    """
    recall, found, missing = score_keyword_recall(gt.keywords, ocr_text)

    return KeywordScore(
        page_id=page_id,
        keyword_recall=recall,
        keywords_found=len(found),
        keywords_total=len(gt.keywords),
        found_keywords=tuple(found),
        missing_keywords=tuple(missing),
    )
