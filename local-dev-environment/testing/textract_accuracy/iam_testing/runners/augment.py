"""LLM-augmented OCR scoring runner.

Takes baseline Textract results and applies LLM correction to handwriting text,
then recalculates WER/CER to measure improvement.

Uses AWS Bedrock models for secure processing with no data retention.

Modes:
    - all: Augment all handwriting text
    - low_confidence: Only augment pages below confidence threshold

Usage:
    python -m iam_testing.runners.augment --baseline-run 20260126_140000
    python -m iam_testing.runners.augment --baseline-run 20260126_140000 --mode low_confidence
    python -m iam_testing.runners.augment --baseline-run 20260126_140000 --model nova-pro
"""

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from jiwer import cer, wer

from ..iam_filters import normalize_text
from ..llm import LLMResponse, get_llm_client
from ..llm.prompt import get_prompt_hash

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AugmentedScoreResult:
    """Score result comparing baseline vs LLM-augmented OCR."""

    form_id: str
    # LLM info
    llm_model: str
    prompt_version: str  # Hash of prompt used for reproducibility
    augmentation_mode: str  # 'all' or 'low_confidence'
    was_augmented: bool  # False if skipped due to mode/threshold

    # Baseline scores (from Textract only)
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
    baseline_ocr_text: str
    augmented_ocr_text: str

    # Diff showing exact changes made
    diff_summary: str  # Human-readable list of changes

    # Token usage for cost tracking
    input_tokens: int
    output_tokens: int


def load_baseline_results(results_path: Path) -> list[dict]:
    """Load baseline score results from JSONL file.

    Args:
        results_path: Path to the score_results JSONL file.

    Returns:
        List of score result dicts.
    """
    if not results_path.exists():
        logger.error("Baseline results not found: %s", results_path)
        return []

    results = []
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))

    logger.info("Loaded %d baseline results", len(results))
    return results


def should_augment(
    baseline: dict,
    mode: Literal["all", "low_confidence"],
    confidence_threshold: float,
    ocr_results: dict[str, dict],
) -> bool:
    """Determine if a form should be augmented based on mode.

    Args:
        baseline: Baseline score result dict.
        mode: Augmentation mode ('all' or 'low_confidence').
        confidence_threshold: Confidence threshold for low_confidence mode.
        ocr_results: Dict mapping form_id to OCR result.

    Returns:
        True if form should be augmented.
    """
    if mode == "all":
        return True

    # low_confidence mode: check confidence from OCR results
    form_id = baseline["form_id"]
    ocr = ocr_results.get(form_id)
    if not ocr:
        logger.warning("OCR result not found for %s, skipping", form_id)
        return False

    confidence = ocr.get("avg_handwriting_confidence", 100.0)
    return confidence < confidence_threshold


