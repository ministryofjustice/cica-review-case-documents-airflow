"""Unit tests for search_looper.py."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluation_suite.search_evaluation import search_looper


def sample_hits():
    """Helper to provide sample OpenSearch hits for testing."""
    return [
        {"_id": "c1", "_score": 10.0, "_source": {"chunk_text": "fractured arm", "page_number": 1}},
        {"_id": "c2", "_score": 5.0, "_source": {"chunk_text": "injury report", "page_number": 2}},
        {"_id": "c3", "_score": 2.0, "_source": {"chunk_text": "no relevant info", "page_number": 3}},
    ]


def write_sample_csv(path: Path, rows: list[dict]) -> Path:
    """Helper to write a sample CSV file for testing."""
    df = pd.DataFrame(rows)
    csv_path = path / "search_terms.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


# --- Tests for load_search_terms ---


def test_load_search_terms_returns_dataframe(tmp_path):
    """Test load_search_terms returns a DataFrame with correct columns."""
    csv_path = write_sample_csv(
        tmp_path,
        [
            {
                "search_term": "fracture",
                "expected_chunk_id": "c1",
                "manual identifications": "1",
                "acceptable associated terms": "bruise",
            },
        ],
    )
    df, metadata = search_looper.load_search_terms(csv_path)
    assert isinstance(df, pd.DataFrame)
    assert "search_term" in df.columns
    assert "manual_identifications" in df.columns
    assert "acceptable_terms" in df.columns


def test_load_search_terms_renames_columns(tmp_path):
    """Test load_search_terms renames columns correctly."""
    csv_path = write_sample_csv(
        tmp_path,
        [
            {"search_term": "fracture", "manual identifications": "2", "acceptable associated terms": "bruise"},
        ],
    )
    df, metadata = search_looper.load_search_terms(csv_path)
    assert "manual_identifications" in df.columns
    assert "acceptable_terms" in df.columns
    assert "manual identifications" not in df.columns
    assert "acceptable associated terms" not in df.columns


def test_load_search_terms_strips_whitespace(tmp_path):
    """Test load_search_terms strips whitespace from string columns."""
    csv_path = write_sample_csv(
        tmp_path,
        [
            {"search_term": "  fracture  ", "manual identifications": " 1 ", "acceptable associated terms": " bruise "},
        ],
    )
    df, metadata = search_looper.load_search_terms(csv_path)
    assert df["search_term"].iloc[0] == "fracture"
    assert df["manual_identifications"].iloc[0] == "1"
    assert df["acceptable_terms"].iloc[0] == "bruise"


def test_load_search_terms_fills_na(tmp_path):
    """Test load_search_terms fills NaN values with empty strings."""
    csv_path = write_sample_csv(
        tmp_path,
        [
            {"search_term": "fracture", "manual identifications": None, "acceptable associated terms": None},
        ],
    )
    df, metadata = search_looper.load_search_terms(csv_path)
    assert df["manual_identifications"].iloc[0] == ""
    assert df["acceptable_terms"].iloc[0] == ""


def test_load_search_terms_multiple_rows(tmp_path):
    """Test load_search_terms loads multiple rows correctly."""
    csv_path = write_sample_csv(
        tmp_path,
        [
            {"search_term": "fracture", "manual identifications": "1", "acceptable associated terms": "bruise"},
            {"search_term": "injury", "manual identifications": "2", "acceptable associated terms": "wound"},
        ],
    )
    df, metadata = search_looper.load_search_terms(csv_path)
    assert len(df) == 2
    assert df["search_term"].tolist() == ["fracture", "injury"]


# --- Tests for _process_hits ---


def test_process_hits_returns_correct_keys():
    """Test _process_hits returns dict with all required keys."""
    result = search_looper._process_hits(sample_hits(), "fracture")
    assert "all_chunk_ids" in result
    assert "all_page_numbers" in result
    assert "all_term_frequencies" in result
    assert "total_term_frequency" in result


def test_process_hits_empty_hits_returns_defaults():
    """Test _process_hits returns default empty values for empty hits."""
    result = search_looper._process_hits([], "fracture")
    assert result["all_chunk_ids"] == ""
    assert result["all_page_numbers"] == ""
    assert result["all_term_frequencies"] == ""
    assert result["total_term_frequency"] == 0


def test_process_hits_chunk_ids_joined():
    """Test _process_hits joins chunk IDs correctly."""
    result = search_looper._process_hits(sample_hits(), "fracture")
    assert "c1" in result["all_chunk_ids"]
    assert "c2" in result["all_chunk_ids"]
    assert "c3" in result["all_chunk_ids"]


def test_process_hits_page_numbers_joined():
    """Test _process_hits joins page numbers correctly."""
    result = search_looper._process_hits(sample_hits(), "fracture")
    assert "1" in result["all_page_numbers"]
    assert "2" in result["all_page_numbers"]
    assert "3" in result["all_page_numbers"]


def test_process_hits_term_frequency_counted():
    """Test _process_hits counts term frequency across hits correctly."""
    result = search_looper._process_hits(sample_hits(), "fracture")
    # "fractured arm" has 1, "injury report" has 0, "no relevant info" has 0
    assert result["total_term_frequency"] == 1


def test_process_hits_term_frequencies_joined():
    """Test _process_hits joins per-chunk term frequencies as string."""
    result = search_looper._process_hits(sample_hits(), "fracture")
    freqs = result["all_term_frequencies"].split(", ")
    assert freqs == ["1", "0", "0"]


def test_process_hits_missing_chunk_id_uses_na():
    """Test _process_hits uses N/A for missing chunk IDs."""
    hits = [{"_score": 5.0, "_source": {"chunk_text": "fracture", "page_number": 1}}]
    result = search_looper._process_hits(hits, "fracture")
    assert "N/A" in result["all_chunk_ids"]


def test_process_hits_missing_page_number_uses_na():
    """Test _process_hits uses N/A for missing page numbers."""
    hits = [{"_id": "c1", "_score": 5.0, "_source": {"chunk_text": "fracture"}}]
    result = search_looper._process_hits(hits, "fracture")
    assert "N/A" in result["all_page_numbers"]


# --- Tests for run_search_loop ---


def test_run_search_loop_returns_empty_df_when_file_not_found():
    """Test run_search_loop returns empty DataFrame when input file does not exist."""
    result, metadata = search_looper.run_search_loop(Path("/nonexistent/path/search_terms.csv"))
    assert isinstance(result, pd.DataFrame)
    assert result.empty


@patch("evaluation_suite.search_evaluation.search_looper.local_search_client")
@patch("evaluation_suite.search_evaluation.search_looper.settings")
def test_run_search_loop_returns_dataframe_with_results(mock_settings, mock_local_search, tmp_path):
    """Test run_search_loop returns DataFrame with correct columns on success."""
    mock_settings.SCORE_FILTER = 0
    mock_local_search.return_value = sample_hits()
    csv_path = write_sample_csv(
        tmp_path,
        [
            {
                "search_term": "fracture",
                "expected_chunk_id": "c1",
                "manual identifications": "1",
                "acceptable associated terms": "bruise",
                "expected_page_number": "1",
            },
        ],
    )
    result, metadata = search_looper.run_search_loop(csv_path)
    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert "search_term" in result.columns
    assert "all_chunk_ids" in result.columns
    assert "total_results" in result.columns


@patch("evaluation_suite.search_evaluation.search_looper.local_search_client")
@patch("evaluation_suite.search_evaluation.search_looper.settings")
def test_run_search_loop_filters_hits_by_score(mock_settings, mock_local_search, tmp_path):
    """Test run_search_loop filters hits below SCORE_FILTER threshold."""
    mock_settings.SCORE_FILTER = 6.0
    mock_local_search.return_value = sample_hits()
    csv_path = write_sample_csv(
        tmp_path,
        [
            {
                "search_term": "fracture",
                "expected_chunk_id": "c1",
                "manual identifications": "1",
                "acceptable associated terms": "bruise",
                "expected_page_number": "1",
            },
        ],
    )
    result, metadata = search_looper.run_search_loop(csv_path)
    # Only c1 has score >= 6.0
    assert result["total_results"].iloc[0] == 1
    assert "c1" in result["all_chunk_ids"].iloc[0]


@patch("evaluation_suite.search_evaluation.search_looper.local_search_client")
@patch("evaluation_suite.search_evaluation.search_looper.settings")
def test_run_search_loop_skips_empty_search_terms(mock_settings, mock_local_search, tmp_path):
    """Test run_search_loop skips rows with empty search terms."""
    mock_settings.SCORE_FILTER = 0
    mock_local_search.return_value = sample_hits()
    csv_path = write_sample_csv(
        tmp_path,
        [
            {
                "search_term": "",
                "expected_chunk_id": "",
                "manual identifications": "",
                "acceptable associated terms": "",
                "expected_page_number": "",
            },
            {
                "search_term": "fracture",
                "expected_chunk_id": "c1",
                "manual identifications": "1",
                "acceptable associated terms": "bruise",
                "expected_page_number": "1",
            },
        ],
    )
    result, metadata = search_looper.run_search_loop(csv_path)
    assert len(result) == 1
    assert result["search_term"].iloc[0] == "fracture"


@patch("evaluation_suite.search_evaluation.search_looper.local_search_client")
@patch("evaluation_suite.search_evaluation.search_looper.settings")
def test_run_search_loop_handles_search_exception(mock_settings, mock_local_search, tmp_path):
    """Test run_search_loop handles search exceptions gracefully and continues."""
    mock_settings.SCORE_FILTER = 0
    mock_local_search.side_effect = Exception("Search failed")
    csv_path = write_sample_csv(
        tmp_path,
        [
            {
                "search_term": "fracture",
                "expected_chunk_id": "c1",
                "manual identifications": "1",
                "acceptable associated terms": "bruise",
                "expected_page_number": "1",
            },
            {
                "search_term": "injury",
                "expected_chunk_id": "c2",
                "manual identifications": "1",
                "acceptable associated terms": "wound",
                "expected_page_number": "2",
            },
        ],
    )
    result, metadata = search_looper.run_search_loop(csv_path)
    # Both rows should still be in results with 0 hits
    assert len(result) == 2
    assert result["total_results"].iloc[0] == 0
    assert result["total_results"].iloc[1] == 0


@patch("evaluation_suite.search_evaluation.search_looper.local_search_client")
@patch("evaluation_suite.search_evaluation.search_looper.settings")
def test_run_search_loop_adds_index_column(mock_settings, mock_local_search, tmp_path):
    """Test run_search_loop adds 1-based index column to results."""
    mock_settings.SCORE_FILTER = 0
    mock_local_search.return_value = sample_hits()
    csv_path = write_sample_csv(
        tmp_path,
        [
            {
                "search_term": "fracture",
                "expected_chunk_id": "c1",
                "manual identifications": "1",
                "acceptable associated terms": "bruise",
                "expected_page_number": "1",
            },
            {
                "search_term": "injury",
                "expected_chunk_id": "c2",
                "manual identifications": "1",
                "acceptable associated terms": "wound",
                "expected_page_number": "2",
            },
        ],
    )
    result, metadata = search_looper.run_search_loop(csv_path)
    assert "index" in result.columns
    assert result["index"].tolist() == [1, 2]


@patch("evaluation_suite.search_evaluation.search_looper.local_search_client")
@patch("evaluation_suite.search_evaluation.search_looper.settings")
def test_run_search_loop_multiple_terms(mock_settings, mock_local_search, tmp_path):
    """Test run_search_loop processes multiple search terms correctly."""
    mock_settings.SCORE_FILTER = 0
    mock_local_search.return_value = sample_hits()
    csv_path = write_sample_csv(
        tmp_path,
        [
            {
                "search_term": "fracture",
                "expected_chunk_id": "c1",
                "manual identifications": "1",
                "acceptable associated terms": "bruise",
                "expected_page_number": "1",
            },
            {
                "search_term": "injury",
                "expected_chunk_id": "c2",
                "manual identifications": "1",
                "acceptable associated terms": "wound",
                "expected_page_number": "2",
            },
            {
                "search_term": "swelling",
                "expected_chunk_id": "c3",
                "manual identifications": "1",
                "acceptable associated terms": "contusion",
                "expected_page_number": "3",
            },
        ],
    )
    result, metadata = search_looper.run_search_loop(csv_path)
    assert len(result) == 3
    assert mock_local_search.call_count == 3
