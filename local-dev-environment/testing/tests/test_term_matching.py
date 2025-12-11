"""Unit tests for term_matching module."""

from testing.term_matching import (
    check_terms_in_chunks,
    exact_match,
    fuzzy_match,
    stemmed_match,
    term_matches,
    term_matches_single,
    wildcard_match,
)


class TestExactMatch:
    """Tests for exact_match function (word boundary matching)."""

    def test_exact_word_found(self) -> None:
        """Test that exact word is found in text."""
        assert exact_match("hello", "hello world") is True

    def test_exact_word_not_found(self) -> None:
        """Test that non-matching term returns False."""
        assert exact_match("goodbye", "hello world") is False

    def test_case_insensitive(self) -> None:
        """Test that matching is case insensitive."""
        assert exact_match("HELLO", "hello world") is True
        assert exact_match("hello", "HELLO WORLD") is True

    def test_partial_word_no_match(self) -> None:
        """Test that partial word does NOT match (word boundary)."""
        assert exact_match("hell", "hello world") is False
        assert exact_match("brain", "brainwave") is False
        assert exact_match("run", "running") is False

    def test_word_at_start(self) -> None:
        """Test matching word at start of text."""
        assert exact_match("hello", "hello there") is True

    def test_word_at_end(self) -> None:
        """Test matching word at end of text."""
        assert exact_match("world", "hello world") is True

    def test_word_in_middle(self) -> None:
        """Test matching word in middle of text."""
        assert exact_match("is", "this is a test") is True

    def test_word_with_punctuation(self) -> None:
        """Test matching word adjacent to punctuation."""
        assert exact_match("hello", "hello, world!") is True
        assert exact_match("world", "hello, world!") is True

    def test_empty_term(self) -> None:
        """Test that empty term returns False (no word to match)."""
        assert exact_match("", "hello world") is False

    def test_empty_text(self) -> None:
        """Test that non-empty term doesn't match empty text."""
        assert exact_match("hello", "") is False


class TestWildcardMatch:
    """Tests for wildcard_match function (substring matching)."""

    def test_exact_substring_found(self) -> None:
        """Test that exact substring is found in text."""
        assert wildcard_match("hello", "hello world") is True

    def test_substring_not_found(self) -> None:
        """Test that non-matching term returns False."""
        assert wildcard_match("goodbye", "hello world") is False

    def test_case_insensitive(self) -> None:
        """Test that matching is case insensitive."""
        assert wildcard_match("HELLO", "hello world") is True
        assert wildcard_match("hello", "HELLO WORLD") is True

    def test_partial_word_match(self) -> None:
        """Test that partial word match is found (substring match)."""
        assert wildcard_match("hell", "hello world") is True
        assert wildcard_match("brain", "brainwave") is True
        assert wildcard_match("run", "running") is True

    def test_substring_in_middle(self) -> None:
        """Test substring in middle of word."""
        assert wildcard_match("ell", "hello world") is True
        assert wildcard_match("orl", "hello world") is True

    def test_empty_term(self) -> None:
        """Test that empty term matches (empty string is in all strings)."""
        assert wildcard_match("", "hello world") is True

    def test_empty_text(self) -> None:
        """Test that non-empty term doesn't match empty text."""
        assert wildcard_match("hello", "") is False


class TestStemmedMatch:
    """Tests for stemmed_match function."""

    def test_exact_word_found(self) -> None:
        """Test that exact word is found."""
        assert stemmed_match("run", "I like to run every day") is True

    def test_stemmed_variant_found(self) -> None:
        """Test that stemmed variants are matched (running -> run)."""
        assert stemmed_match("running", "I like to run every day") is True

    def test_reverse_stemming(self) -> None:
        """Test that search term is also stemmed (run matches running)."""
        assert stemmed_match("run", "I was running yesterday") is True

    def test_no_match(self) -> None:
        """Test that non-matching term returns False."""
        assert stemmed_match("swim", "I like to run every day") is False

    def test_case_insensitive(self) -> None:
        """Test that stemming is case insensitive."""
        assert stemmed_match("RUNNING", "i like to run") is True

    def test_multi_word_term_any_match(self) -> None:
        """Test that multi-word term matches if ANY word is found."""
        assert stemmed_match("running swimming", "I like to run") is True

    def test_multi_word_term_all_missing(self) -> None:
        """Test that multi-word term fails if NO words are found."""
        assert stemmed_match("flying swimming", "I like to run") is False

    def test_multi_word_all_present(self) -> None:
        """Test that multi-word term matches when all words present."""
        assert stemmed_match("running jogging", "I run and jog daily") is True

    def test_plural_to_singular(self) -> None:
        """Test that plurals are stemmed to singulars."""
        assert stemmed_match("dogs", "I have a dog") is True
        assert stemmed_match("dog", "I have dogs") is True

    def test_possessives_stripped(self) -> None:
        """Test that possessives are tokenized correctly (patient's -> patient)."""
        assert stemmed_match("patient", "The patient's medication") is True
        assert stemmed_match("patient", "patient's records show") is True

    def test_verb_conjugations(self) -> None:
        """Test that verb conjugations are matched."""
        assert stemmed_match("walked", "I walk every day") is True
        assert stemmed_match("walks", "I walked yesterday") is True


