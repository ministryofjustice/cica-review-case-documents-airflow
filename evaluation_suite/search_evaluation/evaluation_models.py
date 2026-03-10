"""Data models for evaluation results.

This module contains immutable dataclasses used across the evaluation framework.
"""

from dataclasses import dataclass


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
