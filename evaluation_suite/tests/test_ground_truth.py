"""Unit tests for the ground_truth auto-generation module."""

from evaluation_suite.search_evaluation.relevance import ground_truth


class TestClassifyQuery:
    """Tests for classify_query."""

    def test_short_phrase_is_keyword(self):
        assert ground_truth.classify_query("brain injury") == "keyword_phrase"

    def test_trailing_question_mark_is_question(self):
        assert ground_truth.classify_query("Was the applicant in a coma?") == "question"

    def test_short_phrase_with_question_mark_is_question(self):
        assert ground_truth.classify_query("coma?") == "question"

    def test_long_phrase_is_question(self):
        # 5+ words counts as a question even without a question mark.
        assert ground_truth.classify_query("treatment after brain injury report") == "question"

    def test_empty_is_keyword(self):
        assert ground_truth.classify_query("") == "keyword_phrase"


class TestExtractQueryTerms:
    """Tests for extract_query_terms."""

    def test_keyword_keeps_all_words(self):
        terms = ground_truth.extract_query_terms("brain injury", "keyword_phrase")
        assert terms == ["brain", "injury"]

    def test_question_filters_stop_words(self):
        terms = ground_truth.extract_query_terms("Was the applicant in a coma?", "question")
        assert "applicant" in terms
        assert "coma" in terms
        # Common stop words removed.
        assert "was" not in terms
        assert "the" not in terms
        assert "in" not in terms

    def test_single_char_tokens_dropped(self):
        terms = ground_truth.extract_query_terms("a b coma", "keyword_phrase")
        assert terms == ["coma"]

    def test_classification_inferred_when_missing(self):
        # No query_type passed -> question (ends with ?) -> stop words removed.
        terms = ground_truth.extract_query_terms("Was the applicant injured?")
        assert "injured" in terms
        assert "was" not in terms


class TestGenerateExpectedChunks:
    """Tests for generate_expected_chunks."""

    def test_matches_whole_words_only(self):
        chunk_lookup = {
            "c1": "The applicant suffered a brain injury after the assault.",
            "c2": "No relevant content here about weather.",
            "c3": "Brainstorming session notes",  # 'brain' substring should NOT match
        }
        result = ground_truth.generate_expected_chunks("brain injury", chunk_lookup, "keyword_phrase")
        assert result == ["c1"]

    def test_returns_sorted_ids(self):
        chunk_lookup = {
            "c3": "coma reported",
            "c1": "the patient was in a coma",
            "c2": "unrelated",
        }
        result = ground_truth.generate_expected_chunks("coma", chunk_lookup, "keyword_phrase")
        assert result == ["c1", "c3"]

    def test_no_terms_returns_empty(self):
        chunk_lookup = {"c1": "anything"}
        # A single stop-word question with no content terms -> no expected chunks.
        result = ground_truth.generate_expected_chunks("the?", chunk_lookup, "question")
        assert result == []

    def test_no_match_returns_empty(self):
        chunk_lookup = {"c1": "completely unrelated text"}
        result = ground_truth.generate_expected_chunks("fracture", chunk_lookup, "keyword_phrase")
        assert result == []
