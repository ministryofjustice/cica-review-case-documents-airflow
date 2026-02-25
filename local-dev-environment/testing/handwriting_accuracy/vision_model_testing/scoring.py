"""Vision model scoring module with WER/CER metrics.

Calculates accuracy metrics comparing vision model output to ground truth.
"""

import logging
from dataclasses import dataclass

from iam_testing.iam_filters import normalize_text
from iam_testing.scoring import calculate_wer_cer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisionScoreResult:
    """Vision model accuracy score for a single page."""

    page_id: str
    # Vision model info
    vision_model: str
    vision_prompt: str

    # Metrics
    wer: float  # Word Error Rate (0.0 = perfect, 1.0 = all wrong)
    cer: float  # Character Error Rate

    # Word counts
    gt_word_count: int
    vision_word_count: int

    # Text comparison
    gt_text: str
    vision_text: str

    # Token usage for cost tracking
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class VisionAugmentedScoreResult:
    """Score result comparing vision baseline vs LLM-augmented output."""

    page_id: str

    # Vision model info
    vision_model: str
    vision_prompt: str

    # LLM augmentation info
    llm_model: str
    llm_prompt: str

    # Baseline scores (vision only)
    baseline_wer: float
    baseline_cer: float

    # Augmented scores (after LLM correction)
    augmented_wer: float
    augmented_cer: float

    # Improvement (negative = LLM made it worse)
    wer_improvement: float  # baseline_wer - augmented_wer
    cer_improvement: float  # baseline_cer - augmented_cer

    # Text comparison
    gt_text: str
    vision_text: str
    augmented_text: str

    # Token usage
    vision_input_tokens: int
    vision_output_tokens: int
    llm_input_tokens: int
    llm_output_tokens: int


def score_vision_result(
    page_id: str,
    gt_text: str,
    vision_text: str,
    vision_model: str,
    vision_prompt: str,
    input_tokens: int,
    output_tokens: int,
) -> VisionScoreResult:
    """Score a single vision model result against ground truth.

    Args:
        page_id: Page identifier.
        gt_text: Ground truth text.
        vision_text: Text extracted by vision model.
        vision_model: Model name.
        vision_prompt: Prompt version hash.
        input_tokens: Input token count.
        output_tokens: Output token count.

    Returns:
        VisionScoreResult with metrics.
    """
    gt_normalized = normalize_text(gt_text)
    vision_normalized = normalize_text(vision_text)
    wer_score, cer_score = calculate_wer_cer(gt_normalized, vision_normalized)

    return VisionScoreResult(
        page_id=page_id,
        vision_model=vision_model,
        vision_prompt=vision_prompt,
        wer=wer_score,
        cer=cer_score,
        gt_word_count=len(gt_normalized.split()) if gt_normalized else 0,
        vision_word_count=len(vision_normalized.split()) if vision_normalized else 0,
        gt_text=gt_text,
        vision_text=vision_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def generate_vision_summary(scores: list[VisionScoreResult]) -> dict:
    """Generate summary statistics for a vision run.

    Args:
        scores: List of VisionScoreResult objects.

    Returns:
        Summary dict with aggregate metrics.
    """
    if not scores:
        return {"total_pages": 0, "avg_wer": 0.0, "avg_cer": 0.0}

    total_wer = sum(s.wer for s in scores)
    total_cer = sum(s.cer for s in scores)
    total_input_tokens = sum(s.input_tokens for s in scores)
    total_output_tokens = sum(s.output_tokens for s in scores)

    return {
        "total_pages": len(scores),
        "avg_wer": total_wer / len(scores),
        "avg_cer": total_cer / len(scores),
        "min_wer": min(s.wer for s in scores),
        "max_wer": max(s.wer for s in scores),
        "min_cer": min(s.cer for s in scores),
        "max_cer": max(s.cer for s in scores),
        "perfect_pages": sum(1 for s in scores if s.wer == 0.0),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "vision_model": scores[0].vision_model if scores else "",
        "vision_prompt": scores[0].vision_prompt if scores else "",
    }


def print_vision_summary(summary: dict) -> None:
    """Log formatted summary."""
    logger.info("=" * 60)
    logger.info("VISION MODEL EXTRACTION SUMMARY")
    logger.info("=" * 60)
    logger.info("Model: %s | Prompt: %s", summary.get("vision_model", "N/A"), summary.get("vision_prompt", "N/A"))
    logger.info("Total pages: %d | Perfect (WER=0): %d", summary["total_pages"], summary.get("perfect_pages", 0))
    logger.info("-" * 60)
    logger.info("Average WER: %.4f (%.2f%%)", summary["avg_wer"], summary["avg_wer"] * 100)
    logger.info("Average CER: %.4f (%.2f%%)", summary["avg_cer"], summary["avg_cer"] * 100)
    logger.info("WER range: %.4f - %.4f", summary.get("min_wer", 0), summary.get("max_wer", 0))
    logger.info("CER range: %.4f - %.4f", summary.get("min_cer", 0), summary.get("max_cer", 0))
    logger.info("-" * 60)
    logger.info(
        "Tokens: %d input, %d output", summary.get("total_input_tokens", 0), summary.get("total_output_tokens", 0)
    )
    logger.info("=" * 60)
