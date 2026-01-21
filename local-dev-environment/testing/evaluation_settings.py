"""Evaluation settings - EDIT THIS FILE TO CONFIGURE SEARCH EVALUATION.

This is the single location to configure all search evaluation parameters.
Modify the values below to test different search configurations.

Run evaluation from local-dev-environment directory:
    python -m testing.run_evaluation

For programmatic override (e.g., optimization), use:
    from testing.evaluation_settings import apply_overrides, reset_settings
    apply_overrides({"KEYWORD_BOOST": 2.0, "K_QUERIES": 100})
    # ... run evaluation ...
    reset_settings()  # restore defaults
"""

# =============================================================================
# SEARCH TYPE BOOSTS
# =============================================================================
# Set boost to 0 to disable a search type, or >0 to enable and weight it.
# Higher boost = more weight in the combined search score.

KEYWORD_BOOST = 1.2  # Exact keyword matching
ANALYSER_BOOST = 3.9  # English analyzer (stemming, stopwords)
SEMANTIC_BOOST = 0.9  # Vector/embedding similarity search
FUZZY_BOOST = 3.9  # Fuzzy matching (typo tolerance)
WILDCARD_BOOST = 3.9  # Wildcard pattern matching

# =============================================================================
# SEARCH PARAMETERS
# =============================================================================

K_QUERIES = 40  # Number of results to retrieve per search
SCORE_FILTER = 0.57  # Minimum score threshold for initial results

# Additive semantic fallback - supplements initial results when too few
ADAPTIVE_SCORE_FILTER = False  # Enable/disable adaptive filtering
MIN_RESULTS_BEFORE_FALLBACK = 3  # Minimum results needed before lowering score filter
SEMANTIC_SCORE_FILTER = 0.5  # Threshold for semantic results (lower than keyword)
MAX_SEMANTIC_RESULTS = 10  # Maximum semantic results to add as supplement

# Fuzzy search settings
FUZZINESS = "Auto"  # "Auto", "0", "1", "2" - Auto chooses based on term length
MAX_EXPANSIONS = 50  # Maximum fuzzy term expansions
PREFIX_LENGTH = 2  # Number of initial characters that must match exactly

# =============================================================================
# TERM MATCHING SETTINGS
# =============================================================================
# These control how we verify if returned chunks contain search terms when a
# fuzzy match is conducted using rapidfuzz to simulate opensearch fuzzy matching.

FUZZY_MATCH_THRESHOLD = 85  # Similarity threshold for fuzzy term matching (0-100)

# =============================================================================
# DATE FORMAT DETECTION
# =============================================================================
# When enabled, dates in search terms are detected and searched using exact
# match_phrase queries with multiple format variants (e.g., "20-Jul-21" also
# searches for "20 July 2021", "20/07/2021", etc.)

DATE_FORMAT_DETECTION = True  # Enable/disable date format detection


# =============================================================================
# RUNTIME OVERRIDE SUPPORT
# =============================================================================
# Store default values for reset functionality
_DEFAULTS = {
    "KEYWORD_BOOST": KEYWORD_BOOST,
    "ANALYSER_BOOST": ANALYSER_BOOST,
    "SEMANTIC_BOOST": SEMANTIC_BOOST,
    "FUZZY_BOOST": FUZZY_BOOST,
    "WILDCARD_BOOST": WILDCARD_BOOST,
    "K_QUERIES": K_QUERIES,
    "SCORE_FILTER": SCORE_FILTER,
    "ADAPTIVE_SCORE_FILTER": ADAPTIVE_SCORE_FILTER,
    "MIN_RESULTS_BEFORE_FALLBACK": MIN_RESULTS_BEFORE_FALLBACK,
    "SEMANTIC_SCORE_FILTER": SEMANTIC_SCORE_FILTER,
    "MAX_SEMANTIC_RESULTS": MAX_SEMANTIC_RESULTS,
    "FUZZINESS": FUZZINESS,
    "MAX_EXPANSIONS": MAX_EXPANSIONS,
    "PREFIX_LENGTH": PREFIX_LENGTH,
    "FUZZY_MATCH_THRESHOLD": FUZZY_MATCH_THRESHOLD,
    "DATE_FORMAT_DETECTION": DATE_FORMAT_DETECTION,
}


def apply_overrides(overrides: dict) -> None:
    """Apply setting overrides at runtime.

    Args:
        overrides: Dictionary of setting names to new values.
                   Keys should match the module-level constant names.

    Example:
        apply_overrides({"KEYWORD_BOOST": 2.0, "SEMANTIC_BOOST": 0.5})
    """
    import testing.evaluation_settings as module

    for key, value in overrides.items():
        if key in _DEFAULTS:
            setattr(module, key, value)
        else:
            raise ValueError(f"Unknown setting: {key}")


def reset_settings() -> None:
    """Reset all settings to their default values."""
    import testing.evaluation_settings as module

    for key, value in _DEFAULTS.items():
        setattr(module, key, value)


def get_current_settings() -> dict:
    """Get all current settings as a dictionary."""
    import testing.evaluation_settings as module

    return {key: getattr(module, key) for key in _DEFAULTS}
