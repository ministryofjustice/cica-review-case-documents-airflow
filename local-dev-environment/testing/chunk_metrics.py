"""Chunk-level metrics for relevance scoring.

This module provides functions to calculate precision, recall, and other
chunk-level metrics when comparing search results against expected values.
"""

import pandas as pd


def calculate_chunk_match(row: pd.Series) -> pd.Series:
    """Calculate chunk match metrics including precision, recall, and missing chunks.

    Args:
        row: DataFrame row containing 'expected_chunk_id' and 'all_chunk_ids' columns.

    Returns:
        Series with chunk_match_percentage, precision, recall, and missing_chunk_ids.

    Scoring logic:
        - If expected chunks exist: calculate precision/recall normally
        - If no expected chunks but results found: precision=0 (all false positives), recall=None
        - If no expected chunks and no results: precision=1, recall=1 (correct rejection)
    """
    expected_chunk = str(row.get("expected_chunk_id", "")).strip()
    all_chunks = str(row.get("all_chunk_ids", ""))

    found_chunks = [c.strip() for c in all_chunks.split(",") if c.strip()]
    expected_chunks = [c.strip() for c in expected_chunk.split(",") if c.strip()]

    if expected_chunks:
        # True positives: expected chunks that were found
        true_positives = sum(1 for ec in expected_chunks if ec in found_chunks)

        # Recall: Of expected chunks, how many were found?
        recall = round(true_positives / len(expected_chunks) * 100, 2)

        # Precision: Of found chunks, how many were expected?
        precision = round(true_positives / len(found_chunks) * 100, 2) if found_chunks else 0.0

        chunk_match_percentage = recall  # Keep for backwards compatibility
        missing_chunks = [ec for ec in expected_chunks if ec not in found_chunks]
    else:
        # No expected chunks
        if found_chunks:
            # Results returned but none expected = all false positives
            precision = 0.0
            recall = None  # Recall is undefined when no expected chunks
            chunk_match_percentage = None
        else:
            # No expected and no results = correct rejection
            precision = 100.0
            recall = 100.0
            chunk_match_percentage = 100.0
        missing_chunks = []

    return pd.Series(
        {
            "chunk_match_percentage": chunk_match_percentage,
            "precision": precision,
            "recall": recall,
            "missing_chunk_ids": ", ".join(missing_chunks) if missing_chunks else "",
        }
    )


def safe_int(value: str | int | float, default: int = 0) -> int:
    """Safely convert a value to int, handling non-numeric values like '-'.

    Args:
        value: Value to convert.
        default: Default value if conversion fails.

    Returns:
        Integer value or default.
    """
    if pd.isna(value) or value == "" or value == "-":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
