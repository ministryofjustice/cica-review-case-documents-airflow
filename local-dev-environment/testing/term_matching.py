"""Term matching utilities for relevance scoring.

This module provides different matching strategies to align with OpenSearch
search types:
- exact: Word boundary matching (keyword search) - term must appear as whole word(s)
- wildcard: Substring matching (wildcard search) - term can appear anywhere
- stemmed: Snowball stemmer matching (English analyzer search)
- fuzzy: Approximate string matching (fuzzy search)
- semantic_only: Returns False (semantic search - term matching not applicable)
"""

import re

import snowballstemmer
from rapidfuzz import fuzz

# Import module to access settings dynamically (supports runtime overrides)
from testing import evaluation_settings as settings

# Initialize stemmer for English (matches OpenSearch's English analyzer)
_stemmer = snowballstemmer.stemmer("english")


def exact_match(term: str, text: str) -> bool:
    """Check if term appears as whole word(s) in text using word boundaries.

    This matches OpenSearch keyword search behavior where tokenized terms
    must match tokenized text. For multi-word terms, matches if ANY word
    in the term is found as a whole word.
    """
    term_words = re.findall(r"\b\w+\b", term.lower())
    text_lower = text.lower()

    # Match if ANY term word appears as a whole word in text
    for tw in term_words:
        # Use word boundary regex to match whole words only
        if re.search(rf"\b{re.escape(tw)}\b", text_lower):
            return True
    return False


def wildcard_match(term: str, text: str) -> bool:
    """Check if term appears as substring anywhere in text.

    This matches OpenSearch wildcard search behavior (*term*) where
    the term can appear anywhere, including within other words.
    """
    return term.lower() in text.lower()


def stemmed_match(term: str, text: str) -> bool:
    """Check if stemmed term appears in stemmed text.

    Uses Snowball English stemmer to match OpenSearch's English analyzer behavior.
    Tokenizes on word boundaries (strips punctuation like possessives) before stemming.
    For multi-word terms, matches if ANY word in the term is found (stemmed).
    """
    # Tokenize: extract alphanumeric words, stripping punctuation
    term_words = re.findall(r"\b\w+\b", term.lower())
    text_words = re.findall(r"\b\w+\b", text.lower())
    stemmed_text = [_stemmer.stemWord(w) for w in text_words]

    # Match if ANY term word is found in text (OR logic)
    for tw in term_words:
        if _stemmer.stemWord(tw) in stemmed_text:
            return True
    return False


def fuzzy_match(term: str, text: str, threshold: int | None = None) -> bool:
    """Check if term fuzzy-matches any word in text.

    Uses rapidfuzz to find approximate matches. Handles both single words
    and hyphenated/multi-word terms by checking:
    1. Word-to-word matching for individual term words
    2. Partial ratio for the full term (handles hyphenated terms like "neuro-psychologist")

    Args:
        term: The term to search for.
        text: The text to search in.
        threshold: Similarity threshold (0-100). Uses FUZZY_MATCH_THRESHOLD if None.

    Returns:
        True if term fuzzy-matches, False otherwise.
    """
    if threshold is None:
        threshold = settings.FUZZY_MATCH_THRESHOLD

    term_lower = term.lower()
    text_lower = text.lower()

    # First, check if the full term fuzzy-matches anywhere in the text
    # This handles hyphenated terms like "neuro-psychologist" matching "neuro psychologist"
    if fuzz.partial_ratio(term_lower, text_lower) >= threshold:
        return True

    # Fall back to word-by-word matching for multi-word terms
    term_words = term_lower.split()
    text_words = text_lower.split()

    # Match if ANY term word fuzzy-matches any text word (OR logic)
    for tw in term_words:
        for word in text_words:
            if fuzz.ratio(tw, word) >= threshold:
                return True
    return False


def term_matches_single(term: str, text: str, method: str) -> bool:
    """Check if term matches text using a single specified method.

    Args:
        term: The term to search for.
        text: The text to search in.
        method: One of 'exact', 'wildcard', 'stemmed', 'fuzzy', or 'semantic_only'.

    Returns:
        True if term matches, False otherwise.
        Always returns False for 'semantic_only' method.
    """
    if method == "semantic_only":
        return False
    if method == "fuzzy":
        return fuzzy_match(term, text)
    if method == "stemmed":
        return stemmed_match(term, text)
    if method == "wildcard":
        return wildcard_match(term, text)
    # 'exact' uses word boundary matching (keyword search)
    return exact_match(term, text)


