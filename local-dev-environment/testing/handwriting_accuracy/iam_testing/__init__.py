"""Textract accuracy testing module for handwriting OCR evaluation.

Subpackages:
    llm: LLM clients for OCR augmentation (Nova, Claude via Bedrock)
    runners: CLI entry points (single, batch, augment)

Modules:
    schemas: Data structures (OCRResult, WordBlock, ScoreResult)
    textract_client: AWS Textract API utilities
    iam_filters: IAM dataset-specific post-processing filters
    scoring: Ground truth loading and WER/CER scoring
    textract_ocr: Main OCR processing logic
    ground_truth_parser: Parse IAM XML files to JSONL

Usage:
    # Single form test
    python -m iam_testing.runners.single --form-id r06-121

    # Batch baseline (Textract only)
    python -m iam_testing.runners.batch --limit 10

    # LLM augmentation
    python -m iam_testing.runners.augment --baseline-run 20260126_140000
"""

from .iam_filters import filter_iam_header_footer, filter_iam_signature, normalize_text
from .llm import LLMResponse, get_llm_client
from .paths import DATA_DIR, PACKAGE_ROOT, TEXTRACT_ACCURACY_ROOT, get_repo_root
from .schemas import OCRResult, WordBlock
from .scoring import (
    ScoreResult,
    load_all_ground_truth,
    score_ocr_result,
    write_score_result,
)
from .textract_client import (
    analyze_image_sync,
    extract_word_blocks,
    get_textract_client,
)
from .textract_ocr import process_single_image, write_ocr_result

__all__ = [
    # Path constants
    "PACKAGE_ROOT",
    "TEXTRACT_ACCURACY_ROOT",
    "DATA_DIR",
    "get_repo_root",
    # Data structures
    "OCRResult",
    "WordBlock",
    "ScoreResult",
    "LLMResponse",
    # Textract
    "get_textract_client",
    "analyze_image_sync",
    "extract_word_blocks",
    "process_single_image",
    "write_ocr_result",
    # LLM
    "get_llm_client",
    # Filters
    "filter_iam_header_footer",
    "filter_iam_signature",
    "normalize_text",
    # Scoring
    "load_all_ground_truth",
    "score_ocr_result",
    "write_score_result",
]
