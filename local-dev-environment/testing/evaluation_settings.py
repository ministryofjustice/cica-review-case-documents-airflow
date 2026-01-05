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

KEYWORD_BOOST = 1.0  # Exact keyword matching
ANALYSER_BOOST = 0.0  # English analyzer (stemming, stopwords)
SEMANTIC_BOOST = 0.0  # Vector/embedding similarity search
FUZZY_BOOST = 0.0  # Fuzzy matching (typo tolerance)
WILDCARD_BOOST = 0.0  # Wildcard pattern matching

# =============================================================================
# SEARCH PARAMETERS
# =============================================================================

K_QUERIES = 60  # Number of results to retrieve per search
SCORE_FILTER = 0.56  # Minimum score threshold (0.0 = no filter)

# Fuzzy search settings
FUZZINESS = "Auto"  # "Auto", "0", "1", "2" - Auto chooses based on term length
MAX_EXPANSIONS = 50  # Maximum fuzzy term expansions

# =============================================================================
# TERM MATCHING SETTINGS
# =============================================================================
# These control how we verify if returned chunks contain search terms when a
# fuzzy match is conducted using rapidfuzz to simulate opensearch fuzzy matching.

FUZZY_MATCH_THRESHOLD = 80  # Similarity threshold for fuzzy term matching (0-100)


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
    "FUZZINESS": FUZZINESS,
    "MAX_EXPANSIONS": MAX_EXPANSIONS,
    "FUZZY_MATCH_THRESHOLD": FUZZY_MATCH_THRESHOLD,
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