def term_matches(term: str, text: str, methods: str | list[str]) -> bool:
    """Check if term matches text using any of the specified methods.

    Args:
        term: The term to search for.
        text: The text to search in.
        methods: Single method string or list of methods.
                 Each method is one of 'exact', 'stemmed', 'fuzzy', or 'semantic_only'.

    Returns:
        True if term matches via ANY of the specified methods, False otherwise.
        'semantic_only' is skipped (cannot text-match semantic results).
    """
    # Handle single method string for backwards compatibility
    if isinstance(methods, str):
        methods = [methods]

    for method in methods:
        if term_matches_single(term, text, method):
            return True
    return False


def check_terms_in_chunks(
    chunk_ids: list[str],
    chunk_lookup: dict[str, str],
    search_term: str,
    acceptable_terms: str,
    match_methods: str | list[str] = "exact",
) -> dict[str, int]:
    """Check which terms are present in the returned chunk texts.

    Args:
        chunk_ids: List of chunk IDs returned from search.
        chunk_lookup: Dictionary mapping chunk_id to chunk_text.
        search_term: The primary search term.
        acceptable_terms: Comma-separated acceptable associated terms.
        match_methods: Single method or list of methods. Term matches if ANY method finds it.
                       Methods: 'exact', 'stemmed', 'fuzzy', or 'semantic_only'.

    Returns:
        Dictionary with counts and details of term matches.
        Note: acceptable_list excludes the search term to avoid double counting.
    """
    # Parse terms into lists
    search_term_lower = search_term.lower().strip()
    acceptable_list = [t.strip().lower() for t in acceptable_terms.split(",") if t.strip()]

    # Deduplicate: remove search term from acceptable
    acceptable_list = [t for t in acceptable_list if t != search_term_lower]

    chunks_with_search_term = 0
    chunks_with_acceptable = 0
    chunks_with_any_term = 0

    for chunk_id in chunk_ids:
        chunk_text = chunk_lookup.get(chunk_id, "")
        if not chunk_text:
            continue

        # Use the appropriate matching method(s) - matches if ANY method finds the term
        has_search_term = term_matches(search_term_lower, chunk_text, match_methods)
        has_acceptable = (
            any(term_matches(term, chunk_text, match_methods) for term in acceptable_list) if acceptable_list else False
        )

        if has_search_term:
            chunks_with_search_term += 1
        if has_acceptable:
            chunks_with_acceptable += 1
        if has_search_term or has_acceptable:
            chunks_with_any_term += 1

    return {
        "chunks_with_search_term": chunks_with_search_term,
        "chunks_with_acceptable": chunks_with_acceptable,
        "chunks_with_any_term": chunks_with_any_term,
        "total_chunks_checked": len(chunk_ids),
    }


def check_terms_by_expected_chunks(
    returned_chunk_ids: list[str],
    search_term: str,
    acceptable_terms: str,
    term_to_expected_chunks: dict[str, set[str]],
) -> dict[str, int]:
    """Check term relevance using expected chunk IDs from other search terms.

    This is used for semantic-only or hybrid search where text matching isn't
    meaningful. Instead, we check if any of the returned chunks are in the
    expected chunks for the acceptable terms.

    Args:
        returned_chunk_ids: List of chunk IDs returned from search.
        search_term: The primary search term.
        acceptable_terms: Comma-separated acceptable associated terms.
        term_to_expected_chunks: Dict mapping search terms to their expected chunk IDs.

    Returns:
        Dictionary with counts of chunks that overlap with expected chunks for each term type.
    """
    returned_set = set(returned_chunk_ids)
    search_term_lower = search_term.lower().strip()

    # Parse and deduplicate term lists
    acceptable_list = [t.strip().lower() for t in acceptable_terms.split(",") if t.strip()]
    acceptable_list = [t for t in acceptable_list if t != search_term_lower]

    # Get expected chunks for the search term itself
    search_term_expected = term_to_expected_chunks.get(search_term_lower, set())
    chunks_with_search_term = len(returned_set & search_term_expected)

    # Get expected chunks for acceptable terms
    acceptable_expected: set[str] = set()
    for term in acceptable_list:
        acceptable_expected.update(term_to_expected_chunks.get(term, set()))
    chunks_with_acceptable = len(returned_set & acceptable_expected)

    # Any term = union of all expected chunks
    all_expected = search_term_expected | acceptable_expected
    chunks_with_any_term = len(returned_set & all_expected)

    return {
        "chunks_with_search_term": chunks_with_search_term,
        "chunks_with_acceptable": chunks_with_acceptable,
        "chunks_with_any_term": chunks_with_any_term,
        "total_chunks_checked": len(returned_chunk_ids),
    }
