"""Search looper for batch testing search terms against OpenSearch.

This script reads search terms from a CSV file, runs each through the local search client,
and returns results as a pandas DataFrame to be used for relevance scoring.

Run python -m evaluation_suite.search_evaluation.run_evaluation
"""

import logging
from pathlib import Path

import pandas as pd

# Import module to access settings dynamically (supports runtime overrides)
from evaluation_suite.search_evaluation import evaluation_settings as settings
from evaluation_suite.search_evaluation.search_client import count_term_occurrences, local_search_client

# --- Configuration ---
SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_FILE_NAME = "search_terms.csv"  # Change this to use a different input file
INPUT_FILE = SCRIPT_DIR.parent / "testing_docs" / INPUT_FILE_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("search_looper")


def load_search_terms(input_file: Path) -> tuple[pd.DataFrame, dict]:
    """Load search terms from a CSV file.

    Args:
        input_file: Path to CSV file with search terms.

    Returns:
        Tuple of (DataFrame with search terms, metadata dict from first row columns).
    """
    df = pd.read_csv(input_file, dtype=str).fillna("")
    # Rename columns to standardize
    df = df.rename(
        columns={
            "manual identifications": "manual_identifications",
            "acceptable associated terms": "acceptable_terms",
        }
    )
    # Strip whitespace from all string columns
    for col in df.columns:
        df[col] = df[col].str.strip()

    # Extract metadata from first row if present
    metadata = {}
    metadata_cols = [
        "chunks_generated_with_date_variants",
        "chunks_generated_with_stemming",
        "chunking_strategy",
    ]
    if not df.empty:
        for col in metadata_cols:
            if col in df.columns:
                val = df.iloc[0].get(col, "")
                if val.lower() == "true":
                    metadata[col] = True
                elif val.lower() == "false":
                    metadata[col] = False
                elif val:
                    metadata[col] = val

    return df, metadata


def _process_hits(filtered_hits: list[dict], search_term: str) -> dict:
    """Extract aggregated data from filtered search hits.

    Args:
        filtered_hits: List of OpenSearch hit dictionaries.
        search_term: The search term used for term frequency counting.

    Returns:
        Dictionary with aggregated hit data.
    """
    if not filtered_hits:
        return {
            "all_chunk_ids": "",
            "all_page_numbers": "",
            "all_term_frequencies": "",
            "total_term_frequency": 0,
        }

    all_chunk_ids = ", ".join(hit.get("_id", "N/A") for hit in filtered_hits)
    all_page_numbers = ", ".join(str(hit["_source"].get("page_number", "N/A")) for hit in filtered_hits)
    term_freq_list = [
        count_term_occurrences(hit["_source"].get("chunk_text", ""), search_term) for hit in filtered_hits
    ]
    all_term_frequencies = ", ".join(str(tf) for tf in term_freq_list)
    total_term_frequency = sum(term_freq_list)

    return {
        "all_chunk_ids": all_chunk_ids,
        "all_page_numbers": all_page_numbers,
        "all_term_frequencies": all_term_frequencies,
        "total_term_frequency": total_term_frequency,
    }


def run_search_loop(input_file: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Run search loop and return results as a DataFrame.

    Args:
        input_file: Path to CSV file with search terms. Uses default INPUT_FILE if None.

    Returns:
        Tuple of (DataFrame with search results, metadata dict from CSV header).
    """
    file_path = input_file or INPUT_FILE

    if not file_path.exists():
        logger.error(f"Input file not found: {file_path}")
        return pd.DataFrame(), {}

    search_terms_df, csv_metadata = load_search_terms(file_path)
    logger.info(f"Loaded {len(search_terms_df)} search terms from {file_path}")

    results = []
    for _, row in search_terms_df.iterrows():
        search_term = row.get("search_term", "")

        if not search_term:
            continue

        logger.debug(f"Searching for: '{search_term}'")

        try:
            hits = local_search_client(search_term=search_term)
            filtered_hits = [hit for hit in hits if hit["_score"] >= settings.SCORE_FILTER]
        except Exception as e:
            logger.error(f"Search failed for term '{search_term}': {e}")
            filtered_hits = []

        hit_data = _process_hits(filtered_hits, search_term)

        results.append(
            {
                "search_term": search_term,
                "acceptable_terms": row.get("acceptable_terms", ""),
                "expected_page_number": row.get("expected_page_number", ""),
                "expected_chunk_id": row.get("expected_chunk_id", ""),
                "manual_identifications": row.get("manual_identifications", ""),
                **hit_data,
                "total_results": len(filtered_hits),
            }
        )

    results_df = pd.DataFrame(results)
    # Add index column starting from 1
    results_df.insert(0, "index", range(1, len(results_df) + 1))

    logger.info("Search loop completed.")
    return results_df, csv_metadata


def main():
    """Main entry point for the search looper (for standalone testing)."""
    logger.info("Search looper started.")
    results_df, metadata = run_search_loop()
    if not results_df.empty:
        logger.info(f"Results:\n{results_df.to_string()}")
        logger.info(f"CSV Metadata: {metadata}")
    logger.info("Search looper finished.")


if __name__ == "__main__":
    main()
