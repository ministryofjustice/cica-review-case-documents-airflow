"""Unit tests for generate_expected_chunks.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from evaluation_suite.search_evaluation import generate_expected_chunks


def sample_chunks():
    """Helper function to provide sample chunks for testing."""
    return [
        {"chunk_id": "c1", "chunk_text": "The injury occurred on 12/05/2021.", "page_number": 1},
        {"chunk_id": "c2", "chunk_text": "There were multiple injuries reported.", "page_number": 2},
        {"chunk_id": "c3", "chunk_text": "Incident date: 2021-05-12.", "page_number": 3},
        {"chunk_id": "c4", "chunk_text": "No relevant information.", "page_number": 4},
    ]


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
def test_find_matching_chunks_regular_keyword(mock_is_date_search):
    """Test that find_matching_chunks correctly matches regular keywords."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = False

    result = generate_expected_chunks.find_matching_chunks(
        chunks, "injury", use_date_variants=False, use_stemming=False
    )
    chunk_ids = [c["chunk_id"] for c in result]
    assert "c1" in chunk_ids
    assert "c2" not in chunk_ids
    assert "c3" not in chunk_ids
    assert "c4" not in chunk_ids


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
def test_find_matching_chunks_regular_stemming(mock_is_date_search):
    """Test that find_matching_chunks correctly matches keywords with stemming when use_stemming=True."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = False

    result = generate_expected_chunks.find_matching_chunks(
        chunks, "injuries", use_date_variants=False, use_stemming=True
    )
    chunk_ids = [c["chunk_id"] for c in result]
    assert "c1" in chunk_ids
    assert "c2" in chunk_ids
    assert "c3" not in chunk_ids
    assert "c4" not in chunk_ids


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
@patch("evaluation_suite.search_evaluation.generate_expected_chunks.extract_dates_for_search")
def test_find_matching_chunks_date_variants(mock_extract_dates, mock_is_date_search):
    """Test that find_matching_chunks correctly matches date variants when use_date_variants=True."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = True
    mock_extract_dates.return_value = ["12/05/2021", "2021-05-12"]

    result = generate_expected_chunks.find_matching_chunks(
        chunks, "12/05/2021", use_date_variants=True, use_stemming=False
    )
    chunk_ids = [c["chunk_id"] for c in result]
    assert "c1" in chunk_ids
    assert "c3" in chunk_ids
    assert "c2" not in chunk_ids
    assert "c4" not in chunk_ids


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
def test_find_matching_chunks_date_exact(mock_is_date_search):
    """Test that find_matching_chunks correctly matches exact date when use_date_variants=False."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = True

    result = generate_expected_chunks.find_matching_chunks(
        chunks, "12/05/2021", use_date_variants=False, use_stemming=False
    )
    chunk_ids = [c["chunk_id"] for c in result]
    assert "c1" in chunk_ids
    assert "c3" not in chunk_ids
    assert "c2" not in chunk_ids
    assert "c4" not in chunk_ids


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
def test_find_matching_chunks_no_match(mock_is_date_search):
    """Test that find_matching_chunks returns empty when no match found."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = False

    result = generate_expected_chunks.find_matching_chunks(
        chunks, "unrelated", use_date_variants=False, use_stemming=False
    )
    assert result == []


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
def test_find_matching_chunks_multi_word(mock_is_date_search):
    """Test that find_matching_chunks matches any word in multi-word search term."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = False

    result = generate_expected_chunks.find_matching_chunks(
        chunks, "injury incident", use_date_variants=False, use_stemming=False
    )
    chunk_ids = [c["chunk_id"] for c in result]
    assert "c1" in chunk_ids
    assert "c3" in chunk_ids
    assert "c2" not in chunk_ids
    assert "c4" not in chunk_ids


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
def test_find_matching_chunks_empty_term(mock_is_date_search):
    """Test that find_matching_chunks returns empty for empty search term."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = False

    result = generate_expected_chunks.find_matching_chunks(chunks, "", use_date_variants=False, use_stemming=False)
    assert result == []


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.is_date_search")
def test_find_matching_chunks_whitespace_handling(mock_is_date_search):
    """Test that find_matching_chunks handles whitespace in search term."""
    chunks = sample_chunks()
    mock_is_date_search.return_value = False

    result = generate_expected_chunks.find_matching_chunks(
        chunks, "  injury  ", use_date_variants=False, use_stemming=False
    )
    chunk_ids = [c["chunk_id"] for c in result]
    assert "c1" in chunk_ids


# Tests for _read_csv_file
@patch("builtins.open", create=True)
def test_read_csv_file_success(mock_file):
    """Test that _read_csv_file reads CSV correctly."""
    mock_file.return_value.__enter__.return_value = MagicMock()

    with patch("evaluation_suite.search_evaluation.generate_expected_chunks.csv.DictReader") as mock_reader:
        mock_reader.return_value.fieldnames = ["search_term", "expected_chunk_id"]
        mock_reader.return_value.__iter__ = lambda x: iter([{"search_term": "injury", "expected_chunk_id": ""}])

        fieldnames, rows = generate_expected_chunks._read_csv_file(Path("test.csv"))

        assert fieldnames == ["search_term", "expected_chunk_id"]
        assert len(rows) == 1


