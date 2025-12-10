"""Unit tests for chunk_metrics module.

Tests calculate_chunk_match() for various edge cases in precision/recall calculation.
"""

import pandas as pd
from testing.chunk_metrics import calculate_chunk_match, safe_int


class TestCalculateChunkMatch:
    """Tests for calculate_chunk_match function."""

    def test_perfect_match_single_chunk(self):
        """All expected chunks found, no extras."""
        row = pd.Series({"expected_chunk_id": "chunk1", "all_chunk_ids": "chunk1"})
        result = calculate_chunk_match(row)

        assert result["precision"] == 100.0
        assert result["recall"] == 100.0
        assert result["chunk_match_percentage"] == 100.0
        assert result["missing_chunk_ids"] == ""

    def test_perfect_match_multiple_chunks(self):
        """All expected chunks found, no extras."""
        row = pd.Series({"expected_chunk_id": "chunk1, chunk2, chunk3", "all_chunk_ids": "chunk1, chunk2, chunk3"})
        result = calculate_chunk_match(row)

        assert result["precision"] == 100.0
        assert result["recall"] == 100.0
        assert result["missing_chunk_ids"] == ""

    def test_partial_recall(self):
        """Some expected chunks found, some missing."""
        row = pd.Series({"expected_chunk_id": "chunk1, chunk2, chunk3", "all_chunk_ids": "chunk1, chunk2"})
        result = calculate_chunk_match(row)

        # 2 of 3 expected found = 66.67% recall
        assert result["recall"] == 66.67
        # 2 of 2 found are expected = 100% precision
        assert result["precision"] == 100.0
        assert result["missing_chunk_ids"] == "chunk3"

    def test_low_precision_high_recall(self):
        """All expected chunks found plus many extras."""
        row = pd.Series({"expected_chunk_id": "chunk1", "all_chunk_ids": "chunk1, chunk2, chunk3, chunk4, chunk5"})
        result = calculate_chunk_match(row)

        # 1 of 1 expected found = 100% recall
        assert result["recall"] == 100.0
        # 1 of 5 found are expected = 20% precision
        assert result["precision"] == 20.0
        assert result["missing_chunk_ids"] == ""

    def test_no_expected_with_results_false_positives(self):
        """No expected chunks but results returned = all false positives."""
        row = pd.Series({"expected_chunk_id": "", "all_chunk_ids": "chunk1, chunk2, chunk3"})
        result = calculate_chunk_match(row)

        assert result["precision"] == 0.0
        assert result["recall"] is None  # Undefined when no expected
        assert result["chunk_match_percentage"] is None
        assert result["missing_chunk_ids"] == ""

    def test_no_expected_no_results_correct_rejection(self):
        """No expected chunks and no results = correct rejection."""
        row = pd.Series({"expected_chunk_id": "", "all_chunk_ids": ""})
        result = calculate_chunk_match(row)

        assert result["precision"] == 100.0
        assert result["recall"] == 100.0
        assert result["chunk_match_percentage"] == 100.0
        assert result["missing_chunk_ids"] == ""

    def test_expected_but_no_results(self):
        """Expected chunks but none returned."""
        row = pd.Series({"expected_chunk_id": "chunk1, chunk2", "all_chunk_ids": ""})
        result = calculate_chunk_match(row)

        # 0 of 2 expected found = 0% recall
        assert result["recall"] == 0.0
        # No results found = 0% precision (0/0 edge case handled as 0)
        assert result["precision"] == 0.0
        assert "chunk1" in result["missing_chunk_ids"]
        assert "chunk2" in result["missing_chunk_ids"]

    def test_no_overlap(self):
        """Results returned but none are expected."""
        row = pd.Series({"expected_chunk_id": "chunk1, chunk2", "all_chunk_ids": "chunk3, chunk4"})
        result = calculate_chunk_match(row)

        # 0 of 2 expected found = 0% recall
        assert result["recall"] == 0.0
        # 0 of 2 found are expected = 0% precision
        assert result["precision"] == 0.0
        assert "chunk1" in result["missing_chunk_ids"]
        assert "chunk2" in result["missing_chunk_ids"]

    def test_handles_whitespace(self):
        """Handles extra whitespace in chunk IDs."""
        row = pd.Series({"expected_chunk_id": "  chunk1 ,  chunk2  ", "all_chunk_ids": "chunk1,   chunk2"})
        result = calculate_chunk_match(row)

        assert result["precision"] == 100.0
        assert result["recall"] == 100.0

    def test_handles_nan_values(self):
        """Handles NaN/None values gracefully."""
        row = pd.Series({"expected_chunk_id": None, "all_chunk_ids": None})
        result = calculate_chunk_match(row)

        # None converts to "None" string, which is treated as empty after strip
        assert result["precision"] == 100.0  # Correct rejection
        assert result["recall"] == 100.0


class TestSafeInt:
    """Tests for safe_int function."""

    def test_valid_int(self) -> None:
        """Test that valid integers are returned as-is."""
        assert safe_int(42) == 42

    def test_valid_string_int(self) -> None:
        """Test that string integers are converted correctly."""
        assert safe_int("42") == 42

    def test_valid_float(self) -> None:
        """Test that floats are truncated to integers."""
        assert safe_int(42.7) == 42

    def test_empty_string(self) -> None:
        """Test that empty string returns default (0)."""
        assert safe_int("") == 0

    def test_dash(self) -> None:
        """Test that dash character returns default (0)."""
        assert safe_int("-") == 0

    def test_nan(self) -> None:
        """Test that NaN returns default (0)."""
        assert safe_int(float("nan")) == 0

    def test_none(self) -> None:
        """Test that None returns default (0)."""
        assert safe_int(None) == 0

    def test_invalid_string(self) -> None:
        """Test that invalid strings return default (0)."""
        assert safe_int("abc") == 0

    def test_custom_default(self) -> None:
        """Test that custom default value is returned for invalid input."""
        assert safe_int("", default=-1) == -1
