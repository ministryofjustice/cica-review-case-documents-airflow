"""Unit tests for search_type_config.py."""

import pytest

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.query.search_type_config import (
    DEFAULT_SEARCH_TYPE,
    IMPLEMENTED_SEARCH_TYPES,
    SEARCH_TYPE_VALUES,
    QueryDslConfig,
    SearchType,
    resolve_search_type,
)

# --- SearchType / constants ---


def test_search_type_values_match_frontend():
    """The search type values match the frontend SEARCH_TYPES enum."""
    assert SEARCH_TYPE_VALUES == {
        "hybrid-dates",
        "keyword-dates",
        "hybrid",
        "keyword",
        "semantic",
    }


def test_default_search_type_is_hybrid_dates():
    """The default mirrors the frontend DEFAULT_SEARCH_TYPE."""
    assert DEFAULT_SEARCH_TYPE == SearchType.HYBRID_DATES


def test_implemented_types_are_hybrid_and_hybrid_dates():
    """Only hybrid and hybrid-dates are implemented at this stage."""
    assert IMPLEMENTED_SEARCH_TYPES == {SearchType.HYBRID, SearchType.HYBRID_DATES}


# --- resolve_search_type ---


@pytest.mark.parametrize(
    "value",
    ["hybrid", "hybrid-dates", "keyword", "keyword-dates", "semantic"],
)
def test_resolve_search_type_returns_known_values(value):
    """A known search type is returned unchanged."""
    assert resolve_search_type(value) == value


def test_resolve_search_type_trims_and_lowercases():
    """Whitespace is trimmed and case is normalised."""
    assert resolve_search_type("  HYBRID  ") == SearchType.HYBRID


@pytest.mark.parametrize("value", [None, "", "   ", 123, [], "not-a-type"])
def test_resolve_search_type_falls_back_to_default(value):
    """Unusable or unknown values fall back to the default."""
    assert resolve_search_type(value) == DEFAULT_SEARCH_TYPE


def test_resolve_search_type_uses_session_feature_flag_fallback():
    """An unknown value falls back to a valid session feature flag."""
    session = {"featureFlags": {"type": "keyword"}}
    assert resolve_search_type("nonsense", session=session) == SearchType.KEYWORD


def test_resolve_search_type_ignores_invalid_session_feature_flag():
    """An invalid session feature flag is ignored in favour of the default."""
    session = {"featureFlags": {"type": "bogus"}}
    assert resolve_search_type("nonsense", session=session) == DEFAULT_SEARCH_TYPE


# --- QueryDslConfig ---


def test_query_dsl_config_defaults_match_frontend():
    """The default config matches the frontend DEFAULT_QUERY_DSL_CONFIG boosts."""
    config = QueryDslConfig()
    assert config.lexical_boost == 20.0
    assert config.neural_boost == 4.0
    assert config.date_boost == 4.0
    assert config.min_score == 0.0


def test_query_dsl_config_from_settings_reads_evaluation_settings():
    """from_settings sources boosts from evaluation_settings (for optimization)."""
    config = QueryDslConfig.from_settings()
    assert config.lexical_boost == eval_settings.KEYWORD_BOOST
    assert config.neural_boost == eval_settings.SEMANTIC_BOOST
    assert config.date_boost == eval_settings.DATE_QUERY_BOOST
    assert config.min_score == eval_settings.MIN_SCORE
