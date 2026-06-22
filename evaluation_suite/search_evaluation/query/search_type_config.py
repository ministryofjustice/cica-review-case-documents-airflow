"""Search type configuration mirroring the frontend hybrid search DSL.

This module defines the search types and query DSL configuration used by the
evaluation suite so that evaluation searches match what users experience in the
frontend.

Frontend reference (``api/search/constants/searchTypes.js`` and
``api/DAL/utils/buildQueryJson/``):
- ``searchTypes.js`` — the ``SEARCH_TYPES`` enum, ``DEFAULT_SEARCH_TYPE``, and
  the ``resolveSearchType`` helper.
- ``buildQueryJson/`` — the query DSL builders and their default boosts
  (lexical=20, date=4, neural=4).

Only ``hybrid`` and ``hybrid-dates`` are fully implemented at this stage. The
remaining types are defined so the plumbing is in place, but the query builder
raises ``NotImplementedError`` for them.
"""

from dataclasses import dataclass


class SearchType:
    """String constants for the supported search types.

    Values match the frontend ``SEARCH_TYPES`` enum exactly so that a search
    type chosen in the frontend maps directly onto an evaluation run.
    """

    HYBRID_DATES = "hybrid-dates"
    KEYWORD_DATES = "keyword-dates"
    HYBRID = "hybrid"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"


# All valid search type values (mirrors Object.freeze(SEARCH_TYPES) values).
SEARCH_TYPE_VALUES = frozenset(
    {
        SearchType.HYBRID_DATES,
        SearchType.KEYWORD_DATES,
        SearchType.HYBRID,
        SearchType.KEYWORD,
        SearchType.SEMANTIC,
    }
)

# Frontend DEFAULT_SEARCH_TYPE.
DEFAULT_SEARCH_TYPE = SearchType.HYBRID_DATES

# Search types whose query builder is fully implemented in this phase.
IMPLEMENTED_SEARCH_TYPES = frozenset({SearchType.HYBRID, SearchType.HYBRID_DATES})


@dataclass(frozen=True)
class QueryDslConfig:
    """Tunable query DSL parameters, mirroring the frontend ``queryDslConfig``.

    Defaults match the frontend ``DEFAULT_QUERY_DSL_CONFIG`` boosts so the
    evaluation reproduces the user experience. They can be overridden per run
    (e.g. by boost hyperparameter optimization) via :meth:`from_settings`, which
    sources values from ``evaluation_settings``.

    Attributes:
        lexical_boost: Boost applied to the keyword ``match`` clause (frontend
            ``lexicalBoost``, default 20).
        neural_boost: Boost applied to the vector ANN clause (frontend
            ``neuralBoost``, default 4).
        date_boost: Boost applied to the grouped date ``match_phrase`` clause (frontend
            ``dateBoost``, default 4).
        min_score: Optional OpenSearch ``min_score`` cut-off. 0 disables it so
            the evaluation can apply its own downstream score filtering.
    """

    lexical_boost: float = 20.0
    neural_boost: float = 4.0
    date_boost: float = 4.0
    min_score: float = 0.0

    @classmethod
    def from_settings(cls) -> "QueryDslConfig":
        """Build a config from the current ``evaluation_settings`` values.

        Reading from settings (rather than hard-coding) keeps boost
        hyperparameter optimization working: ``apply_overrides`` mutates the
        settings module and the next config picks the new values up.
        """
        # Imported lazily to avoid a circular import at module load time.
        from evaluation_suite.search_evaluation import evaluation_settings as eval_settings

        return cls(
            lexical_boost=eval_settings.KEYWORD_BOOST,
            neural_boost=eval_settings.SEMANTIC_BOOST,
            date_boost=eval_settings.DATE_QUERY_BOOST,
            min_score=eval_settings.MIN_SCORE,
        )


def resolve_search_type(value: str | None, session: dict | None = None) -> str:
    """Resolve a requested search type to a valid value, mirroring the frontend.

    Mirrors the frontend ``resolveSearchType`` helper:
    1. If ``value`` is not a usable non-empty string, return the default.
    2. Trim and lowercase it; if it is a known search type, use it.
    3. Otherwise fall back to ``session.featureFlags.type`` if that is valid.
    4. Otherwise return the default.

    Args:
        value: The requested search type (e.g. from a URL toggle).
        session: Optional session dict that may carry a ``featureFlags.type``
            fallback.

    Returns:
        A valid search type string.
    """
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_SEARCH_TYPE

    normalised = value.strip().lower()
    if normalised in SEARCH_TYPE_VALUES:
        return normalised

    feature_flag = (session or {}).get("featureFlags", {}).get("type")
    if isinstance(feature_flag, str) and feature_flag.strip().lower() in SEARCH_TYPE_VALUES:
        return feature_flag.strip().lower()

    return DEFAULT_SEARCH_TYPE
