"""Configuration management for relevance scoring.

This module handles search configuration and determines the appropriate
term checking method based on active search types.

Run python -m evaluation_suite.search_evaluation.run_evaluation
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Import module to access settings dynamically (supports runtime overrides)
from evaluation_suite.search_evaluation import evaluation_settings as settings

# Base directory for relative paths
SCRIPT_DIR = Path(__file__).resolve().parent
_OUTPUT_DIR = SCRIPT_DIR / "output"
_EVALUATION_DIR = _OUTPUT_DIR / "evaluation"


@dataclass(frozen=True)
class OutputPaths:
    """Immutable paths for evaluation output directories and files."""

    output_dir: Path = _OUTPUT_DIR
    evaluation_dir: Path = _EVALUATION_DIR
    evaluation_log_file: Path = _EVALUATION_DIR / "evaluation_log.csv"


# Singleton instance for use throughout the module
OUTPUT_PATHS = OutputPaths()

# Backwards compatibility aliases
OUTPUT_DIR = OUTPUT_PATHS.output_dir
EVALUATION_DIR = OUTPUT_PATHS.evaluation_dir
EVALUATION_LOG_FILE = OUTPUT_PATHS.evaluation_log_file


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

    if settings.KEYWORD_BOOST > 0:
        methods.append("exact")
    if settings.WILDCARD_BOOST > 0:
        methods.append("wildcard")
    if settings.ANALYSER_BOOST > 0:
        methods.append("stemmed")
    if settings.FUZZY_BOOST > 0:
        methods.append("fuzzy")
    if settings.SEMANTIC_BOOST > 0:
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


def _resolve_chunking_strategy() -> str:
    """Return the ingestion pipeline's configured chunking strategy.

    Sourced from the ingestion pipeline settings (the chunker actually used to
    build the index) rather than a placeholder, so the comparison log can
    attribute metric changes to the chunking strategy used for the corpus.
    Falls back to ``"unknown"`` if the ingestion settings cannot be imported.
    """
    try:
        from ingestion_pipeline.config import settings as ingestion_settings

        return ingestion_settings.DOCUMENT_CHUNKING_STRATEGY
    except Exception:  # pragma: no cover - defensive; ingestion config is normally importable
        return "unknown"


def get_search_config(
    timestamp: str | None = None,
    num_chunks_indexed: int | None = None,
    chunking_strategy: str | None = None,
) -> dict:
    """Get the current search configuration as a dictionary.

    The fields mirror the parts of the query that actually vary between runs of
    the hybrid / hybrid-dates DSL, plus the context needed to compare runs in
    the cumulative log (which case, which corpus, which chunking strategy).

    Args:
        timestamp: Optional timestamp string. If None, generates current timestamp.
        num_chunks_indexed: Number of chunks in the index at run time (corpus
            size). Recorded so precision/recall can be interpreted and so a
            corpus change is visible in the comparison log.
        chunking_strategy: Chunking strategy used to build the corpus. Defaults
            to the ingestion pipeline's configured strategy.

    Returns:
        Dictionary containing the search configuration parameters.
    """
    if timestamp is None:
        timestamp = get_timestamp()
    if chunking_strategy is None:
        chunking_strategy = _resolve_chunking_strategy()

    return {
        "search_type": get_active_search_type(),
        "case_filter": settings.CASE_FILTER,
        "score_filter": settings.SCORE_FILTER,
        "min_score": settings.MIN_SCORE,
        "result_size": settings.RESULT_SIZE,
        "keyword_boost": settings.KEYWORD_BOOST,
        "semantic_boost": settings.SEMANTIC_BOOST,
        "date_boost": settings.DATE_QUERY_BOOST,
        "date_format_detection": settings.DATE_FORMAT_DETECTION,
        "chunking_strategy": chunking_strategy,
        "num_chunks_indexed": num_chunks_indexed,
        "timestamp": timestamp,
    }
