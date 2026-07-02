"""Unit tests for the synonym_generator module.

These tests use a stub :class:`SynonymProvider` so the heavy scispaCy model is
never loaded; the scispaCy-backed provider is exercised only for its pure
helper functions and its graceful-degradation behaviour.
"""

from evaluation_suite.search_evaluation.relevance import synonym_generator
from evaluation_suite.search_evaluation.relevance.synonym_generator import (
    SciSpacySynonymProvider,
    generate_acceptable_terms,
    set_default_provider,
)


class _StubProvider:
    """Returns a fixed, sliceable list of synonyms regardless of query."""

    def __init__(self, terms: list[str]) -> None:
        self._terms = terms
        self.calls: list[tuple[str, int]] = []

    def synonyms(self, query: str, top_n: int) -> list[str]:
        self.calls.append((query, top_n))
        return self._terms[:top_n]


class _RaisingProvider:
    def synonyms(self, query: str, top_n: int) -> list[str]:
        raise RuntimeError("boom")


class TestGenerateAcceptableTerms:
    def test_uses_injected_provider(self):
        stub = _StubProvider(["unconsciousness", "stupor", "comatose"])
        result = generate_acceptable_terms("coma", top_n=3, provider=stub)
        assert result == "unconsciousness, stupor, comatose"
        assert stub.calls == [("coma", 3)]

    def test_respects_top_n(self):
        stub = _StubProvider(["a", "b", "c", "d"])
        result = generate_acceptable_terms("query", top_n=2, provider=stub)
        assert result == "a, b"

    def test_empty_synonyms_returns_empty_string(self):
        result = generate_acceptable_terms("query", provider=_StubProvider([]))
        assert result == ""

    def test_provider_exception_is_swallowed(self):
        # A failing provider must never break the evaluation run.
        result = generate_acceptable_terms("query", provider=_RaisingProvider())
        assert result == ""

    def test_set_default_provider(self):
        original = synonym_generator._default_provider
        try:
            set_default_provider(_StubProvider(["x", "y"]))
            assert generate_acceptable_terms("anything", top_n=5) == "x, y"
        finally:
            set_default_provider(original)


class TestIsReasonableWord:
    def test_accepts_normal_words(self):
        assert synonym_generator._is_reasonable_word("comatose")
        assert synonym_generator._is_reasonable_word("brain-injury")

    def test_rejects_too_short(self):
        assert not synonym_generator._is_reasonable_word("ab")

    def test_rejects_no_vowel(self):
        assert not synonym_generator._is_reasonable_word("fjwtk")

    def test_rejects_repeated_chars(self):
        assert not synonym_generator._is_reasonable_word("aaab")

    def test_rejects_non_alpha(self):
        assert not synonym_generator._is_reasonable_word("co3ma")


class TestContentWords:
    def test_filters_stop_words_and_short_tokens(self):
        words = synonym_generator._content_words("Was the applicant in a coma?")
        assert "coma" in words
        assert "applicant" in words
        assert "the" not in words
        assert "was" not in words


class TestSciSpacyGracefulDegradation:
    def test_missing_model_returns_empty(self):
        # Point at a non-existent model name; provider must degrade to [].
        provider = SciSpacySynonymProvider(model_name="definitely_not_a_real_model_xyz")
        assert provider.synonyms("coma", top_n=5) == []
        # Second call uses the cached failure path and still returns [].
        assert provider.synonyms("assault", top_n=5) == []
