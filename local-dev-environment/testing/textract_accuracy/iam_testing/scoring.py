"""OCR scoring module with WER/CER metrics using jiwer.

This module consolidates ground truth loading and accuracy scoring.

Metrics:
    - WER (Word Error Rate): Fraction of words that are wrong
    - CER (Character Error Rate): Fraction of characters that are wrong

Install: uv pip install jiwer
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from jiwer import cer, wer

from .iam_filters import normalize_text
from .schemas import OCRResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """OCR accuracy score for a single form with separate print/handwriting metrics."""

    form_id: str
    # Handwriting metrics
    wer_handwriting: float  # Word Error Rate (0.0 = perfect, 1.0 = all wrong)
    cer_handwriting: float  # Character Error Rate
    gt_handwriting_word_count: int  # gt->ground truth
    ocr_handwriting_word_count: int
    gt_handwriting_text: str
    ocr_handwriting_text: str
    # Print metrics
    wer_print: float
    cer_print: float
    gt_print_word_count: int
    ocr_print_word_count: int
    gt_print_text: str
    ocr_print_text: str


def load_all_ground_truth(gt_path: Path) -> dict[str, dict]:
    """Load all ground truth records into a dict for fast lookup.

    Args:
        gt_path: Path to ground_truth.jsonl file.

    Returns:
        Dict mapping form_id to ground truth record.
    """
    if not gt_path.exists():
        logger.warning("Ground truth file not found: %s", gt_path)
        return {}

    records = {}
    with open(gt_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            form_id = record.get("form_id")
            if form_id:
                records[form_id] = record

    logger.info("Loaded %d ground truth records", len(records))
    return records


def _calculate_wer_cer(gt_text: str, ocr_text: str, form_id: str, text_type: str) -> tuple[float, float]:
    """Calculate WER and CER for a text pair.

    Args:
        gt_text: Ground truth text (normalized).
        ocr_text: OCR output text.
        form_id: Form ID for logging.
        text_type: 'handwriting' or 'print' for logging.

    Returns:
        Tuple of (wer, cer).
    """
    if not gt_text.strip():
        logger.warning("Empty %s ground truth for form %s", text_type, form_id)
        return (1.0, 1.0) if ocr_text.strip() else (0.0, 0.0)
    if not ocr_text.strip():
        return (1.0, 1.0)

    return (wer(gt_text, ocr_text), cer(gt_text, ocr_text))


def score_ocr_result(result: OCRResult, gt: dict) -> ScoreResult:
    """Calculate WER and CER for an OCR result against ground truth.

    Args:
        result: OCRResult object from Textract processing.
        gt: Ground truth record dict with gt_handwriting_text and gt_print_text fields.

    Returns:
        ScoreResult with separate WER/CER for handwriting and print.

    Note:
        Both texts are normalized before scoring to ensure fair comparison.
        Print text comparison uses filtered OCR output vs ground truth.
    """
    # Handwriting scoring
    gt_hw_text = normalize_text(gt.get("gt_handwriting_text", ""))
<<<<<<< HEAD
    # Normalize OCR output before scoring to match ground truth normalization
    ocr_hw_text = normalize_text(result.ocr_handwriting_text)
=======
    ocr_hw_text = result.ocr_handwriting_text
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
    wer_hw, cer_hw = _calculate_wer_cer(gt_hw_text, ocr_hw_text, result.form_id, "handwriting")

    # Print scoring (uses filtered OCR output)
    gt_print_text = normalize_text(gt.get("gt_print_text", ""))
<<<<<<< HEAD
    # Normalize OCR print text as well
    ocr_print_text = normalize_text(result.ocr_print_text)
=======
    ocr_print_text = result.ocr_print_text
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
    wer_print, cer_print = _calculate_wer_cer(gt_print_text, ocr_print_text, result.form_id, "print")

    return ScoreResult(
        form_id=result.form_id,
        # Handwriting
        wer_handwriting=round(wer_hw, 4),
        cer_handwriting=round(cer_hw, 4),
        gt_handwriting_word_count=len(gt_hw_text.split()),
        ocr_handwriting_word_count=len(ocr_hw_text.split()),
        gt_handwriting_text=gt_hw_text,
        ocr_handwriting_text=ocr_hw_text,
        # Print
        wer_print=round(wer_print, 4),
        cer_print=round(cer_print, 4),
        gt_print_word_count=len(gt_print_text.split()),
        ocr_print_word_count=len(ocr_print_text.split()),
        gt_print_text=gt_print_text,
        ocr_print_text=ocr_print_text,
    )


def write_score_result(score: ScoreResult, output_path: Path) -> None:
    """Append a score result to a JSONL file.

    Args:
        score: ScoreResult object to write.
        output_path: Path to the JSONL output file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "a", encoding="utf-8") as f:
        json.dump(asdict(score), f, ensure_ascii=False)
        f.write("\n")

    logger.info("Appended score for %s to %s", score.form_id, output_path)
