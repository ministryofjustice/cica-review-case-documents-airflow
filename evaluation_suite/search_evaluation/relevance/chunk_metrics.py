"""Chunk-level metrics for relevance scoring.

This module provides functions to calculate ranked precision@K and recall@K
per query, comparing search results against the (auto-generated) expected
chunks. Results are evaluated at fixed rank cutoffs rather than over the whole
returned set.
"""

import pandas as pd

# Rank cutoffs at which precision/recall are reported.
K_VALUES: tuple[int, ...] = (10, 20)


def _precision_recall_at_k(
    found_chunks: list[str],
    expected_chunks: list[str],
    k: int,
) -> tuple[float, float | None]:
    """Compute precision@k and recall@k for one query.

    ``found_chunks`` must be ordered by descending search rank.

    Returns:
        (precision, recall) as percentages. Mirrors the no-expected-chunks
        conventions used across the suite:
          - expected present: normal precision/recall over the top-k slice.
          - no expected, results returned: precision 0, recall None.
          - no expected, no results: precision 100, recall 100 (correct rejection).
    """
    top_k = found_chunks[:k]

    if expected_chunks:
        true_positives = sum(1 for ec in expected_chunks if ec in top_k)
        precision = round(true_positives / len(top_k) * 100, 2) if top_k else 0.0
        recall = round(true_positives / len(expected_chunks) * 100, 2)
        return precision, recall

    # No expected chunks.
    if top_k:
        return 0.0, None
    return 100.0, 100.0


def calculate_chunk_match(row: pd.Series) -> pd.Series:
    """Calculate ranked precision@K / recall@K and missing chunks for a row.

    Args:
        row: DataFrame row containing 'expected_chunk_id' and 'all_chunk_ids'.
            'all_chunk_ids' is a comma-separated list in descending rank order.

    Returns:
        Series with precision_at_{k}, recall_at_{k} for each k in K_VALUES,
        plus missing_chunk_ids (expected chunks not retrieved at all).
    """
    expected_chunk = str(row.get("expected_chunk_id", "")).strip()
    all_chunks = str(row.get("all_chunk_ids", ""))

    found_chunks = [c.strip() for c in all_chunks.split(",") if c.strip()]
    expected_chunks = [c.strip() for c in expected_chunk.split(",") if c.strip()]

    metrics: dict[str, float | None] = {}
    for k in K_VALUES:
        precision, recall = _precision_recall_at_k(found_chunks, expected_chunks, k)
        metrics[f"precision_at_{k}"] = precision
        metrics[f"recall_at_{k}"] = recall

    # Missing chunks: expected chunks that were not retrieved anywhere in the
    # returned set (independent of the rank cutoff).
    missing_chunks = [ec for ec in expected_chunks if ec not in found_chunks]
    metrics["missing_chunk_ids"] = ", ".join(missing_chunks) if missing_chunks else ""

    return pd.Series(metrics)


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
