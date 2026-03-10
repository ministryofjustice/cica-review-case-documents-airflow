"""Unit tests for term_matching module."""

from evaluation_suite.search_evaluation.term_matching import (
    check_terms_in_chunks,
    exact_match,
    fuzzy_match,
    stemmed_match,
    term_matches,
    term_matches_single,
    wildcard_match,
)

# --- Tests for exact_match ---


def test_exact_word_found():
    """Test that exact_match returns True when the exact word is found in the text."""
    assert exact_match("hello", "hello world") is True


def test_exact_word_not_found():
    """Test that exact_match returns False when the exact word is not found in the text."""
    assert exact_match("goodbye", "hello world") is False


def test_exact_case_insensitive():
    """Test that exact_match is case-insensitive."""
    assert exact_match("HELLO", "hello world") is True
    assert exact_match("hello", "HELLO WORLD") is True


def test_exact_partial_word_no_match():
    """Test that exact_match does not match partial words."""
    assert exact_match("hell", "hello world") is False
    assert exact_match("brain", "brainwave") is False
    assert exact_match("run", "running") is False


def test_exact_word_at_start():
    """Test that exact_match finds a word at the start of the text."""
    assert exact_match("hello", "hello there") is True


def test_exact_word_at_end():
    """Test that exact_match finds a word at the end of the text."""
    assert exact_match("world", "hello world") is True


def test_exact_word_with_punctuation():
    """Test that exact_match finds a word followed by punctuation."""
    assert exact_match("hello", "hello, world!") is True
    assert exact_match("world", "hello, world!") is True


def test_exact_empty_term():
    """Test that exact_match returns False when the search term is empty."""
    assert exact_match("", "hello world") is False


def test_exact_empty_text():
    """Test that exact_match returns False when the text is empty."""
    assert exact_match("hello", "") is False


# --- Tests for wildcard_match ---


def test_wildcard_exact_substring_found():
    """Test that wildcard_match returns True when the search term is a substring of the text."""
    assert wildcard_match("hello", "hello world") is True


def test_wildcard_substring_not_found():
    """Test that wildcard_match returns False when the search term is not a substring of the text."""
    assert wildcard_match("goodbye", "hello world") is False


def test_wildcard_case_insensitive():
    """Test that wildcard_match is case-insensitive."""
    assert wildcard_match("HELLO", "hello world") is True
    assert wildcard_match("hello", "HELLO WORLD") is True


def test_wildcard_partial_word_match():
    """Test that wildcard_match matches partial words."""
    assert wildcard_match("hell", "hello world") is True
    assert wildcard_match("brain", "brainwave") is True
    assert wildcard_match("run", "running") is True


def test_wildcard_substring_in_middle():
    """Test that wildcard_match finds a substring in the middle of the text."""
    assert wildcard_match("ell", "hello world") is True
    assert wildcard_match("orl", "hello world") is True


def test_wildcard_empty_term():
    """Test that wildcard_match returns True when the search term is empty."""
    assert wildcard_match("", "hello world") is True


def test_wildcard_empty_text():
    """Test that wildcard_match returns False when the text is empty."""
    assert wildcard_match("hello", "") is False


# --- Tests for stemmed_match ---


def test_stemmed_exact_word_found():
    """Test that stemmed_match returns True when the exact word is found in the text."""
    assert stemmed_match("run", "I like to run every day") is True


def test_stemmed_variant_found():
    """Test that stemmed_match returns True when a variant of the word is found in the text."""
    assert stemmed_match("running", "I like to run every day") is True


def test_stemmed_reverse_stemming():
    """Test that stemmed_match returns True when the text contains a variant of the search term."""
    assert stemmed_match("run", "I was running yesterday") is True


def test_stemmed_no_match():
    """Test that stemmed_match returns False when no variant of the search term is found."""
    assert stemmed_match("swim", "I like to run every day") is False


def test_stemmed_case_insensitive():
    """Test that stemmed_match is case-insensitive."""
    assert stemmed_match("RUNNING", "i like to run") is True


def test_stemmed_multi_word_term_any_match():
    """Test that stemmed_match returns True if any word in a multi-word term is found."""
    assert stemmed_match("running swimming", "I like to run") is True


def test_stemmed_multi_word_term_all_missing():
    """Test that stemmed_match returns False if all words in a multi-word term are missing."""
    assert stemmed_match("flying swimming", "I like to run") is False


