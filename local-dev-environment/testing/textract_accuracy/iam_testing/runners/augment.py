"""LLM-augmented OCR scoring runner.

Takes baseline Textract results and applies LLM correction to handwriting text,
then recalculates WER/CER to measure improvement.

Uses AWS Bedrock models for secure processing with no data retention.

Modes:
    - all: Augment all handwriting text
    - low_confidence: Only augment pages below confidence threshold

Usage:
    # IAM dataset
    python -m iam_testing.runners.augment --baseline-run 20260126_140000
    python -m iam_testing.runners.augment --baseline-run 20260126_140000 --mode low_confidence
    python -m iam_testing.runners.augment --baseline-run 20260126_140000 --model nova-pro

    # Custom documents
    python -m iam_testing.runners.augment --baseline-run 20260126_140000 --dataset custom
"""

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from jiwer import cer, wer

from .. import DATA_DIR
from ..iam_filters import normalize_text
from ..llm import LLMResponse, get_llm_client
from ..llm.prompt import PROMPTS
from ..summary_stats import (
    generate_augmented_summary,
    print_augmented_summary,
    save_summary,
)
from .utils import (
    append_jsonl,
    get_augmented_paths,
    get_baseline_paths,
    get_completed_ids,
    load_jsonl,
    load_jsonl_as_dict,
)

logger = logging.getLogger(__name__)

# Default prompt version for LLM-augmented OCR correction
DEFAULT_PROMPT_VERSION = "v2"


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


def print_summary(results_path: Path, summary_path: Path, run_id: str, baseline_run_id: str) -> None:
    """Generate, save, and print summary of augmented results.

    Args:
        results_path: Path to augmented results JSONL file.
        summary_path: Path to save summary JSON.
        run_id: Augmented run identifier.
        baseline_run_id: Baseline run identifier.
    """
    summary = generate_augmented_summary(results_path, run_id, baseline_run_id)
    if summary is None:
        return

    # Save summary JSON
    save_summary(summary, summary_path)

    # Print to console
    print_augmented_summary(summary)


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
            # Llama (typically auto-enabled)
            "llama-3-8b",
            "llama-3-70b",
            "llama-3-1-8b",
            "llama-3-1-70b",
            # Mistral (typically auto-enabled)
            "mistral-7b",
            "mixtral-8x7b",
            "mistral-large",
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
    parser.add_argument(
        "--prompt",
        choices=list(PROMPTS.keys()),
        default=None,
        help=f"Prompt version to use (default: {DEFAULT_PROMPT_VERSION})",
    )
    parser.add_argument(
        "--dataset",
        choices=["iam", "custom"],
        default="iam",
        help="Dataset type: 'iam' for IAM database or 'custom' for custom documents (default: iam)",
    )
    args = parser.parse_args()

    # Use default if not specified
    prompt_version = args.prompt or DEFAULT_PROMPT_VERSION

    # Paths - use centralized DATA_DIR
    data_dir = DATA_DIR
    if args.dataset == "custom":
        batch_runs_dir = data_dir / "custom_batch_runs"
    else:
        batch_runs_dir = data_dir / "batch_runs"

    # Get baseline paths from hierarchical structure
    baseline_paths = get_baseline_paths(batch_runs_dir, args.baseline_run)
    baseline_scores_path = baseline_paths["scores"]
    baseline_ocr_path = baseline_paths["ocr"]

    # Get augmented paths
    model_name = args.model
    augmented_run_id = f"{model_name}_{prompt_version}_{args.mode}"
    augmented_paths = get_augmented_paths(batch_runs_dir, args.baseline_run, model_name, prompt_version, args.mode)
    augmented_paths["dir"].mkdir(parents=True, exist_ok=True)
    output_path = augmented_paths["results"]
    summary_path = augmented_paths["summary"]

    if args.summary_only:
        print_summary(output_path, summary_path, augmented_run_id, args.baseline_run)
        return

    # Load baseline results
    baseline_results = load_jsonl(baseline_scores_path)
    if not baseline_results:
        logger.error("Baseline results not found: %s", baseline_scores_path)
        return

    # Load OCR results for confidence checking
    ocr_results = load_jsonl_as_dict(baseline_ocr_path)

    # Apply limit
    if args.limit:
        baseline_results = baseline_results[: args.limit]
        logger.info("Limited to %d forms", len(baseline_results))

    # Initialize LLM client with prompt version
    llm_client = get_llm_client(model=args.model, prompt_version=prompt_version)
    logger.info("Using LLM: %s with prompt: %s", llm_client.model_name, prompt_version)

    # Check for already processed forms
    processed_forms = get_completed_ids(output_path)

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
                    prompt_version=llm_client.get_prompt_hash(),
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
            append_jsonl(result, output_path)

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

    # Print and save summary
    print_summary(output_path, summary_path, augmented_run_id, args.baseline_run)


if __name__ == "__main__":
    main()
