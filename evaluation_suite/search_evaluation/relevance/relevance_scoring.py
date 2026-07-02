"""Relevance scoring for search results.

This module evaluates search results from the search looper by comparing
expected pages and chunk IDs against actual search results.
"""

import logging

import pandas as pd

from evaluation_suite.search_evaluation.opensearch.chunks_loader import load_all_chunks_from_opensearch
from evaluation_suite.search_evaluation.pipeline_config import (
    get_active_search_type,
    get_active_search_types,
)
from evaluation_suite.search_evaluation.relevance.chunk_metrics import K_VALUES, calculate_chunk_match, safe_int
from evaluation_suite.search_evaluation.relevance.evaluation_models import EvaluationSummary
from evaluation_suite.search_evaluation.relevance.ground_truth import classify_query, generate_expected_chunks
from evaluation_suite.search_evaluation.relevance.synonym_generator import generate_acceptable_terms
from evaluation_suite.search_evaluation.relevance.term_matching import (
    check_terms_by_expected_chunks,
    check_terms_in_chunks,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("relevance_scoring")


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

    # Auto-generate ground truth (expected chunks) and acceptable terms from the
    # currently-indexed corpus. This keeps both valid for whatever chunking
    # strategy built the index, rather than relying on hand annotations.
    df = _generate_ground_truth_and_terms(df, chunk_lookup)

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

    def count_terms(chunk_ids: list[str], row: pd.Series) -> dict[str, int]:
        """Count chunks containing the search term / any acceptable term."""
        if not chunk_ids:
            return {"chunks_with_search_term": 0, "chunks_with_any_term": 0}

        # Use chunk-based checking for semantic_only, text matching otherwise
        if match_method_label == "semantic_only":
            result = check_terms_by_expected_chunks(
                returned_chunk_ids=chunk_ids,
                search_term=str(row.get("search_term", "")),
                acceptable_terms=str(row.get("acceptable_terms", "")),
                term_to_expected_chunks=term_to_expected_chunks,
            )
        elif not chunk_lookup:
            return {"chunks_with_search_term": 0, "chunks_with_any_term": 0}
        else:
            result = check_terms_in_chunks(
                chunk_ids=chunk_ids,
                chunk_lookup=chunk_lookup,
                search_term=str(row.get("search_term", "")),
                acceptable_terms=str(row.get("acceptable_terms", "")),
                match_methods=match_methods,
            )
        return {
            "chunks_with_search_term": result["chunks_with_search_term"],
            "chunks_with_any_term": result["chunks_with_any_term"],
        }

    # Ranked term-presence precision: of the top-k returned chunks, what fraction
    # contain the search term (term_based) / any acceptable term (acceptable).
    def term_precision_at_k(row: pd.Series) -> pd.Series:
        chunk_ids = [c.strip() for c in str(row.get("all_chunk_ids", "")).split(",") if c.strip()]
        total = int(row.get("total_results", 0) or 0)
        out: dict[str, float | None] = {}
        for k in K_VALUES:
            denom = min(k, total)
            counts = count_terms(chunk_ids[:k], row)
            if denom > 0:
                out[f"term_based_precision_at_{k}"] = round(counts["chunks_with_search_term"] / denom * 100, 2)
                out[f"acceptable_term_based_precision_at_{k}"] = round(counts["chunks_with_any_term"] / denom * 100, 2)
            else:
                out[f"term_based_precision_at_{k}"] = None
                out[f"acceptable_term_based_precision_at_{k}"] = None
        return pd.Series(out)

    term_checks = df.apply(term_precision_at_k, axis=1)
    df = pd.concat([df, term_checks], axis=1)

    # Calculate summary statistics
    summary = _calculate_summary_stats(df)

    # Select and order output columns
    ranked_columns: list[str] = []
    for k in K_VALUES:
        ranked_columns.extend(
            [
                f"precision_at_{k}",
                f"recall_at_{k}",
            ]
        )

    output_columns = [
        "search_term",
        "query_type",
        "num_expected_chunks",
        "total_results",
        *ranked_columns,
        "missing_chunk_ids",
        "acceptable_terms",
        "manual_identifications",
        "total_term_frequency",
        "term_freq_difference",
    ]
    output_df = df[output_columns]

    return output_df, summary


def _generate_ground_truth_and_terms(df: pd.DataFrame, chunk_lookup: dict[str, str]) -> pd.DataFrame:
    """Populate expected_chunk_id, acceptable_terms and query_type per query.

    Ground truth is derived from ``chunk_lookup`` (the indexed corpus) and
    acceptable terms from the synonym generator. Existing non-empty values are
    preserved, so a caller may still supply hand-curated overrides.
    """
    if "expected_chunk_id" not in df.columns:
        df["expected_chunk_id"] = ""
    if "acceptable_terms" not in df.columns:
        df["acceptable_terms"] = ""

    query_types: list[str] = []
    expected_ids: list[str] = []
    acceptable: list[str] = []
    num_expected: list[int] = []

    for _, row in df.iterrows():
        query = str(row.get("search_term", "")).strip()
        qtype = classify_query(query) if query else "keyword_phrase"
        query_types.append(qtype)

        existing_expected = str(row.get("expected_chunk_id", "")).strip()
        if existing_expected:
            expected_list = [c.strip() for c in existing_expected.split(",") if c.strip()]
        else:
            expected_list = generate_expected_chunks(query, chunk_lookup, qtype) if query else []
        expected_ids.append(", ".join(expected_list))
        num_expected.append(len(expected_list))

        existing_acceptable = str(row.get("acceptable_terms", "")).strip()
        if existing_acceptable:
            acceptable.append(existing_acceptable)
        else:
            acceptable.append(generate_acceptable_terms(query) if query else "")

    df["query_type"] = query_types
    df["expected_chunk_id"] = expected_ids
    df["num_expected_chunks"] = num_expected
    df["acceptable_terms"] = acceptable
    return df


def _calculate_summary_stats(df: pd.DataFrame) -> EvaluationSummary:
    """Calculate ranked (@10/@20) summary statistics from the evaluated DataFrame.

    Args:
        df: DataFrame with per-query ranked metric columns.

    Returns:
        EvaluationSummary dataclass with aggregated @K metrics.
    """
    total_queries = len(df)
    queries_with_results = (df["total_results"] > 0).sum()
    result_rate = queries_with_results / total_queries if total_queries > 0 else 0

    def avg(column: str) -> float:
        values = df[column].dropna() if column in df.columns else pd.Series(dtype=float)
        return float(values.mean()) if len(values) > 0 else 0.0

    def f1(precision: float, recall: float) -> float:
        return 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    ranked: dict[str, float] = {}
    for k in K_VALUES:
        p = avg(f"precision_at_{k}")
        r = avg(f"recall_at_{k}")
        ranked[f"avg_precision_at_{k}"] = round(p, 2)
        ranked[f"avg_recall_at_{k}"] = round(r, 2)
        ranked[f"avg_f1_at_{k}"] = round(f1(p, r), 2)
        ranked[f"avg_term_based_precision_at_{k}"] = round(avg(f"term_based_precision_at_{k}"), 2)
        ranked[f"avg_acceptable_term_based_precision_at_{k}"] = round(avg(f"acceptable_term_based_precision_at_{k}"), 2)

    # Average chunks returned per query, counting only queries with some
    # acceptable-term signal in their top 10 (avoids noise inflating the count).
    signal_col = "acceptable_term_based_precision_at_10"
    df_with_signal = df[df[signal_col] > 0] if signal_col in df.columns else df.iloc[0:0]
    total_chunks_returned = df_with_signal["total_results"].sum()
    avg_chunks_returned = total_chunks_returned / total_queries if total_queries > 0 else 0

    queries_with_expected_chunk = df["expected_chunk_id"].apply(lambda x: bool(str(x).strip())).sum()

    # Optimization score driven by acceptable-term precision@10 (squared to
    # penalise low precision), scaled by chunks returned per query.
    precision_decimal = ranked["avg_acceptable_term_based_precision_at_10"] / 100
    optimization_score = (total_chunks_returned / total_queries) * (precision_decimal**2) if total_queries > 0 else 0

    return EvaluationSummary(
        total_queries=total_queries,
        queries_with_results=int(queries_with_results),
        result_rate=round(result_rate, 2),
        avg_chunks_returned=round(avg_chunks_returned, 2),
        queries_with_expected_chunk=int(queries_with_expected_chunk),
        avg_precision_at_10=ranked["avg_precision_at_10"],
        avg_precision_at_20=ranked["avg_precision_at_20"],
        avg_recall_at_10=ranked["avg_recall_at_10"],
        avg_recall_at_20=ranked["avg_recall_at_20"],
        avg_f1_at_10=ranked["avg_f1_at_10"],
        avg_f1_at_20=ranked["avg_f1_at_20"],
        avg_term_based_precision_at_10=ranked["avg_term_based_precision_at_10"],
        avg_term_based_precision_at_20=ranked["avg_term_based_precision_at_20"],
        avg_acceptable_term_based_precision_at_10=ranked["avg_acceptable_term_based_precision_at_10"],
        avg_acceptable_term_based_precision_at_20=ranked["avg_acceptable_term_based_precision_at_20"],
        optimization_score=round(optimization_score, 4),
    )