def test_stemmed_multi_word_all_present():
    """Test that stemmed_match returns True if all words in a multi-word term are present."""
    assert stemmed_match("running jogging", "I run and jog daily") is True


def test_stemmed_plural_to_singular():
    """Test that stemmed_match handles plural to singular conversions."""
    assert stemmed_match("dogs", "I have a dog") is True
    assert stemmed_match("dog", "I have dogs") is True


def test_stemmed_possessives_stripped():
    """Test that stemmed_match handles possessive forms."""
    assert stemmed_match("patient", "The patient's medication") is True
    assert stemmed_match("patient", "patient's records show") is True


def test_stemmed_verb_conjugations():
    """Test that stemmed_match handles different verb conjugations."""
    assert stemmed_match("walked", "I walk every day") is True
    assert stemmed_match("walks", "I walked yesterday") is True


# --- Tests for fuzzy_match ---


def test_fuzzy_exact_match():
    """Test that fuzzy_match returns True for an exact match."""
    assert fuzzy_match("hello", "hello world") is True


def test_fuzzy_close_match():
    """Test that fuzzy_match returns True for a close match."""
    assert fuzzy_match("helo", "hello world") is True


def test_fuzzy_no_match():
    """Test that fuzzy_match returns False when there is no match."""
    assert fuzzy_match("xyz", "hello world") is False


def test_fuzzy_case_insensitive():
    """Test that fuzzy_match is case-insensitive."""
    assert fuzzy_match("HELLO", "hello world") is True


def test_fuzzy_multi_word_term_all_missing():
    """Test that fuzzy_match returns False if all words in a multi-word term are missing."""
    assert fuzzy_match("abc xyz", "hello world") is False


def test_fuzzy_custom_threshold():
    """Test that fuzzy_match respects a custom threshold."""
    assert fuzzy_match("helo", "hello world", threshold=100) is False
    assert fuzzy_match("hello", "hello world", threshold=100) is True


def test_fuzzy_low_threshold():
    """Test that fuzzy_match returns True for a low threshold."""
    assert fuzzy_match("helo", "hello world", threshold=70) is True


def test_fuzzy_empty_text():
    """Test that fuzzy_match returns False for an empty text."""
    assert fuzzy_match("hello", "") is False


def test_fuzzy_hyphenated_term_matches_spaced_text():
    """Test that fuzzy_match matches hyphenated terms with spaced text."""
    assert fuzzy_match("neuro-psychologist", "The neuro psychologist reviewed the case") is True


def test_fuzzy_spaced_term_matches_hyphenated_text():
    """Test that fuzzy_match matches spaced terms with hyphenated text."""
    assert fuzzy_match("neuro psychologist", "The neuro-psychologist reviewed the case") is True


def test_fuzzy_partial_match_in_longer_text():
    """Test that fuzzy_match matches partial terms in longer text."""
    assert fuzzy_match("psychologist", "The neuro-psychologist was consulted") is True


# --- Tests for term_matches_single ---


def test_term_matches_single_exact_method():
    """Test that term_matches_single returns True for an exact match."""
    assert term_matches_single("hello", "hello world", "exact") is True
    assert term_matches_single("goodbye", "hello world", "exact") is False


def test_term_matches_single_stemmed_method():
    """Test that term_matches_single returns True for a stemmed match."""
    assert term_matches_single("running", "I run daily", "stemmed") is True


def test_term_matches_single_fuzzy_method():
    """Test that term_matches_single returns True for a fuzzy match."""
    assert term_matches_single("helo", "hello world", "fuzzy") is True


def test_term_matches_single_wildcard_method():
    """Test that term_matches_single returns True for a wildcard match."""
    assert term_matches_single("hell", "hello world", "wildcard") is True
    assert term_matches_single("brain", "brainwave", "wildcard") is True
    assert term_matches_single("goodbye", "hello world", "wildcard") is False


def test_term_matches_single_semantic_only_always_false():
    """Test that term_matches_single returns False for semantic_only method."""
    assert term_matches_single("hello", "hello world", "semantic_only") is False


def test_term_matches_single_unknown_method_defaults_to_exact():
    """Test that term_matches_single defaults to exact match for unknown method."""
    assert term_matches_single("hello", "hello world", "unknown") is True


# --- Tests for term_matches ---


def test_term_matches_single_method_as_string():
    """Test that term_matches returns True for a single method as a string."""
    assert term_matches("hello", "hello world", "exact") is True