def load_ocr_results(ocr_path: Path) -> dict[str, dict]:
    """Load OCR results into a dict keyed by form_id.

    Args:
        ocr_path: Path to the ocr_results JSONL file.

    Returns:
        Dict mapping form_id to OCR result.
    """
    if not ocr_path.exists():
        return {}

    results = {}
    with open(ocr_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            results[record["form_id"]] = record

    return results


def augment_and_score(
    baseline: dict,
    llm_response: LLMResponse,
    model: str,
    mode: str,
    was_augmented: bool,
) -> AugmentedScoreResult:
    """Calculate augmented scores and create result.

    Args:
        baseline: Baseline score result dict.
        llm_response: LLM response with corrected text.
        model: LLM model name.
        mode: Augmentation mode used.
        was_augmented: Whether augmentation was actually applied.

    Returns:
        AugmentedScoreResult with comparison data.
    """
    gt_text = baseline["gt_handwriting_text"]
    baseline_ocr = baseline["ocr_handwriting_text"]
    augmented_ocr = normalize_text(llm_response.corrected_text) if was_augmented else baseline_ocr

    # Calculate augmented WER/CER
    if gt_text.strip() and augmented_ocr.strip():
        augmented_wer = wer(gt_text, augmented_ocr)
        augmented_cer = cer(gt_text, augmented_ocr)
    elif not gt_text.strip() and not augmented_ocr.strip():
        augmented_wer = 0.0
        augmented_cer = 0.0
    else:
        augmented_wer = 1.0
        augmented_cer = 1.0

    baseline_wer = baseline["wer_handwriting"]
    baseline_cer = baseline["cer_handwriting"]

    return AugmentedScoreResult(
        form_id=baseline["form_id"],
        llm_model=model,
        prompt_version=llm_response.prompt_version,
        augmentation_mode=mode,
        was_augmented=was_augmented,
        baseline_wer=baseline_wer,
        baseline_cer=baseline_cer,
        augmented_wer=round(augmented_wer, 4),
        augmented_cer=round(augmented_cer, 4),
        wer_improvement=round(baseline_wer - augmented_wer, 4),
        cer_improvement=round(baseline_cer - augmented_cer, 4),
        gt_text=gt_text,
        baseline_ocr_text=baseline_ocr,
        augmented_ocr_text=augmented_ocr,
        diff_summary=llm_response.diff_summary,
        input_tokens=llm_response.input_tokens,
        output_tokens=llm_response.output_tokens,
    )


def write_augmented_result(result: AugmentedScoreResult, output_path: Path) -> None:
    """Append augmented result to JSONL file.

    Args:
        result: AugmentedScoreResult to write.
        output_path: Path to output JSONL file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "a", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False)
        f.write("\n")


def print_summary(results_path: Path) -> None:
    """Print summary of augmented results.

    Args:
        results_path: Path to augmented results JSONL file.
    """
    if not results_path.exists():
        logger.warning("No augmented results found")
        return

    results = []
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))

    if not results:
        return

    augmented = [r for r in results if r["was_augmented"]]
    total_input_tokens = sum(r["input_tokens"] for r in results)
    total_output_tokens = sum(r["output_tokens"] for r in results)

    # Calculate means
    mean_baseline_wer = sum(r["baseline_wer"] for r in results) / len(results)
    mean_augmented_wer = sum(r["augmented_wer"] for r in results) / len(results)
    mean_wer_improvement = sum(r["wer_improvement"] for r in results) / len(results)

    mean_baseline_cer = sum(r["baseline_cer"] for r in results) / len(results)
    mean_augmented_cer = sum(r["augmented_cer"] for r in results) / len(results)
    mean_cer_improvement = sum(r["cer_improvement"] for r in results) / len(results)

    # Count improvements
    improved_wer = len([r for r in augmented if r["wer_improvement"] > 0])
    worse_wer = len([r for r in augmented if r["wer_improvement"] < 0])
    unchanged_wer = len([r for r in augmented if r["wer_improvement"] == 0])

    logger.info("=" * 70)
    logger.info("LLM AUGMENTATION SUMMARY")
    logger.info("=" * 70)
    logger.info(
        "Model: %s | Prompt: %s | Mode: %s",
        results[0]["llm_model"],
        results[0]["prompt_version"],
        results[0]["augmentation_mode"],
    )
    logger.info(
        "Total forms: %d | Augmented: %d | Skipped: %d", len(results), len(augmented), len(results) - len(augmented)
    )
    logger.info("-" * 70)
    logger.info("WER (Word Error Rate):")
    logger.info("  Baseline Mean:  %.2f%%", mean_baseline_wer * 100)
    logger.info("  Augmented Mean: %.2f%%", mean_augmented_wer * 100)
    logger.info("  Improvement:    %.2f%% (positive = better)", mean_wer_improvement * 100)
    logger.info("  Improved: %d | Worse: %d | Unchanged: %d", improved_wer, worse_wer, unchanged_wer)
    logger.info("-" * 70)
    logger.info("CER (Character Error Rate):")
    logger.info("  Baseline Mean:  %.2f%%", mean_baseline_cer * 100)
    logger.info("  Augmented Mean: %.2f%%", mean_augmented_cer * 100)
    logger.info("  Improvement:    %.2f%% (positive = better)", mean_cer_improvement * 100)
    logger.info("-" * 70)
    logger.info("Token Usage:")
    logger.info("  Input:  %d tokens", total_input_tokens)
    logger.info("  Output: %d tokens", total_output_tokens)
    logger.info("=" * 70)


def main() -> None:
    """Run LLM augmentation on baseline Textract results."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="LLM-augmented OCR scoring")
    parser.add_argument(
        "--baseline-run",
        required=True,
        help="Run ID of baseline batch to augment (e.g., 20260126_140000)",
    )
    parser.add_argument(
        "--model",
        default="nova-lite",
        choices=[
            # Nova (auto-enabled, no subscription needed)
            "nova-micro",
            "nova-lite",
            "nova-pro",
            # Claude (requires Bedrock model access)
            "claude-3-haiku",
            "claude-3-5-haiku",
            "claude-3-sonnet",
            "claude-3-5-sonnet",
        ],
        help="Bedrock model (default: nova-lite)",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "low_confidence"],
        default="all",
        help="Augmentation mode (default: all)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=80.0,
        help="Confidence threshold for low_confidence mode (default: 80.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of forms to process",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print summary of existing augmented results",
    )
    args = parser.parse_args()

    # Paths
    data_dir = Path(__file__).parent.parent.parent / "data"
    batch_dir = data_dir / "batch_runs"

    baseline_scores_path = batch_dir / f"score_results_{args.baseline_run}.jsonl"
    baseline_ocr_path = batch_dir / f"ocr_results_{args.baseline_run}.jsonl"

    # Generate augmented run ID
    model_name = args.model
    augmented_run_id = f"{args.baseline_run}_augmented_{model_name}_{args.mode}"
    output_path = batch_dir / f"augmented_results_{augmented_run_id}.jsonl"

    if args.summary_only:
        print_summary(output_path)
        return

    # Load baseline results
    baseline_results = load_baseline_results(baseline_scores_path)
    if not baseline_results:
        return

    # Load OCR results for confidence checking
    ocr_results = load_ocr_results(baseline_ocr_path)

    # Apply limit
    if args.limit:
        baseline_results = baseline_results[: args.limit]
        logger.info("Limited to %d forms", len(baseline_results))

    # Initialize LLM client
    llm_client = get_llm_client(model=args.model)
    logger.info("Using LLM: %s", llm_client.model_name)

    # Check for already processed forms
    processed_forms: set[str] = set()
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                processed_forms.add(record["form_id"])
        logger.info("Found %d already processed forms", len(processed_forms))

    # Process forms
    for i, baseline in enumerate(baseline_results, 1):
        form_id = baseline["form_id"]

        if form_id in processed_forms:
            continue

        # Check if should augment
        should = should_augment(baseline, args.mode, args.confidence_threshold, ocr_results)

        logger.info("[%d/%d] Processing: %s (augment: %s)", i, len(baseline_results), form_id, should)

        try:
            if should:
                # Get LLM correction
                ocr_text = baseline["ocr_handwriting_text"]
                llm_response = llm_client.correct_ocr_text(ocr_text)
            else:
                # Create empty response for skipped forms
                llm_response = LLMResponse(
                    original_text=baseline["ocr_handwriting_text"],
                    corrected_text=baseline["ocr_handwriting_text"],
                    model=llm_client.model_name,
                    prompt_version=get_prompt_hash(),
                    input_tokens=0,
                    output_tokens=0,
                    diff_summary="(skipped)",
                )

            # Score and write result
            result = augment_and_score(
                baseline=baseline,
                llm_response=llm_response,
                model=llm_client.model_name,
                mode=args.mode,
                was_augmented=should,
            )
            write_augmented_result(result, output_path)

            if should:
                logger.info(
                    "[%d/%d] %s: WER %.2f%% -> %.2f%% (Δ%.2f%%)",
                    i,
                    len(baseline_results),
                    form_id,
                    result.baseline_wer * 100,
                    result.augmented_wer * 100,
                    result.wer_improvement * 100,
                )
                if result.diff_summary != "(no changes)":
                    logger.info("    Changes: %s", result.diff_summary[:100])

        except Exception:
            logger.exception("[%d/%d] Failed: %s", i, len(baseline_results), form_id)

    # Print summary
    print_summary(output_path)


if __name__ == "__main__":
    main()
