"""Unit tests for IAM dataset filters."""

import pytest
from iam_testing.iam_filters import (
    FOOTER_THRESHOLD,
    HEADER_THRESHOLD,
    SIGNATURE_TOLERANCE,
    filter_iam_header_footer,
    filter_iam_signature,
    normalize_text,
)
from iam_testing.schemas import WordBlock


class TestNormalizeText:
    """Tests for normalize_text function."""

    def test_collapses_multiple_spaces(self):
        assert normalize_text("hello   world") == "hello world"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_text("  hello world  ") == "hello world"

    def test_handles_tabs_and_newlines(self):
        assert normalize_text("hello\t\nworld") == "hello world"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_single_word(self):
        assert normalize_text("hello") == "hello"


class TestFilterIamHeaderFooter:
    """Tests for filter_iam_header_footer function."""

    def _make_word(self, text: str, top: float = 0.5, confidence: float = 99.0) -> WordBlock:
        """Create a WordBlock for testing."""
        return WordBlock(
            text=text,
            text_type="PRINTED",
            confidence=confidence,
            bbox_left=0.1,
            bbox_top=top,
        )

    def test_filters_sentence_in_header(self):
        words = [
            self._make_word("Sentence", top=0.05),
            self._make_word("Database", top=0.05),
            self._make_word("Hello", top=0.3),
        ]
        filtered, _ = filter_iam_header_footer(words)
        assert len(filtered) == 1
        assert filtered[0].text == "Hello"

    def test_filters_form_id_in_header(self):
        words = [
            self._make_word("A01-000u", top=0.05),
            self._make_word("Hello", top=0.3),
        ]
        filtered, _ = filter_iam_header_footer(words)
        assert len(filtered) == 1
        assert filtered[0].text == "Hello"

    def test_filters_various_form_id_formats(self):
        """Test form ID patterns like A01-000, A01-000u, R06-121."""
        form_ids = ["A01-000", "A01-000u", "R06-121", "C02-059", "F07-028b"]
        for form_id in form_ids:
            words = [
                self._make_word(form_id, top=0.05),
                self._make_word("Content", top=0.3),
            ]
            filtered, _ = filter_iam_header_footer(words)
            assert len(filtered) == 1, f"Failed to filter form ID: {form_id}"

    def test_does_not_filter_header_words_below_threshold(self):
        """Words matching header patterns but not in header region should be kept."""
        words = [
            self._make_word("Sentence", top=0.3),  # Below header threshold
            self._make_word("Database", top=0.3),
        ]
        filtered, _ = filter_iam_header_footer(words)
        assert len(filtered) == 2

    def test_filters_name_label_in_footer(self):
        words = [
            self._make_word("Hello", top=0.3),
            self._make_word("Name:", top=0.80),
        ]
        filtered, name_top = filter_iam_header_footer(words)
        assert len(filtered) == 1
        assert filtered[0].text == "Hello"
        assert name_top == pytest.approx(0.80)

    def test_does_not_filter_name_above_footer_threshold(self):
        words = [
            self._make_word("Name:", top=0.5),  # Above footer threshold
        ]
        filtered, name_top = filter_iam_header_footer(words)
        assert len(filtered) == 1
        assert name_top is None

    def test_empty_list_returns_empty(self):
        filtered, name_top = filter_iam_header_footer([])
        assert filtered == []
        assert name_top is None

    def test_returns_name_label_position(self):
        words = [
            self._make_word("Content", top=0.3),
            self._make_word("Name:", top=0.79),
        ]
        _, name_top = filter_iam_header_footer(words)
        assert name_top == pytest.approx(0.79)


class TestFilterIamSignature:
    """Tests for filter_iam_signature function."""

    def _make_word(self, text: str, top: float) -> WordBlock:
        """Create a WordBlock for testing."""
        return WordBlock(
            text=text,
            text_type="HANDWRITING",
            confidence=90.0,
            bbox_left=0.1,
            bbox_top=top,
        )

    def test_filters_signature_near_name_label(self):
        name_label_top = 0.79
        words = [
            self._make_word("Content", top=0.3),
            self._make_word("John", top=0.79),  # Signature at same height as Name:
            self._make_word("Smith", top=0.80),
        ]
        filtered = filter_iam_signature(words, name_label_top)
        assert len(filtered) == 1
        assert filtered[0].text == "Content"

    def test_does_not_filter_when_no_name_label(self):
        words = [
            self._make_word("Content", top=0.3),
            self._make_word("John", top=0.79),
        ]
        filtered = filter_iam_signature(words, None)
        assert len(filtered) == 2

    def test_signature_tolerance_boundary(self):
        name_label_top = 0.79
        tolerance = SIGNATURE_TOLERANCE

        # Just inside tolerance - should be filtered
        inside_word = self._make_word("Inside", top=name_label_top + tolerance - 0.001)
        filtered = filter_iam_signature([inside_word], name_label_top)
        assert len(filtered) == 0

        # Just outside tolerance - should be kept
        outside_word = self._make_word("Outside", top=name_label_top + tolerance + 0.01)
        filtered = filter_iam_signature([outside_word], name_label_top)
        assert len(filtered) == 1

    def test_empty_list_returns_empty(self):
        filtered = filter_iam_signature([], 0.79)
        assert filtered == []


class TestThresholdConstants:
    """Test that threshold constants have sensible values."""

    def test_header_threshold_is_top_portion(self):
        assert 0 < HEADER_THRESHOLD < 0.25

    def test_footer_threshold_is_bottom_portion(self):
        assert 0.5 < FOOTER_THRESHOLD < 1.0

    def test_signature_tolerance_is_small(self):
        assert 0 < SIGNATURE_TOLERANCE < 0.1
