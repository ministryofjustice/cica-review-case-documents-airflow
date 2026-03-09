"""Unit tests for evaluation_config.py."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from evaluation_suite.search_evaluation import evaluation_config


def test_get_timestamp_format():
    """Test that get_timestamp returns a string in the expected format."""
    ts = evaluation_config.get_timestamp()
    # Should match YYYY-MM-DD_HH-MM-SS
    assert ts.count("-") == 4 and ts.count("_") == 1


def test_get_date_folder_returns_today():
    """Test that get_date_folder returns a Path with today's date as the folder name."""
    today = datetime.now().strftime("%Y-%m-%d")
    folder = evaluation_config.get_date_folder()
    assert folder.name == today
    assert str(folder).endswith(today)


def test_output_paths_are_correct():
    """Test that the output paths are correctly set in the configuration."""
    paths = evaluation_config.OUTPUT_PATHS
    assert isinstance(paths.output_dir, Path)
    assert isinstance(paths.evaluation_dir, Path)
    assert isinstance(paths.evaluation_log_file, Path)
    assert paths.evaluation_log_file.name == "evaluation_log.csv"


@patch("evaluation_suite.search_evaluation.evaluation_config.settings")
def test_get_active_search_types_exact_only(mock_settings):
    """Test that get_active_search_types returns ['exact'] when only keyword boost is set."""
    mock_settings.KEYWORD_BOOST = 1
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0
    assert evaluation_config.get_active_search_types() == ["exact"]


@patch("evaluation_suite.search_evaluation.evaluation_config.settings")
def test_get_active_search_types_multiple(mock_settings):
    """Test that get_active_search_types returns multiple types when multiple boosts are set."""
    mock_settings.KEYWORD_BOOST = 1
    mock_settings.WILDCARD_BOOST = 2
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 3
    mock_settings.SEMANTIC_BOOST = 0
    types = evaluation_config.get_active_search_types()
    assert set(types) == {"exact", "wildcard", "fuzzy"}


@patch("evaluation_suite.search_evaluation.evaluation_config.settings")
def test_get_active_search_types_semantic_only(mock_settings):
    """Test that get_active_search_types returns ['semantic_only'] when only semantic boost is set."""
    mock_settings.KEYWORD_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 1
    assert evaluation_config.get_active_search_types() == ["semantic_only"]


@patch("evaluation_suite.search_evaluation.evaluation_config.settings")
def test_get_active_search_types_default_exact(mock_settings):
    """Test that get_active_search_types returns ['exact'] when no boosts are set."""
    mock_settings.KEYWORD_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0
    assert evaluation_config.get_active_search_types() == ["exact"]


@patch("evaluation_suite.search_evaluation.evaluation_config.get_active_search_types")
def test_get_active_search_type_hybrid(mock_types):
    """Test that get_active_search_type returns 'hybrid' when multiple types are active."""
    mock_types.return_value = ["exact", "wildcard"]
    assert evaluation_config.get_active_search_type() == "hybrid"


@patch("evaluation_suite.search_evaluation.evaluation_config.get_active_search_types")
def test_get_active_search_type_single(mock_types):
    """Test that get_active_search_type returns the single active type."""
    mock_types.return_value = ["stemmed"]
    assert evaluation_config.get_active_search_type() == "stemmed"


@patch("evaluation_suite.search_evaluation.evaluation_config.settings")
@patch("evaluation_suite.search_evaluation.evaluation_config.get_timestamp")
def test_get_search_config_returns_dict(mock_timestamp, mock_settings):
    """Test that get_search_config returns a dictionary with the correct values."""
    mock_timestamp.return_value = "2024-02-27_12-00-00"
    mock_settings.SCORE_FILTER = 0.5
    mock_settings.RESULT_SIZE = 10
    mock_settings.KEYWORD_BOOST = 1
    mock_settings.ANALYSER_BOOST = 2
    mock_settings.SEMANTIC_BOOST = 3
    mock_settings.FUZZY_BOOST = 4
    mock_settings.WILDCARD_BOOST = 5
    mock_settings.FUZZINESS = 2
    mock_settings.MAX_EXPANSIONS = 50

    config = evaluation_config.get_search_config()
    assert config["search_type"] in {"exact", "stemmed", "fuzzy", "wildcard", "semantic_only", "hybrid"}
    assert config["score_filter"] == 0.5
    assert config["result_size"] == 10
    assert config["keyword_boost"] == 1
    assert config["analyser_boost"] == 2
    assert config["semantic_boost"] == 3
    assert config["fuzzy_boost"] == 4
    assert config["wildcard_boost"] == 5
    assert config["fuzziness"] == 2
    assert config["max_expansions"] == 50
    assert config["timestamp"] == "2024-02-27_12-00-00"