def test_term_matches_single_method_as_list():
    """Test that term_matches returns True for a single method as a list."""
    assert term_matches("hello", "hello world", ["exact"]) is True


def test_term_matches_multiple_methods_first_matches():
    """Test that term_matches returns True if the first method matches."""
    assert term_matches("hello", "hello world", ["exact", "stemmed"]) is True


def test_term_matches_multiple_methods_second_matches():
    """Test that term_matches returns True if the second method matches."""
    assert term_matches("run", "I was running", ["exact", "stemmed"]) is True


def test_term_matches_multiple_methods_none_match():
    """Test that term_matches returns False if none of the methods match."""
    assert term_matches("xyz", "hello world", ["exact", "stemmed"]) is False


def test_term_matches_semantic_only_skipped():
    """Test that term_matches skips semantic_only method if other methods are present."""
    assert term_matches("hello", "hello world", ["semantic_only", "exact"]) is True


def test_term_matches_only_semantic_returns_false():
    """Test that term_matches returns False if only semantic_only method is provided."""
    assert term_matches("hello", "hello world", ["semantic_only"]) is False


def test_term_matches_hybrid_search_scenario():
    """Test that term_matches works correctly in a hybrid search scenario."""
    assert term_matches("running", "I run daily", ["exact", "stemmed", "fuzzy"]) is True


# --- Tests for check_terms_in_chunks ---


def test_check_terms_in_chunks_basic_term_matching():
    """Test that check_terms_in_chunks correctly counts chunks with search and acceptable terms."""
    chunk_lookup = {
        "chunk1": "The claimant suffered a fractured arm",
        "chunk2": "Bruising was observed on the left leg",
        "chunk3": "No visible injuries were present",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2", "chunk3"],
        chunk_lookup=chunk_lookup,
        search_term="fractured",
        acceptable_terms="bruising, injuries",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 2
    assert result["chunks_with_any_term"] == 3
    assert result["total_chunks_checked"] == 3


def test_check_terms_in_chunks_deduplication_search_term_in_acceptable():
    """Test that check_terms_in_chunks correctly handles deduplication when search term is in acceptable terms."""
    chunk_lookup = {"chunk1": "fracture of the wrist"}
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="fracture",
        acceptable_terms="fracture, bruise",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 0
    assert result["chunks_with_any_term"] == 1


def test_check_terms_in_chunks_empty_chunk_lookup():
    """Test that check_terms_in_chunks handles empty chunk lookup correctly."""
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2"],
        chunk_lookup={},
        search_term="fracture",
        acceptable_terms="",
    )
    assert result["chunks_with_search_term"] == 0
    assert result["chunks_with_any_term"] == 0
    assert result["total_chunks_checked"] == 2


def test_check_terms_in_chunks_empty_term_lists():
    """Test that check_terms_in_chunks handles empty term lists correctly."""
    chunk_lookup = {"chunk1": "fracture and swelling"}
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="fracture",
        acceptable_terms="",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 0


def test_check_terms_in_chunks_stemmed_method():
    """Test that check_terms_in_chunks correctly handles stemmed match method."""
    chunk_lookup = {"chunk1": "The claimant is running from danger"}
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="run",
        acceptable_terms="",
        match_methods="stemmed",
    )
    assert result["chunks_with_search_term"] == 1


def test_check_terms_in_chunks_fuzzy_method():
    """Test that check_terms_in_chunks correctly handles fuzzy match method."""
    chunk_lookup = {"chunk1": "fracture diagnosis"}
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="frakture",
        acceptable_terms="",
        match_methods="fuzzy",
    )
    assert result["chunks_with_search_term"] == 1


def test_check_terms_in_chunks_multiple_methods_hybrid():
    """Test that check_terms_in_chunks correctly handles multiple match methods."""
    chunk_lookup = {"chunk1": "running analysis"}
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="run",
        acceptable_terms="",
        match_methods=["exact", "stemmed", "fuzzy"],
    )
    assert result["chunks_with_search_term"] == 1


def test_check_terms_in_chunks_whitespace_in_terms():
    """Test that check_terms_in_chunks correctly handles terms with leading/trailing whitespace."""
    chunk_lookup = {"chunk1": "fracture and swelling"}
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="  fracture  ",
        acceptable_terms="  swelling  ,  bruise  ",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 1


