"""Evaluation settings - EDIT THIS FILE TO CONFIGURE SEARCH EVALUATION.

This is the single location to configure all search evaluation parameters.
Modify the values below to test different search configurations.

Run evaluation from local-dev-environment directory:
    python -m testing.run_evaluation
"""

# =============================================================================
# SEARCH TYPE BOOSTS
# =============================================================================
# Set boost to 0 to disable a search type, or >0 to enable and weight it.
# Higher boost = more weight in the combined search score.

KEYWORD_BOOST = 0.0  # Exact keyword matching
ANALYSER_BOOST = 1.0  # English analyzer (stemming, stopwords)
SEMANTIC_BOOST = 1.0  # Vector/embedding similarity search
FUZZY_BOOST = 0.0  # Fuzzy matching (typo tolerance)
WILDCARD_BOOST = 0.0  # Wildcard pattern matching

# =============================================================================
# SEARCH PARAMETERS
# =============================================================================

K_QUERIES = 180  # Number of results to retrieve per search
SCORE_FILTER = 0.5  # Minimum score threshold (0.0 = no filter)

# Fuzzy search settings
FUZZINESS = "Auto"  # "Auto", "0", "1", "2" - Auto chooses based on term length
MAX_EXPANSIONS = 50  # Maximum fuzzy term expansions

# =============================================================================
# TERM MATCHING SETTINGS
# =============================================================================
# These control how we verify if returned chunks contain search terms when a
# fuzzy match is conducted.

FUZZY_MATCH_THRESHOLD = 80  # Similarity threshold for fuzzy term matching (0-100)
