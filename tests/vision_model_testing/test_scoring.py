"""Tests for vision model scoring."""

from vision_model_testing.scoring import (
    VisionScoreResult,
    calculate_wer_cer,
    generate_vision_summary,
    score_vision_result,
)


class TestCalculateWerCer:
    """Test WER/CER calculation."""

    def test_identical_text(self):
        """Identical text should have 0 WER and CER."""
        wer, cer = calculate_wer_cer("hello world", "hello world")
        assert wer == 0.0
        assert cer == 0.0

    def test_completely_different_text(self):
        """Completely different text should have high WER/CER."""
        wer, cer = calculate_wer_cer("hello world", "goodbye universe")
        assert wer == 1.0  # All words wrong
        assert cer > 0.5  # More than half characters wrong

    def test_partial_match(self):
        """Partial match should have intermediate WER/CER."""
        wer, cer = calculate_wer_cer("hello world", "hello there")
        assert 0 < wer < 1
        assert 0 < cer < 1

    def test_empty_ground_truth(self):
        """Empty ground truth with non-empty prediction should return 1.0."""
        wer, cer = calculate_wer_cer("", "some text")
        assert wer == 1.0
        assert cer == 1.0

    def test_empty_prediction(self):
        """Non-empty ground truth with empty prediction should return 1.0."""
        wer, cer = calculate_wer_cer("some text", "")
        assert wer == 1.0
        assert cer == 1.0

    def test_both_empty(self):
        """Both empty should return 0.0."""
        wer, cer = calculate_wer_cer("", "")
        assert wer == 0.0
        assert cer == 0.0

    def test_whitespace_only_treated_as_empty(self):
        """Whitespace-only text should be treated as empty."""
        wer, cer = calculate_wer_cer("   ", "   ")
        assert wer == 0.0
        assert cer == 0.0


class TestScoreVisionResult:
    """Test VisionScoreResult creation."""

    def test_creates_score_result(self):
        """score_vision_result should create valid VisionScoreResult."""
        result = score_vision_result(
            page_id="page1",
            gt_text="hello world",
            vision_text="hello world",
            vision_model="nova-pro",
            vision_prompt="v1_abc12345",
            input_tokens=100,
            output_tokens=10,
        )

        assert isinstance(result, VisionScoreResult)
        assert result.page_id == "page1"
        assert result.vision_model == "nova-pro"
        assert result.wer == 0.0
        assert result.cer == 0.0

    def test_word_counts(self):
        """Word counts should be calculated correctly."""
        result = score_vision_result(
            page_id="page1",
            gt_text="one two three",
            vision_text="one two",
            vision_model="nova-pro",
            vision_prompt="v1",
            input_tokens=100,
            output_tokens=10,
        )

        assert result.gt_word_count == 3
        assert result.vision_word_count == 2


class TestGenerateVisionSummary:
    """Test summary generation."""

    def test_empty_scores(self):
        """Empty scores should return minimal summary."""
        summary = generate_vision_summary([])
        assert summary["total_pages"] == 0
        assert summary["avg_wer"] == 0.0

    def test_summary_with_scores(self):
        """Summary should aggregate scores correctly."""
        scores = [
            VisionScoreResult(
                page_id="p1",
                vision_model="nova-pro",
                vision_prompt="v1",
                wer=0.1,
                cer=0.05,
                gt_word_count=10,
                vision_word_count=10,
                gt_text="gt",
                vision_text="vision",
                input_tokens=100,
                output_tokens=10,
            ),
            VisionScoreResult(
                page_id="p2",
                vision_model="nova-pro",
                vision_prompt="v1",
                wer=0.3,
                cer=0.15,
                gt_word_count=20,
                vision_word_count=18,
                gt_text="gt2",
                vision_text="vision2",
                input_tokens=200,
                output_tokens=20,
            ),
        ]

        summary = generate_vision_summary(scores)

        assert summary["total_pages"] == 2
        assert summary["avg_wer"] == 0.2  # (0.1 + 0.3) / 2
        assert summary["avg_cer"] == 0.1  # (0.05 + 0.15) / 2
        assert summary["min_wer"] == 0.1
        assert summary["max_wer"] == 0.3
        assert summary["total_input_tokens"] == 300
        assert summary["total_output_tokens"] == 30

    def test_perfect_pages_count(self):
        """Should count pages with WER=0 as perfect."""
        scores = [
            VisionScoreResult(
                page_id="p1",
                vision_model="nova-pro",
                vision_prompt="v1",
                wer=0.0,
                cer=0.0,
                gt_word_count=10,
                vision_word_count=10,
                gt_text="gt",
                vision_text="vision",
                input_tokens=100,
                output_tokens=10,
            ),
            VisionScoreResult(
                page_id="p2",
                vision_model="nova-pro",
                vision_prompt="v1",
                wer=0.1,
                cer=0.05,
                gt_word_count=10,
                vision_word_count=10,
                gt_text="gt",
                vision_text="vision",
                input_tokens=100,
                output_tokens=10,
            ),
        ]

        summary = generate_vision_summary(scores)
        assert summary["perfect_pages"] == 1
