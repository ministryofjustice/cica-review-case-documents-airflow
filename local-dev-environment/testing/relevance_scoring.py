"""Relevance scoring for search results.

This module evaluates search results from the search looper by comparing
expected pages and chunk IDs against actual search results.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from testing.chunk_metrics import calculate_chunk_match, safe_int
from testing.chunks_loader import load_all_chunks_from_opensearch
from testing.evaluation_config import (
    EVALUATION_LOG_FILE,
    get_active_search_type,
    get_active_search_types,
)
from testing.term_matching import check_terms_by_expected_chunks, check_terms_in_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("relevance_scoring")


@dataclass(frozen=True)
class EvaluationSummary:
    """Summary statistics from relevance evaluation.

    Immutable dataclass containing aggregated metrics across all search queries.
    """

    total_queries: int
    queries_with_results: int
    result_rate: float
    avg_chunks_returned: float
    queries_with_expected_chunk: int
    avg_precision: float
    avg_recall: float
    avg_f1_score: float
    avg_acceptable_term_based_precision: float
    optimization_score: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "total_queries": self.total_queries,
            "queries_with_results": self.queries_with_results,
            "result_rate": self.result_rate,
            "avg_chunks_returned": self.avg_chunks_returned,
            "queries_with_expected_chunk": self.queries_with_expected_chunk,
            "avg_precision": self.avg_precision,
            "avg_recall": self.avg_recall,
            "avg_f1_score": self.avg_f1_score,
            "avg_acceptable_term_based_precision": self.avg_acceptable_term_based_precision,
            "optimization_score": self.optimization_score,
        }


def load_chunk_lookup() -> dict[str, str]:
    """Load chunk texts from OpenSearch into a lookup dictionary.

    Returns:
        Dictionary mapping chunk_id to chunk_text.
    """
    return load_all_chunks_from_opensearch()


def evaluate_relevance(results_df: pd.DataFrame) -> tuple[pd.DataFrame, EvaluationSummary] | tuple[pd.DataFrame, dict]:
    """Evaluate relevance of search results against expected values.

    Args:
        results_df: DataFrame from run_search_loop with search results.

    Returns:
        Tuple of (evaluated DataFrame, EvaluationSummary).
        Returns (empty DataFrame, empty dict) if input is empty.
    """
    if results_df.empty:
        return pd.DataFrame(), {}

    # Load chunk lookup for term checking
    chunk_lookup = load_chunk_lookup()
    if not chunk_lookup:
        logger.warning("Chunk lookup is empty - term presence checking will be skipped")

    # Create a copy to avoid modifying the original
    df = results_df.copy()

    # Convert numeric columns safely
    df["manual_identifications"] = df["manual_identifications"].apply(safe_int)
    df["total_term_frequency"] = df["total_term_frequency"].apply(safe_int)
    df["total_results"] = df["total_results"].apply(safe_int)

    # Calculate term frequency difference
    df["term_freq_difference"] = df["total_term_frequency"] - df["manual_identifications"]

    # Calculate chunk match percentage and missing chunks
    chunk_metrics = df.apply(calculate_chunk_match, axis=1)
    df = pd.concat([df, chunk_metrics], axis=1)

    # Determine the term matching methods based on active search types
    match_methods = get_active_search_types()
    match_method_label = get_active_search_type()
    logger.info(f"Using search type: {match_method_label} (methods: {match_methods})")

    # Build term-to-expected-chunks lookup for semantic/hybrid checking
    term_to_expected_chunks: dict[str, set[str]] = {}
    for _, row in df.iterrows():
        term = str(row.get("search_term", "")).lower().strip()
        expected = str(row.get("expected_chunk_id", ""))
        chunk_ids = {c.strip() for c in expected.split(",") if c.strip()}
        if term and chunk_ids:
            term_to_expected_chunks[term] = chunk_ids

    # Check terms in returned chunks
    def check_terms_for_row(row: pd.Series) -> pd.Series:
        chunk_ids = [c.strip() for c in str(row.get("all_chunk_ids", "")).split(",") if c.strip()]
        if not chunk_ids:
            return pd.Series(
                {
                    "chunks_with_search_term": 0,
                    "chunks_with_acceptable": 0,
                    "chunks_with_any_term": 0,
                }
            )

        # Use chunk-based checking for semantic_only, text matching otherwise
        if match_method_label == "semantic_only":
            result = check_terms_by_expected_chunks(
                returned_chunk_ids=chunk_ids,
                search_term=str(row.get("search_term", "")),
                acceptable_terms=str(row.get("acceptable_terms", "")),
                term_to_expected_chunks=term_to_expected_chunks,
            )
        else:
            if not chunk_lookup:
                return pd.Series(
                    {
                        "chunks_with_search_term": 0,
                        "chunks_with_acceptable": 0,
                        "chunks_with_any_term": 0,
                    }
                )
            result = check_terms_in_chunks(
                chunk_ids=chunk_ids,
                chunk_lookup=chunk_lookup,
                search_term=str(row.get("search_term", "")),
                acceptable_terms=str(row.get("acceptable_terms", "")),
                match_methods=match_methods,
            )
        return pd.Series(
            {
                "chunks_with_search_term": result["chunks_with_search_term"],
                "chunks_with_acceptable": result["chunks_with_acceptable"],
                "chunks_with_any_term": result["chunks_with_any_term"],
            }
        )

    term_checks = df.apply(check_terms_for_row, axis=1)
    df = pd.concat([df, term_checks], axis=1)

    # Calculate percentage of returned chunks containing terms
    df["term_based_precision"] = df.apply(
        lambda row: round(row["chunks_with_search_term"] / row["total_results"] * 100, 2)
        if row["total_results"] > 0
        else None,
        axis=1,
    )
    df["acceptable_term_based_precision"] = df.apply(
        lambda row: round(row["chunks_with_any_term"] / row["total_results"] * 100, 2)
        if row["total_results"] > 0
        else None,
        axis=1,
    )

    # Calculate summary statistics
    summary = _calculate_summary_stats(df)

    # Select and order output columns
    output_columns = [
        "search_term",
        "expected_chunk_id",
        "total_results",
        "precision",
        "recall",
        "missing_chunk_ids",
        "term_based_precision",
        "acceptable_term_based_precision",
        "manual_identifications",
        "total_term_frequency",
        "term_freq_difference",
    ]
    output_df = df[output_columns]

    return output_df, summary


def _calculate_summary_stats(df: pd.DataFrame) -> EvaluationSummary:
    """Calculate summary statistics from evaluated DataFrame.

    Args:
        df: DataFrame with evaluation columns.

    Returns:
        EvaluationSummary dataclass with aggregated metrics.
    """
    total_queries = len(df)
    queries_with_results = (df["total_results"] > 0).sum()
    result_rate = queries_with_results / total_queries if total_queries > 0 else 0

    # Calculate average precision and recall
    precision_values = df["precision"].dropna()
    recall_values = df["recall"].dropna()
    avg_precision = precision_values.mean() if len(precision_values) > 0 else 0
    avg_recall = recall_values.mean() if len(recall_values) > 0 else 0

    # Calculate F1 score (harmonic mean of precision and recall)
    if avg_precision + avg_recall > 0:
        avg_f1_score = 2 * (avg_precision * avg_recall) / (avg_precision + avg_recall)
    else:
        avg_f1_score = 0

    # Calculate average chunks returned per query (only count results from searches with precision > 0)
    # This prevents 0-precision searches from inflating the chunk count with noise
    df_with_precision = df[df["acceptable_term_based_precision"] > 0]
    total_chunks_returned = df_with_precision["total_results"].sum()
    avg_chunks_returned = total_chunks_returned / total_queries if total_queries > 0 else 0

    queries_with_expected_chunk = df["expected_chunk_id"].apply(lambda x: bool(str(x).strip())).sum()

    # Calculate average percentage for acceptable term presence
    acceptable_precision_values = df["acceptable_term_based_precision"].dropna()
    avg_acceptable_term_based_precision = (
        acceptable_precision_values.mean() if len(acceptable_precision_values) > 0 else 0
    )

    # Calculate optimization score: (total_chunks / total_queries) * (avg_acceptable_term_precision ^ 2)
    # Squaring precision heavily penalizes low precision results
    # Dividing by total_queries normalizes across different search term sets
    # Convert percentage to decimal (0-1) for the calculation
    precision_decimal = avg_acceptable_term_based_precision / 100
    if total_queries > 0:
        optimization_score = (total_chunks_returned / total_queries) * ((precision_decimal) ** 2)
    else:
        optimization_score = 0

    return EvaluationSummary(
        total_queries=total_queries,
        queries_with_results=int(queries_with_results),
        result_rate=round(result_rate, 2),
        avg_chunks_returned=round(avg_chunks_returned, 2),
        queries_with_expected_chunk=int(queries_with_expected_chunk),
        avg_precision=round(avg_precision, 2),
        avg_recall=round(avg_recall, 2),
        avg_f1_score=round(avg_f1_score, 2),
        avg_acceptable_term_based_precision=round(avg_acceptable_term_based_precision, 2),
        optimization_score=round(optimization_score, 4),
    )


def write_results_csv(
    df: pd.DataFrame,
    output_file: Path,
    config: dict,
    summary: EvaluationSummary | dict,
) -> None:
    """Write evaluation results DataFrame to a CSV file with config header.

    Args:
        df: DataFrame with evaluation results.
        output_file: Path to write the CSV file.
        config: Search configuration dictionary to write at top of file.
        summary: EvaluationSummary or dict with summary statistics.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Convert EvaluationSummary to dict if needed
    summary_dict = summary.to_dict() if isinstance(summary, EvaluationSummary) else summary

    with open(output_file, "w", encoding="utf-8") as f:
        # Write config section as row (keys then values)
        config_keys = ",".join(str(key) for key in config.keys())
        config_values = ",".join(str(value) for value in config.values())
        f.write("Search Configuration\n")
        f.write(f"{config_keys}\n")
        f.write(f"{config_values}\n")
        f.write("\n")

        # Write summary section as row (keys then values)
        summary_keys = ",".join(str(key) for key in summary_dict.keys())
        summary_values = ",".join(str(value) for value in summary_dict.values())
        f.write("Summary Statistics\n")
        f.write(f"{summary_keys}\n")
        f.write(f"{summary_values}\n")
        f.write("\n")

        # Write the DataFrame
        df.to_csv(f, index=False)

    logger.info(f"Results CSV written to {output_file.resolve()}")