def test_check_terms_in_chunks_case_insensitive_terms():
    """Test that check_terms_in_chunks correctly handles case-insensitive terms."""
    chunk_lookup = {"chunk1": "FRACTURE AND SWELLING"}
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="Fracture",
        acceptable_terms="swelling",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 1


def test_check_terms_in_chunks_no_chunks():
    """Test that check_terms_in_chunks handles no chunks correctly."""
    result = check_terms_in_chunks(
        chunk_ids=[],
        chunk_lookup={"chunk1": "fracture"},
        search_term="fracture",
        acceptable_terms="",
    )
    assert result["chunks_with_search_term"] == 0
    assert result["total_chunks_checked"] == 0


def test_check_terms_in_chunks_injury_term_matching():
    """Test that check_terms_in_chunks correctly counts chunks with injury-related terms."""
    chunk_lookup = {
        "chunk1": "The claimant suffered a fractured arm",
        "chunk2": "Bruising was observed on the left leg",
        "chunk3": "No visible injuries were present",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2", "chunk3"],
        chunk_lookup=chunk_lookup,
        search_term="fractured",
        acceptable_terms="bruising, injuries",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 2
    assert result["chunks_with_any_term"] == 3
    assert result["total_chunks_checked"] == 3


def test_check_terms_in_chunks_synonym_in_acceptable_terms():
    """Test that check_terms_in_chunks correctly handles synonyms in acceptable terms."""
    chunk_lookup = {
        "chunk1": "The patient sustained a laceration to the cheek",
        "chunk2": "There was a cut on the forehead",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2"],
        chunk_lookup=chunk_lookup,
        search_term="laceration",
        acceptable_terms="cut, wound",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 1
    assert result["chunks_with_any_term"] == 2


def test_check_terms_in_chunks_multiple_acceptable_terms_some_missing():
    """Test that check_terms_in_chunks correctly handles multiple acceptable terms when some are missing."""
    chunk_lookup = {
        "chunk1": "Swelling was noted",
        "chunk2": "No evidence of concussion",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2"],
        chunk_lookup=chunk_lookup,
        search_term="fracture",
        acceptable_terms="swelling, concussion, abrasion",
    )
    assert result["chunks_with_search_term"] == 0
    assert result["chunks_with_acceptable"] == 2
    assert result["chunks_with_any_term"] == 2


def test_check_terms_in_chunks_stop_words_are_ignored():
    """Test that check_terms_in_chunks correctly ignores stop words."""
    chunk_lookup = {
        "chunk1": "The injury was severe",
        "chunk2": "He had a minor injury",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2"],
        chunk_lookup=chunk_lookup,
        search_term="the injury",
        acceptable_terms="a injury, minor",
    )
    assert result["chunks_with_search_term"] == 2
    assert result["chunks_with_acceptable"] == 2
    assert result["chunks_with_any_term"] == 2


def test_check_terms_in_chunks_punctuation_and_possessives():
    """Test that check_terms_in_chunks correctly handles punctuation and possessives."""
    chunk_lookup = {
        "chunk1": "The victim's statement was recorded",
        "chunk2": "Victims injuries were documented",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2"],
        chunk_lookup=chunk_lookup,
        search_term="victim",
        acceptable_terms="victim's, victims",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 2
    assert result["chunks_with_any_term"] == 2


def test_check_terms_in_chunks_term_not_found():
    """Test that check_terms_in_chunks correctly handles terms not found in any chunk."""
    chunk_lookup = {
        "chunk1": "No abnormalities detected",
        "chunk2": "Patient is in good health",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1", "chunk2"],
        chunk_lookup=chunk_lookup,
        search_term="fracture",
        acceptable_terms="bruise, laceration",
    )
    assert result["chunks_with_search_term"] == 0
    assert result["chunks_with_acceptable"] == 0
    assert result["chunks_with_any_term"] == 0
    assert result["total_chunks_checked"] == 2


def test_check_terms_in_chunks_chunk_with_multiple_terms():
    """Test that check_terms_in_chunks correctly handles chunks with multiple terms."""
    chunk_lookup = {
        "chunk1": "The claimant had a fracture and bruising",
    }
    result = check_terms_in_chunks(
        chunk_ids=["chunk1"],
        chunk_lookup=chunk_lookup,
        search_term="fracture",
        acceptable_terms="bruise, claimant",
    )
    assert result["chunks_with_search_term"] == 1
    assert result["chunks_with_acceptable"] == 1
    assert result["chunks_with_any_term"] == 1
    assert result["total_chunks_checked"] == 1
