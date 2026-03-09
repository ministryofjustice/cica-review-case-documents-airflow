"""Evaluation settings - EDIT THIS FILE TO CONFIGURE SEARCH EVALUATION.

This is the single location to configure all search evaluation parameters.
Modify the values below to test different search configurations.

Run evaluation from local-dev-environment directory:
    python -m evaluation_suite.search_evaluation.run_evaluation

For programmatic override (e.g., optimization), use:
    from evaluation_suite.search_evaluation.evaluation_settings import apply_overrides, reset_settings
    apply_overrides({"KEYWORD_BOOST": 2.0, "RESULT_SIZE": 100})
    # ... run evaluation ...
    reset_settings()  # restore defaults
"""

# =============================================================================
# SEARCH TYPE BOOSTS
# =============================================================================
# Set boost to 0 to disable a search type, or >0 to enable and weight it.
# Higher boost = more weight in the combined search score.

KEYWORD_BOOST = 1.2  # Exact keyword matching
ANALYSER_BOOST = 0  # English analyzer (stemming, stopwords)
SEMANTIC_BOOST = 0  # Vector/embedding similarity search
FUZZY_BOOST = 0  # Fuzzy matching (typo tolerance)
WILDCARD_BOOST = 0  # Wildcard pattern matching

# =============================================================================
# SEARCH PARAMETERS
# =============================================================================

RESULT_SIZE = 40  # Number of results to retrieve per search
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
# EXPECTED CHUNK GENERATION
# =============================================================================
# Settings for generate_expected_chunks.py - controls how expected chunk IDs
# are generated from search terms for evaluation comparison.

CHUNK_GEN_DATE_VARIANTS = False  # Generate expected chunks using date format variants
CHUNK_GEN_USE_STEMMING = False  # Generate expected chunks using word stemming

# =============================================================================
# OPENSEARCH CONFIGURATION
# =============================================================================
# Settings for OpenSearch query execution and data retrieval

OPENSEARCH_SCROLL_TIMEOUT = "2m"  # Timeout for scroll API cursor (e.g., "2m", "5m")
OPENSEARCH_BATCH_SIZE = 1000  # Number of documents per scroll batch
OPENSEARCH_TIMEOUT = 30  # Client request timeout in seconds
OPENSEARCH_MAX_RETRIES = 3  # Maximum number of retries for transient failures
OPENSEARCH_RETRY_BACKOFF_FACTOR = 0.1  # Exponential backoff factor for retries
DATE_QUERY_BOOST = 2.0  # Boost multiplier for exact date phrase queries

# =============================================================================
# CASE FILTERING
# =============================================================================
# Case reference to evaluate. This is required and cannot be None.
# Change this value to evaluate a different case.

CASE_FILTER = "26-711111"  # Required: specify the case reference to evaluate

# =============================================================================
# OPTIMIZATION SETTINGS
# =============================================================================
# Configuration for Bayesian optimization of search parameters

OPTIMIZATION_DEFAULT_N_TRIALS = 30  # Default number of trials to run
OPTIMIZATION_PHASE1_STEP = 0.3  # Step size for phase 1 (coarse search)
OPTIMIZATION_PHASE2_STEP = 0.05  # Step size for phase 2 (fine-tuning)
OPTIMIZATION_SINGLE_PHASE_STEP = 0.1  # Step size for single-phase optimization
OPTIMIZATION_BOOST_RANGE_MIN = 0.0  # Minimum boost value
OPTIMIZATION_BOOST_RANGE_MAX = 5.0  # Maximum boost value
OPTIMIZATION_PRECISION = 4  # Decimal places for rounding boost values
OPTIMIZATION_PENALTY_SCORE = -1000.0  # Penalty score for failed trials

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
    "RESULT_SIZE": RESULT_SIZE,
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
    "CHUNK_GEN_DATE_VARIANTS": CHUNK_GEN_DATE_VARIANTS,
    "CHUNK_GEN_USE_STEMMING": CHUNK_GEN_USE_STEMMING,
    "CASE_FILTER": CASE_FILTER,
    "OPTIMIZATION_DEFAULT_N_TRIALS": OPTIMIZATION_DEFAULT_N_TRIALS,
    "OPTIMIZATION_PHASE1_STEP": OPTIMIZATION_PHASE1_STEP,
    "OPTIMIZATION_PHASE2_STEP": OPTIMIZATION_PHASE2_STEP,
    "OPTIMIZATION_SINGLE_PHASE_STEP": OPTIMIZATION_SINGLE_PHASE_STEP,
    "OPTIMIZATION_BOOST_RANGE_MIN": OPTIMIZATION_BOOST_RANGE_MIN,
    "OPTIMIZATION_BOOST_RANGE_MAX": OPTIMIZATION_BOOST_RANGE_MAX,
    "OPTIMIZATION_PRECISION": OPTIMIZATION_PRECISION,
    "OPTIMIZATION_PENALTY_SCORE": OPTIMIZATION_PENALTY_SCORE,
    "OPENSEARCH_SCROLL_TIMEOUT": OPENSEARCH_SCROLL_TIMEOUT,
    "OPENSEARCH_BATCH_SIZE": OPENSEARCH_BATCH_SIZE,
    "OPENSEARCH_TIMEOUT": OPENSEARCH_TIMEOUT,
    "OPENSEARCH_MAX_RETRIES": OPENSEARCH_MAX_RETRIES,
    "OPENSEARCH_RETRY_BACKOFF_FACTOR": OPENSEARCH_RETRY_BACKOFF_FACTOR,
    "DATE_QUERY_BOOST": DATE_QUERY_BOOST,
}


def apply_overrides(overrides: dict) -> None:
    """Apply setting overrides at runtime.

    Args:
        overrides: Dictionary of setting names to new values.
                   Keys should match the module-level constant names.

    Example:
        apply_overrides({"KEYWORD_BOOST": 2.0, "SEMANTIC_BOOST": 0.5})
    """
    import evaluation_suite.search_evaluation.evaluation_settings as module

    for key, value in overrides.items():
        if key in _DEFAULTS:
            setattr(module, key, value)
        else:
            raise ValueError(f"Unknown setting: {key}")


def reset_settings() -> None:
    """Reset all settings to their default values."""
    import evaluation_suite.search_evaluation.evaluation_settings as module

    for key, value in _DEFAULTS.items():
        setattr(module, key, value)


def get_current_settings() -> dict:
    """Get all current settings as a dictionary."""
    import evaluation_suite.search_evaluation.evaluation_settings as module

    return {key: getattr(module, key) for key in _DEFAULTS}