class TestFuzzyMatch:
    """Tests for fuzzy_match function."""

    def test_exact_match(self) -> None:
        """Test that exact word matches with high score."""
        assert fuzzy_match("hello", "hello world") is True

    def test_close_match(self) -> None:
        """Test that close spelling matches (typo tolerance)."""
        assert fuzzy_match("helo", "hello world") is True

    def test_no_match(self) -> None:
        """Test that very different words don't match."""
        assert fuzzy_match("xyz", "hello world") is False

    def test_case_insensitive(self) -> None:
        """Test that fuzzy match is case insensitive."""
        assert fuzzy_match("HELLO", "hello world") is True

    def test_multi_word_term_any_match(self) -> None:
        """Test that multi-word term matches if ANY word fuzzy-matches."""
        assert fuzzy_match("helo goodbye", "hello world") is True

    def test_multi_word_term_all_missing(self) -> None:
        """Test that multi-word term fails if NO words match."""
        assert fuzzy_match("abc xyz", "hello world") is False

    def test_custom_threshold(self) -> None:
        """Test that custom threshold affects matching."""
        # With very high threshold, only exact matches work
        assert fuzzy_match("helo", "hello world", threshold=100) is False
        assert fuzzy_match("hello", "hello world", threshold=100) is True

    def test_low_threshold(self) -> None:
        """Test that low threshold allows more matches."""
        # "helo" vs "hello" has ~89% similarity, so threshold=70 should match
        assert fuzzy_match("helo", "hello world", threshold=70) is True

    def test_empty_text(self) -> None:
        """Test behavior with empty text."""
        assert fuzzy_match("hello", "") is False


class TestTermMatchesSingle:
    """Tests for term_matches_single function."""

    def test_exact_method(self) -> None:
        """Test exact method routing."""
        assert term_matches_single("hello", "hello world", "exact") is True
        assert term_matches_single("goodbye", "hello world", "exact") is False

    def test_stemmed_method(self) -> None:
        """Test stemmed method routing."""
        assert term_matches_single("running", "I run daily", "stemmed") is True

    def test_fuzzy_method(self) -> None:
        """Test fuzzy method routing."""
        assert term_matches_single("helo", "hello world", "fuzzy") is True

    def test_wildcard_method(self) -> None:
        """Test wildcard method routing (substring match)."""
        assert term_matches_single("hell", "hello world", "wildcard") is True
        assert term_matches_single("brain", "brainwave", "wildcard") is True
        assert term_matches_single("goodbye", "hello world", "wildcard") is False

    def test_semantic_only_always_false(self) -> None:
        """Test that semantic_only method always returns False."""
        assert term_matches_single("hello", "hello world", "semantic_only") is False

    def test_unknown_method_defaults_to_exact(self) -> None:
        """Test that unknown methods default to exact match."""
        assert term_matches_single("hello", "hello world", "unknown") is True


class TestTermMatches:
    """Tests for term_matches function with multiple methods."""

    def test_single_method_as_string(self) -> None:
        """Test backward compatibility with single method string."""
        assert term_matches("hello", "hello world", "exact") is True

    def test_single_method_as_list(self) -> None:
        """Test single method in list format."""
        assert term_matches("hello", "hello world", ["exact"]) is True

    def test_multiple_methods_first_matches(self) -> None:
        """Test that matching succeeds if first method matches."""
        assert term_matches("hello", "hello world", ["exact", "stemmed"]) is True

    def test_multiple_methods_second_matches(self) -> None:
        """Test that matching succeeds if second method matches."""
        # "runing" doesn't exact match "running" but stemmed matches
        assert term_matches("run", "I was running", ["exact", "stemmed"]) is True

    def test_multiple_methods_none_match(self) -> None:
        """Test that matching fails if no methods match."""
        assert term_matches("xyz", "hello world", ["exact", "stemmed"]) is False

    def test_semantic_only_skipped(self) -> None:
        """Test that semantic_only is effectively skipped but others work."""
        assert term_matches("hello", "hello world", ["semantic_only", "exact"]) is True

    def test_only_semantic_returns_false(self) -> None:
        """Test that only semantic_only method returns False."""
        assert term_matches("hello", "hello world", ["semantic_only"]) is False

    def test_hybrid_search_scenario(self) -> None:
        """Test realistic hybrid search with multiple methods."""
        # Simulates keyword + analyzer + fuzzy all active
        assert term_matches("running", "I run daily", ["exact", "stemmed", "fuzzy"]) is True


