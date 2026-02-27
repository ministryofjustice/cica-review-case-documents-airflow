"""Unit tests for relevance_scoring.py."""

from unittest.mock import patch

import pandas as pd

from evaluation_suite.search_evaluation import relevance_scoring


def test_evaluation_summary_to_dict():
    """Test EvaluationSummary.to_dict returns correct dictionary."""
    summary = relevance_scoring.EvaluationSummary(
        total_queries=10,
        queries_with_results=8,
        result_rate=0.8,
        avg_chunks_returned=2.5,
        queries_with_expected_chunk=7,
        avg_precision=0.7,
        avg_recall=0.6,
        avg_f1_score=0.65,
        avg_acceptable_term_based_precision=0.75,
        optimization_score=0.1234,
    )
    d = summary.to_dict()
    assert d["total_queries"] == 10
    assert d["optimization_score"] == 0.1234
    assert "avg_f1_score" in d


@patch("evaluation_suite.search_evaluation.relevance_scoring.load_all_chunks_from_opensearch")
def test_load_chunk_lookup_returns_dict(mock_load):
    """Test load_chunk_lookup returns a dict from loader."""
    mock_load.return_value = {"chunk1": "text1", "chunk2": "text2"}
    lookup = relevance_scoring.load_chunk_lookup()
    assert lookup == {"chunk1": "text1", "chunk2": "text2"}


@patch("evaluation_suite.search_evaluation.relevance_scoring.load_chunk_lookup")
@patch("evaluation_suite.search_evaluation.relevance_scoring.get_active_search_types")
@patch("evaluation_suite.search_evaluation.relevance_scoring.get_active_search_type")
@patch("evaluation_suite.search_evaluation.relevance_scoring.check_terms_in_chunks")
@patch("evaluation_suite.search_evaluation.chunk_metrics.calculate_chunk_match")
def test_evaluate_relevance_returns_summary(
    mock_calculate_chunk_match,
    mock_check_terms_in_chunks,
    mock_get_active_search_type,
    mock_get_active_search_types,
    mock_load_chunk_lookup,
):
    """Test evaluate_relevance returns DataFrame and summary."""
    mock_load_chunk_lookup.return_value = {"c1": "text"}
    mock_get_active_search_types.return_value = ["exact"]
    mock_get_active_search_type.return_value = "text"
    mock_check_terms_in_chunks.return_value = {
        "chunks_with_search_term": 1,
        "chunks_with_acceptable": 1,
        "chunks_with_any_term": 1,
    }
    mock_calculate_chunk_match.return_value = pd.Series({"precision": 1.0, "recall": 1.0, "missing_chunk_ids": ""})

    df = pd.DataFrame(
        {
            "search_term": ["test"],
            "expected_chunk_id": ["c1"],
            "all_chunk_ids": [["c1"]],
            "manual_identifications": [1],
            "total_term_frequency": [1],
            "total_results": [1],
            "acceptable_terms": ["test"],
        }
    )
    output_df, summary = relevance_scoring.evaluate_relevance(df)
    assert isinstance(output_df, pd.DataFrame)
    assert isinstance(summary, relevance_scoring.EvaluationSummary)
    assert summary.total_queries == 1
    assert output_df.shape[0] == 1
    assert "precision" in output_df.columns


def test_evaluate_relevance_empty_df():
    """Test evaluate_relevance returns empty for empty DataFrame."""
    df = pd.DataFrame()
    output_df, summary = relevance_scoring.evaluate_relevance(df)
    assert output_df.empty
    assert summary == {}


def test_calculate_summary_stats_basic():
    """Test _calculate_summary_stats returns correct EvaluationSummary."""
    df = pd.DataFrame(
        {
            "precision": [1.0, 0.5],
            "recall": [0.8, 0.2],
            "acceptable_term_based_precision": [100, 50],
            "total_results": [2, 2],
            "expected_chunk_id": ["c1", ""],
        }
    )
    summary = relevance_scoring._calculate_summary_stats(df)
    assert isinstance(summary, relevance_scoring.EvaluationSummary)
    assert summary.total_queries == 2
    assert summary.avg_precision == 0.75
    assert summary.avg_recall == 0.5
    assert summary.avg_f1_score > 0


def test_write_results_csv(tmp_path):
    """Test write_results_csv writes CSV file with config and summary."""
    df = pd.DataFrame(
        {
            "search_term": ["a"],
            "expected_chunk_id": ["c1"],
            "total_results": [1],
            "precision": [1.0],
            "recall": [1.0],
            "missing_chunk_ids": [""],
            "term_based_precision": [100],
            "acceptable_term_based_precision": [100],
            "manual_identifications": [1],
            "total_term_frequency": [1],
            "term_freq_difference": [0],
        }
    )
    output_file = tmp_path / "results.csv"
    config = {"search_type": "exact"}
    summary = relevance_scoring.EvaluationSummary(
        total_queries=1,
        queries_with_results=1,
        result_rate=1.0,
        avg_chunks_returned=1.0,
        queries_with_expected_chunk=1,
        avg_precision=1.0,
        avg_recall=1.0,
        avg_f1_score=1.0,
        avg_acceptable_term_based_precision=100.0,
        optimization_score=1.0,
    )
    relevance_scoring.write_results_csv(df, output_file, config, summary)
    assert output_file.exists()
    content = output_file.read_text()
    assert "Search Configuration" in content
    assert "Summary Statistics" in content
    assert "search_term" in content


@patch("evaluation_suite.search_evaluation.relevance_scoring.EVALUATION_LOG_FILE")
def test_append_to_evaluation_log_creates_file(mock_log_file, tmp_path):
    """Test append_to_evaluation_log creates log file and writes entry."""
    log_path = tmp_path / "log.csv"
    mock_log_file.__str__.return_value = str(log_path)
    mock_log_file.parent = log_path.parent
    mock_log_file.exists.return_value = False
    # Patch EVALUATION_LOG_FILE with a real Path object for file operations
    with patch("evaluation_suite.search_evaluation.relevance_scoring.EVALUATION_LOG_FILE", log_path):
        config = {"search_type": "exact", "timestamp": "2026-02-27"}
        summary = relevance_scoring.EvaluationSummary(
            total_queries=1,
            queries_with_results=1,
            result_rate=1.0,
            avg_chunks_returned=1.0,
            queries_with_expected_chunk=1,
            avg_precision=1.0,
            avg_recall=1.0,
            avg_f1_score=1.0,
            avg_acceptable_term_based_precision=100.0,
            optimization_score=1.0,
        )
        relevance_scoring.append_to_evaluation_log(config, summary)
        assert log_path.exists()
        content = log_path.read_text()
        assert "search_type" in content
        assert "total_queries" in content
