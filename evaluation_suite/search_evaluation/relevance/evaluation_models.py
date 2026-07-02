"""Data models for evaluation results.

This module contains immutable dataclasses used across the evaluation framework.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationSummary:
    """Summary statistics from relevance evaluation.

    Immutable dataclass containing aggregated ranked (@10 / @20) metrics across
    all search queries.
    """

    total_queries: int
    queries_with_results: int
    result_rate: float
    avg_chunks_returned: float
    queries_with_expected_chunk: int
    avg_precision_at_10: float
    avg_precision_at_20: float
    avg_recall_at_10: float
    avg_recall_at_20: float
    avg_f1_at_10: float
    avg_f1_at_20: float
    avg_term_based_precision_at_10: float
    avg_term_based_precision_at_20: float
    avg_acceptable_term_based_precision_at_10: float
    avg_acceptable_term_based_precision_at_20: float
    optimization_score: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "total_queries": self.total_queries,
            "queries_with_results": self.queries_with_results,
            "avg_chunks_returned": self.avg_chunks_returned,
            "queries_with_expected_chunk": self.queries_with_expected_chunk,
            "avg_precision_at_10": self.avg_precision_at_10,
            "avg_precision_at_20": self.avg_precision_at_20,
            "avg_recall_at_10": self.avg_recall_at_10,
            "avg_recall_at_20": self.avg_recall_at_20,
            "avg_f1_at_10": self.avg_f1_at_10,
            "avg_f1_at_20": self.avg_f1_at_20,
            "optimization_score": self.optimization_score,
        }