# Tests for _write_csv_file
@patch("builtins.open", create=True)
def test_write_csv_file_success(mock_file):
    """Test that _write_csv_file writes CSV correctly."""
    mock_file_handle = MagicMock()
    mock_file.return_value.__enter__.return_value = mock_file_handle

    with patch("evaluation_suite.search_evaluation.generate_expected_chunks.csv.DictWriter") as mock_writer:
        fieldnames = ["search_term", "expected_chunk_id"]
        rows = [{"search_term": "injury", "expected_chunk_id": "c1"}]

        generate_expected_chunks._write_csv_file(Path("test.csv"), fieldnames, rows)

        mock_writer.assert_called_once_with(mock_file_handle, fieldnames=fieldnames)


# Tests for _process_search_terms
@patch("evaluation_suite.search_evaluation.generate_expected_chunks.find_matching_chunks")
def test_process_search_terms_success(mock_find_chunks):
    """Test that _process_search_terms updates rows correctly."""
    mock_find_chunks.return_value = [{"chunk_id": "c1", "page_number": 1}]

    rows = [{"search_term": "injury", "expected_chunk_id": "", "expected_page_number": ""}]
    chunks = sample_chunks()

    result = generate_expected_chunks._process_search_terms(rows, chunks)

    assert result[0]["expected_chunk_id"] == "c1"
    assert result[0]["expected_page_number"] == "1"


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.find_matching_chunks")
def test_process_search_terms_empty_term(mock_find_chunks):
    """Test that _process_search_terms skips empty search terms."""
    rows = [{"search_term": "", "expected_chunk_id": "", "expected_page_number": ""}]
    chunks = sample_chunks()

    result = generate_expected_chunks._process_search_terms(rows, chunks)

    mock_find_chunks.assert_not_called()
    assert result[0]["expected_chunk_id"] == ""


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.find_matching_chunks")
def test_process_search_terms_exception_handled(mock_find_chunks):
    """Test that _process_search_terms handles exceptions."""
    mock_find_chunks.side_effect = Exception("Search error")

    rows = [{"search_term": "injury", "expected_chunk_id": "", "expected_page_number": ""}]
    chunks = sample_chunks()

    with patch("evaluation_suite.search_evaluation.generate_expected_chunks.logger") as mock_logger:
        result = generate_expected_chunks._process_search_terms(rows, chunks)

        mock_logger.error.assert_called()
        assert result[0]["expected_chunk_id"] == ""


# Tests for generate_expected_chunks
@patch("evaluation_suite.search_evaluation.generate_expected_chunks._write_csv_file")
@patch("evaluation_suite.search_evaluation.generate_expected_chunks._process_search_terms")
@patch("evaluation_suite.search_evaluation.generate_expected_chunks.get_chunk_details_from_opensearch")
@patch("evaluation_suite.search_evaluation.generate_expected_chunks._read_csv_file")
def test_generate_expected_chunks_success(mock_read_csv, mock_get_chunks, mock_process, mock_write_csv):
    """Test that generate_expected_chunks completes successfully."""
    fieldnames = ["search_term", "expected_chunk_id", "expected_page_number"]
    rows = [{"search_term": "injury", "expected_chunk_id": "", "expected_page_number": ""}]
    mock_read_csv.return_value = (fieldnames, rows)
    mock_get_chunks.return_value = sample_chunks()
    mock_process.return_value = rows

    generate_expected_chunks.generate_expected_chunks()

    mock_read_csv.assert_called_once()
    mock_get_chunks.assert_called_once()
    mock_process.assert_called_once()
    mock_write_csv.assert_called_once()


@patch("evaluation_suite.search_evaluation.generate_expected_chunks._read_csv_file")
def test_generate_expected_chunks_no_headers(mock_read_csv):
    """Test that generate_expected_chunks handles no CSV headers."""
    mock_read_csv.return_value = (None, [])

    with patch("evaluation_suite.search_evaluation.generate_expected_chunks.logger") as mock_logger:
        generate_expected_chunks.generate_expected_chunks()
        mock_logger.error.assert_called_with("CSV has no headers")


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.get_chunk_details_from_opensearch")
@patch("evaluation_suite.search_evaluation.generate_expected_chunks._read_csv_file")
def test_generate_expected_chunks_no_chunks_loaded(mock_read_csv, mock_get_chunks):
    """Test that generate_expected_chunks handles no chunks from OpenSearch."""
    fieldnames = ["search_term", "expected_chunk_id", "expected_page_number"]
    rows = [{"search_term": "injury", "expected_chunk_id": "", "expected_page_number": ""}]
    mock_read_csv.return_value = (fieldnames, rows)
    mock_get_chunks.return_value = []

    with patch("evaluation_suite.search_evaluation.generate_expected_chunks.logger") as mock_logger:
        generate_expected_chunks.generate_expected_chunks()
        mock_logger.error.assert_called_with("No chunks loaded from OpenSearch")


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.INPUT_FILE", Path("/nonexistent/path.csv"))
def test_generate_expected_chunks_input_file_not_found():
    """Test that generate_expected_chunks handles missing input file."""
    with patch("evaluation_suite.search_evaluation.generate_expected_chunks.logger") as mock_logger:
        generate_expected_chunks.generate_expected_chunks()
        mock_logger.error.assert_called()
        assert "not found" in mock_logger.error.call_args[0][0]


@patch("evaluation_suite.search_evaluation.generate_expected_chunks.generate_expected_chunks")
def test_main(mock_generate):
    """Test main entry point."""
    generate_expected_chunks.main()
    mock_generate.assert_called_once()
