"""Data schemas for IAM Textract OCR testing.

This module defines the data structures used throughout the OCR testing pipeline.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OCRResult:
    """OCR result for a single form.

    Attributes:
        form_id: Unique identifier for the form.
        ocr_print_text: Extracted printed text (after filtering).
        ocr_print_text_raw: Raw printed text before filtering.
        ocr_handwriting_text: Extracted handwritten text.
        ocr_print_word_count: Number of printed words (after filtering).
        ocr_handwriting_word_count: Number of handwritten words.
        avg_print_confidence: Average confidence for printed words (0-100).
        avg_handwriting_confidence: Average confidence for handwritten words (0-100).
        textract_job_id: Textract job ID (None for sync API).
        processed_at: ISO timestamp of processing.
    """

    form_id: str
    ocr_print_text: str
    ocr_print_text_raw: str
    ocr_handwriting_text: str
    ocr_print_word_count: int
    ocr_handwriting_word_count: int
    avg_print_confidence: float
    avg_handwriting_confidence: float
    textract_job_id: str | None
    processed_at: str


@dataclass(frozen=True, slots=True)
class WordBlock:
    """Represents a single word from Textract response.

    Attributes:
        text: The recognized text.
        text_type: "PRINTED" or "HANDWRITING".
        confidence: Confidence score (0-100).
        bbox_top: Top position of bounding box (0-1, relative to page).
        bbox_left: Left position of bounding box (0-1, relative to page).
    """

    text: str
    text_type: str
    confidence: float
    bbox_top: float
    bbox_left: float
