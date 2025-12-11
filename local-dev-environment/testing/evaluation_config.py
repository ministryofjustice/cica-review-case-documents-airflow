"""Configuration management for relevance scoring.

This module handles search configuration and determines the appropriate
term checking method based on active search types.

Run from local-dev-environment directory: python -m testing.run_evaluation
"""

from datetime import datetime
from pathlib import Path

from testing.evaluation_settings import (
    ANALYSER_BOOST,
    FUZZINESS,
    FUZZY_BOOST,
    K_QUERIES,
    KEYWORD_BOOST,
    MAX_EXPANSIONS,
    SCORE_FILTER,
    SEMANTIC_BOOST,
    WILDCARD_BOOST,
)

# Output directories
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
EVALUATION_DIR = OUTPUT_DIR / "evaluation"
EVALUATION_LOG_FILE = EVALUATION_DIR / "evaluation_log.csv"
CHUNKS_FILE = SCRIPT_DIR / "testing_docs" / "TC19_test_all_chunks.csv"


def get_timestamp() -> str:
    """Get current timestamp string for output filenames."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def get_date_folder() -> Path:
    """Get the evaluation output folder for today's date.

    Returns:
        Path to the date-based subfolder within EVALUATION_DIR.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    return EVALUATION_DIR / date_str


def get_active_search_types() -> list[str]:
    """Determine all active term checking methods based on search types.

    Returns:
        List of matching methods to use. When multiple search types are active,
        a term is considered matched if ANY method finds it.

    Methods:
    - 'exact': Substring matching (keyword search)
    - 'wildcard': Wildcard pattern matching (wildcard search)
    - 'stemmed': Snowball English stemmer (analyser search)
    - 'fuzzy': Approximate string matching (fuzzy search)
    - 'semantic_only': Uses expected chunk IDs (semantic search - text matching not applicable)
    """
    methods = []

    if KEYWORD_BOOST > 0:
        methods.append("exact")
    if WILDCARD_BOOST > 0:
        methods.append("wildcard")
    if ANALYSER_BOOST > 0:
        methods.append("stemmed")
    if FUZZY_BOOST > 0:
        methods.append("fuzzy")
    if SEMANTIC_BOOST > 0:
        methods.append("semantic_only")

    # Default to exact if nothing is active
    return methods or ["exact"]


def get_active_search_type() -> str:
    """Get a single search type label for logging/display.

    Returns:
        String describing the active method(s): 'exact', 'stemmed', 'fuzzy',
        'wildcard', 'semantic_only', or 'hybrid' if multiple boosts are active.
    """
    methods = get_active_search_types()

    # If more than one boost is non-zero, it's a hybrid search
    if len(methods) > 1:
        return "hybrid"

    # Single method active
    return methods[0] if methods else "exact"


def get_search_config(timestamp: str | None = None) -> dict:
    """Get the current search configuration as a dictionary.

    Args:
        timestamp: Optional timestamp string. If None, generates current timestamp.

    Returns:
        Dictionary containing all search configuration parameters.
    """
    if timestamp is None:
        timestamp = get_timestamp()

    return {
        "search_type": get_active_search_type(),
        "score_filter": SCORE_FILTER,
        "k_queries": K_QUERIES,
        "keyword_boost": KEYWORD_BOOST,
        "analyser_boost": ANALYSER_BOOST,
        "semantic_boost": SEMANTIC_BOOST,
        "fuzzy_boost": FUZZY_BOOST,
        "wildcard_boost": WILDCARD_BOOST,
        "fuzziness": FUZZINESS,
        "max_expansions": MAX_EXPANSIONS,
        "timestamp": timestamp,
    }
