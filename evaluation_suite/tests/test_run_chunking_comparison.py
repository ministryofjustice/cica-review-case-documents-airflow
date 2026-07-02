"""Unit tests for the automated chunking-strategy comparison runner."""

from unittest.mock import patch

from evaluation_suite.search_evaluation import run_chunking_comparison


@patch("evaluation_suite.search_evaluation.run_chunking_comparison.run_evaluation")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.reset_chunk_index")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.ingestion_settings")
def test_sweeps_each_strategy_resetting_index(mock_settings, mock_reset, mock_run):
    """Each strategy is applied, the index reset, and an evaluation run."""
    mock_settings.DOCUMENT_CHUNKING_STRATEGY = "original"
    mock_run.return_value = ("df", "summary")

    strategies = ["layout", "textractor-word-stream"]
    results = run_chunking_comparison.run_chunking_comparison(strategies)

    assert set(results) == set(strategies)
    assert mock_reset.call_count == len(strategies)
    assert mock_run.call_count == len(strategies)


@patch("evaluation_suite.search_evaluation.run_chunking_comparison.run_evaluation")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.reset_chunk_index")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.ingestion_settings")
def test_restores_original_strategy(mock_settings, mock_reset, mock_run):
    """The original ingestion strategy is restored after the sweep."""
    mock_settings.DOCUMENT_CHUNKING_STRATEGY = "original"

    run_chunking_comparison.run_chunking_comparison(["layout"])

    assert mock_settings.DOCUMENT_CHUNKING_STRATEGY == "original"


@patch("evaluation_suite.search_evaluation.run_chunking_comparison.run_evaluation")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.reset_chunk_index")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.ingestion_settings")
def test_restores_strategy_even_on_error(mock_settings, mock_reset, mock_run):
    """The original strategy is restored even if a run raises."""
    mock_settings.DOCUMENT_CHUNKING_STRATEGY = "original"
    mock_run.side_effect = RuntimeError("boom")

    try:
        run_chunking_comparison.run_chunking_comparison(["layout"])
    except RuntimeError:
        pass

    assert mock_settings.DOCUMENT_CHUNKING_STRATEGY == "original"


@patch("evaluation_suite.search_evaluation.run_chunking_comparison.run_evaluation")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.reset_chunk_index")
@patch("evaluation_suite.search_evaluation.run_chunking_comparison.ingestion_settings")
def test_defaults_to_all_strategies(mock_settings, mock_reset, mock_run):
    """With no argument the sweep uses the default strategy list."""
    mock_settings.DOCUMENT_CHUNKING_STRATEGY = "original"

    results = run_chunking_comparison.run_chunking_comparison()

    assert set(results) == set(run_chunking_comparison.DEFAULT_CHUNKING_STRATEGIES)
