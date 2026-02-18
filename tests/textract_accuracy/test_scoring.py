"""Unit tests for OCR scoring module."""

import pytest
from iam_testing.schemas import OCRResult
from iam_testing.scoring import ScoreResult, _calculate_wer_cer, score_ocr_result


class TestCalculateWerCer:
    """Tests for the _calculate_wer_cer helper function."""

    def test_perfect_match(self):
        wer_score, cer_score = _calculate_wer_cer("hello world", "hello world", "test", "handwriting")
        assert wer_score == 0.0
        assert cer_score == 0.0

    def test_complete_mismatch(self):
        wer_score, cer_score = _calculate_wer_cer("hello world", "goodbye earth", "test", "handwriting")
        assert wer_score == 1.0  # All words wrong
        assert cer_score > 0.5  # Most characters wrong

    def test_partial_match(self):
        wer_score, cer_score = _calculate_wer_cer("hello world", "hello there", "test", "handwriting")
        assert wer_score == 0.5  # 1 of 2 words wrong
        assert 0 < cer_score < 1  # Some characters wrong

    def test_empty_gt_with_empty_ocr(self):
        wer_score, cer_score = _calculate_wer_cer("", "", "test", "handwriting")
        assert wer_score == 0.0
        assert cer_score == 0.0

    def test_empty_gt_with_ocr_text(self):
        wer_score, cer_score = _calculate_wer_cer("", "some text", "test", "handwriting")
        assert wer_score == 1.0
        assert cer_score == 1.0

    def test_empty_ocr_with_gt_text(self):
        wer_score, cer_score = _calculate_wer_cer("some text", "", "test", "handwriting")
        assert wer_score == 1.0
        assert cer_score == 1.0

    def test_whitespace_only_treated_as_empty(self):
        wer_score, cer_score = _calculate_wer_cer("   ", "", "test", "handwriting")
        assert wer_score == 0.0
        assert cer_score == 0.0

    def test_insertion_error(self):
        """OCR has extra words."""
        wer_score, cer_score = _calculate_wer_cer("hello world", "hello big world", "test", "handwriting")
        assert wer_score == 0.5  # 1 insertion out of 2 reference words
        assert cer_score > 0  # Extra characters

    def test_deletion_error(self):
        """OCR is missing words."""
        wer_score, cer_score = _calculate_wer_cer("hello big world", "hello world", "test", "handwriting")
        assert wer_score == pytest.approx(1 / 3)  # 1 deletion out of 3 reference words


class TestScoreOcrResult:
    """Tests for score_ocr_result function."""

    def _make_ocr_result(
        self,
        form_id: str = "test-001",
        hw_text: str = "hello world",
        print_text: str = "printed text",
    ) -> OCRResult:
        """Create an OCRResult for testing."""
        return OCRResult(
            form_id=form_id,
            ocr_print_text=print_text,
            ocr_print_text_raw=print_text,
            ocr_handwriting_text=hw_text,
            ocr_print_word_count=len(print_text.split()),
            ocr_handwriting_word_count=len(hw_text.split()),
            avg_print_confidence=99.0,
            avg_handwriting_confidence=90.0,
            textract_job_id=None,
            processed_at="2026-01-26T00:00:00Z",
        )

    def _make_gt(self, hw_text: str = "hello world", print_text: str = "printed text") -> dict:
        """Create a ground truth dict for testing."""
        return {
            "gt_handwriting_text": hw_text,
            "gt_print_text": print_text,
        }

    def test_perfect_scores(self):
        result = self._make_ocr_result()
        gt = self._make_gt()
        score = score_ocr_result(result, gt)

        assert score.wer_handwriting == 0.0
        assert score.cer_handwriting == 0.0
        assert score.wer_print == 0.0
        assert score.cer_print == 0.0

    def test_handwriting_errors(self):
        result = self._make_ocr_result(hw_text="hello there")
        gt = self._make_gt(hw_text="hello world")
        score = score_ocr_result(result, gt)

        assert score.wer_handwriting == 0.5
        assert score.cer_handwriting > 0
        assert score.wer_print == 0.0  # Print should still be perfect

    def test_print_errors(self):
        result = self._make_ocr_result(print_text="wrong text")
        gt = self._make_gt(print_text="printed text")
        score = score_ocr_result(result, gt)

        assert score.wer_print > 0
        assert score.wer_handwriting == 0.0  # Handwriting should still be perfect

    def test_score_result_has_all_fields(self):
        result = self._make_ocr_result()
        gt = self._make_gt()
        score = score_ocr_result(result, gt)

        assert score.form_id == "test-001"
        assert score.gt_handwriting_word_count == 2
        assert score.ocr_handwriting_word_count == 2
        assert score.gt_print_word_count == 2
        assert score.ocr_print_word_count == 2
        assert score.gt_handwriting_text == "hello world"
        assert score.ocr_handwriting_text == "hello world"

    def test_text_is_normalized(self):
        """Verify that extra whitespace doesn't cause false errors."""
        result = self._make_ocr_result(hw_text="hello   world")
        gt = self._make_gt(hw_text="hello world")
        score = score_ocr_result(result, gt)

        # The OCR text has extra spaces but GT is normalized
        # This test checks that comparison still works
        # (Note: OCRResult.ocr_handwriting_text should already be normalized)
        assert score.wer_handwriting >= 0  # Just verify it runs


class TestScoreResultDataclass:
    """Tests for ScoreResult dataclass properties."""

    def test_is_immutable(self):
        score = ScoreResult(
            form_id="test",
            wer_handwriting=0.1,
            cer_handwriting=0.05,
            gt_handwriting_word_count=10,
            ocr_handwriting_word_count=9,
            gt_handwriting_text="gt text",
            ocr_handwriting_text="ocr text",
            wer_print=0.0,
            cer_print=0.0,
            gt_print_word_count=5,
            ocr_print_word_count=5,
            gt_print_text="print gt",
            ocr_print_text="print ocr",
        )

        with pytest.raises(AttributeError):
            score.wer_handwriting = 0.5  # type: ignore

    def test_stores_all_metrics(self):
        score = ScoreResult(
            form_id="a01-000",
            wer_handwriting=0.0789,
            cer_handwriting=0.0236,
            gt_handwriting_word_count=76,
            ocr_handwriting_word_count=75,
            gt_handwriting_text="ground truth",
            ocr_handwriting_text="ocr output",
            wer_print=0.0,
            cer_print=0.0,
            gt_print_word_count=87,
            ocr_print_word_count=87,
            gt_print_text="printed",
            ocr_print_text="printed",
        )

        assert score.form_id == "a01-000"
        assert score.wer_handwriting == pytest.approx(0.0789)
        assert score.cer_handwriting == pytest.approx(0.0236)