def append_to_evaluation_log(config: dict, summary: EvaluationSummary | dict) -> None:
    """Append evaluation summary to the cumulative log file.

    Creates the log file with headers if it doesn't exist.

    Args:
        config: Search configuration dictionary.
        summary: EvaluationSummary or dict with summary statistics.
    """
    EVALUATION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Convert EvaluationSummary to dict if needed
    summary_dict = summary.to_dict() if isinstance(summary, EvaluationSummary) else summary

    # Combine config and summary into a single row
    log_entry = {**config, **summary_dict}

    # Remove columns we don't want in the log
    for key in ["fuzziness", "max_expansions", "queries_with_expected_chunk"]:
        log_entry.pop(key, None)

    # Reorder to put timestamp first, then search_type
    reordered = {}
    if "timestamp" in log_entry:
        reordered["timestamp"] = log_entry.pop("timestamp")
    if "search_type" in log_entry:
        reordered["search_type"] = log_entry.pop("search_type")
    log_entry = {**reordered, **log_entry}

    # Check if file exists to determine if we need headers
    write_header = not EVALUATION_LOG_FILE.exists()

    # Convert to DataFrame for easy CSV append
    log_df = pd.DataFrame([log_entry])

    with open(EVALUATION_LOG_FILE, "a", encoding="utf-8") as f:
        log_df.to_csv(f, header=write_header, index=False)

    logger.info(f"Appended evaluation summary to {EVALUATION_LOG_FILE.resolve()}")
