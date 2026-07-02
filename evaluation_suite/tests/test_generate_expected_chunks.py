"""Unit tests for generate_expected_chunks.py — per-case extension."""

import csv
from pathlib import Path
from unittest.mock import patch

from evaluation_suite.search_evaluation.generate_expected_chunks import (
    generate_expected_chunks_for_case,
)

_MOD = "evaluation_suite.search_evaluation.generate_expected_chunks"

_CHUNKS = [
    {"chunk_id": "c1", "chunk_text": "brain injury diagnosis", "page_number": 1, "case_ref": "26-700001"},
    {"chunk_id": "c2", "chunk_text": "whiplash treatment plan", "page_number": 2, "case_ref": "26-700001"},
]


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    names = fieldnames or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def test_generate_for_case_missing_csv_returns_early(tmp_path):
    """When csv_path does not exist the function returns without loading chunks."""
    csv_path = tmp_path / "search_terms.csv"

    with patch(f"{_MOD}.get_chunk_details_from_opensearch") as mock_load:
        generate_expected_chunks_for_case("26-700001", csv_path)

    mock_load.assert_not_called()


def test_generate_for_case_no_chunks_returns_early(tmp_path):
    """When OpenSearch returns no chunks the CSV is not modified."""
    csv_path = tmp_path / "search_terms.csv"
    _write_csv(
        csv_path,
        [{"search_term": "brain injury", "expected_chunk_id": "", "expected_page_number": ""}],
    )

    with patch(f"{_MOD}.get_chunk_details_from_opensearch", return_value=[]):
        generate_expected_chunks_for_case("26-700001", csv_path)

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["expected_chunk_id"] == ""


def test_generate_for_case_passes_case_ref_to_loader(tmp_path):
    """get_chunk_details_from_opensearch is called with the supplied case_ref."""
    csv_path = tmp_path / "search_terms.csv"
    _write_csv(
        csv_path,
        [{"search_term": "test", "expected_chunk_id": "", "expected_page_number": ""}],
    )

    with patch(f"{_MOD}.get_chunk_details_from_opensearch", return_value=_CHUNKS) as mock_load:
        generate_expected_chunks_for_case("26-700002", csv_path)

    mock_load.assert_called_once_with(case_ref="26-700002")


def test_generate_for_case_populates_expected_chunks(tmp_path):
    """Matching chunks are written to expected_chunk_id and expected_page_number."""
    csv_path = tmp_path / "search_terms.csv"
    _write_csv(
        csv_path,
        [
            {"search_term": "brain injury", "expected_chunk_id": "", "expected_page_number": ""},
            {"search_term": "whiplash", "expected_chunk_id": "", "expected_page_number": ""},
        ],
    )

    with patch(f"{_MOD}.get_chunk_details_from_opensearch", return_value=_CHUNKS):
        generate_expected_chunks_for_case("26-700001", csv_path)

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert "c1" in rows[0]["expected_chunk_id"]
    assert "1" in rows[0]["expected_page_number"]
    assert "c2" in rows[1]["expected_chunk_id"]
    assert "2" in rows[1]["expected_page_number"]


def test_generate_for_case_unmatched_term_leaves_columns_empty(tmp_path):
    """A search term with no matching chunks produces empty expected columns."""
    csv_path = tmp_path / "search_terms.csv"
    _write_csv(
        csv_path,
        [{"search_term": "completely unrelated term xyz", "expected_chunk_id": "", "expected_page_number": ""}],
    )

    with patch(f"{_MOD}.get_chunk_details_from_opensearch", return_value=_CHUNKS):
        generate_expected_chunks_for_case("26-700001", csv_path)

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["expected_chunk_id"] == ""
    assert rows[0]["expected_page_number"] == ""