class TestCheckTermsInChunks:
    """Tests for check_terms_in_chunks function."""

    def test_basic_term_matching(self) -> None:
        """Test basic term matching in chunks."""
        chunk_lookup = {
            "chunk1": "The patient has cancer",
            "chunk2": "Treatment options discussed",
            "chunk3": "Cancer diagnosis confirmed",
        }
        result = check_terms_in_chunks(
            chunk_ids=["chunk1", "chunk2", "chunk3"],
            chunk_lookup=chunk_lookup,
            search_term="cancer",
            acceptable_terms="patient, treatment",
        )
        assert result["chunks_with_search_term"] == 2  # chunk1, chunk3
        assert result["chunks_with_acceptable"] == 2  # chunk1 (patient), chunk2 (treatment)
        assert result["chunks_with_any_term"] == 3
        assert result["total_chunks_checked"] == 3

    def test_deduplication_search_term_in_acceptable(self) -> None:
        """Test that search term is removed from acceptable list."""
        chunk_lookup = {"chunk1": "cancer cells"}
        result = check_terms_in_chunks(
            chunk_ids=["chunk1"],
            chunk_lookup=chunk_lookup,
            search_term="cancer",
            acceptable_terms="cancer, treatment",  # cancer should be ignored
        )
        assert result["chunks_with_search_term"] == 1
        assert result["chunks_with_acceptable"] == 0  # treatment not in text
        assert result["chunks_with_any_term"] == 1

    def test_empty_chunk_lookup(self) -> None:
        """Test handling of missing chunks in lookup."""
        result = check_terms_in_chunks(
            chunk_ids=["chunk1", "chunk2"],
            chunk_lookup={},  # Empty lookup
            search_term="cancer",
            acceptable_terms="",
        )
        assert result["chunks_with_search_term"] == 0
        assert result["chunks_with_any_term"] == 0
        assert result["total_chunks_checked"] == 2

    def test_empty_term_lists(self) -> None:
        """Test handling of empty acceptable terms."""
        chunk_lookup = {"chunk1": "cancer treatment"}
        result = check_terms_in_chunks(
            chunk_ids=["chunk1"],
            chunk_lookup=chunk_lookup,
            search_term="cancer",
            acceptable_terms="",
        )
        assert result["chunks_with_search_term"] == 1
        assert result["chunks_with_acceptable"] == 0

    def test_stemmed_method(self) -> None:
        """Test check_terms_in_chunks with stemmed matching."""
        chunk_lookup = {"chunk1": "The patient is running tests"}
        result = check_terms_in_chunks(
            chunk_ids=["chunk1"],
            chunk_lookup=chunk_lookup,
            search_term="run",
            acceptable_terms="",
            match_methods="stemmed",
        )
        assert result["chunks_with_search_term"] == 1

    def test_fuzzy_method(self) -> None:
        """Test check_terms_in_chunks with fuzzy matching."""
        chunk_lookup = {"chunk1": "cancer diagnosis"}
        result = check_terms_in_chunks(
            chunk_ids=["chunk1"],
            chunk_lookup=chunk_lookup,
            search_term="cancr",  # typo
            acceptable_terms="",
            match_methods="fuzzy",
        )
        assert result["chunks_with_search_term"] == 1

    def test_multiple_methods_hybrid(self) -> None:
        """Test check_terms_in_chunks with multiple methods (hybrid search)."""
        chunk_lookup = {"chunk1": "running analysis"}
        result = check_terms_in_chunks(
            chunk_ids=["chunk1"],
            chunk_lookup=chunk_lookup,
            search_term="run",  # matches via stemmed
            acceptable_terms="",
            match_methods=["exact", "stemmed", "fuzzy"],
        )
        assert result["chunks_with_search_term"] == 1

    def test_whitespace_in_terms(self) -> None:
        """Test that whitespace in term lists is handled correctly."""
        chunk_lookup = {"chunk1": "cancer treatment"}
        result = check_terms_in_chunks(
            chunk_ids=["chunk1"],
            chunk_lookup=chunk_lookup,
            search_term="  cancer  ",
            acceptable_terms="  treatment  ,  therapy  ",
        )
        assert result["chunks_with_search_term"] == 1
        assert result["chunks_with_acceptable"] == 1

    def test_case_insensitive_terms(self) -> None:
        """Test that term matching is case insensitive."""
        chunk_lookup = {"chunk1": "CANCER TREATMENT"}
        result = check_terms_in_chunks(
            chunk_ids=["chunk1"],
            chunk_lookup=chunk_lookup,
            search_term="Cancer",
            acceptable_terms="treatment",
        )
        assert result["chunks_with_search_term"] == 1
        assert result["chunks_with_acceptable"] == 1

    def test_no_chunks(self) -> None:
        """Test handling of empty chunk list."""
        result = check_terms_in_chunks(
            chunk_ids=[],
            chunk_lookup={"chunk1": "cancer"},
            search_term="cancer",
            acceptable_terms="",
        )
        assert result["chunks_with_search_term"] == 0
        assert result["total_chunks_checked"] == 0
