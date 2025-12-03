"""Search looper for batch testing search terms against OpenSearch.

This script reads search terms from a CSV file, runs each through the local search client,
and outputs results to a CSV file to be used to compare expected page number and expected
chunk ID to the output values for each search term.
"""

import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add the parent directory to sys.path to import search_client
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

# Import after modifying sys.path
from search_client import SCORE_FILTER, local_search_client  # noqa: E402

# --- Configuration ---
INPUT_FILE_NAME = "search_terms.csv"  # Change this to use a different input file
INPUT_FILE = SCRIPT_DIR / "testing_docs" / INPUT_FILE_NAME
OUTPUT_DIR = SCRIPT_DIR / "output"
TIMESTAMP_STR = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_FILE = OUTPUT_DIR / f"{TIMESTAMP_STR}_search_results.csv"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("search_looper")


def load_search_terms(input_file: Path) -> list[dict]:
    """Load search terms from a CSV file."""
    search_terms = []
    with open(input_file, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            search_terms.append(
                {
                    "search_term": row.get("search_term", "").strip(),
                    "expected_page_number": row.get("expected_page_number", "").strip(),
                    "expected_chunk_id": row.get("expected_chunk_id", "").strip(),
                }
            )
    return search_terms


def write_results_to_csv(results: list[dict], output_file: Path) -> None:
    """Write search results to a CSV file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "search_term",
            "expected_page_number",
            "expected_chunk_id",
            "all_chunk_ids",
            "all_page_numbers",
            "total_results",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    logger.info(f"Results written to {output_file.resolve()}")


def main():
    """Main entry point for the search looper."""
    logger.info("Search looper started.")

    # Load search terms from input file
    if not INPUT_FILE.exists():
        logger.error(f"Input file not found: {INPUT_FILE}")
        return

    search_terms = load_search_terms(INPUT_FILE)
    logger.info(f"Loaded {len(search_terms)} search terms from {INPUT_FILE}")

    # Process each search term
    results = []
    for term_data in search_terms:
        search_term = term_data["search_term"]
        expected_page = term_data["expected_page_number"]
        expected_chunk_id = term_data["expected_chunk_id"]

        if not search_term:
            continue

        logger.info(f"Searching for: '{search_term}'")

        try:
            # Use the search_client's local_search_client function
            hits = local_search_client(search_term=search_term)
            # Filter by score
            filtered_hits = [hit for hit in hits if hit["_score"] >= SCORE_FILTER]
        except Exception as e:
            logger.error(f"Search failed for term '{search_term}': {e}")
            filtered_hits = []

        # Get result info
        if filtered_hits:
            # Collect all chunk IDs and page numbers
            all_chunk_ids = ", ".join([hit.get("_id", "N/A") for hit in filtered_hits])
            all_page_numbers = ", ".join([str(hit["_source"].get("page_number", "N/A")) for hit in filtered_hits])
        else:
            all_chunk_ids = ""
            all_page_numbers = ""

        results.append(
            {
                "search_term": search_term,
                "expected_page_number": expected_page,
                "expected_chunk_id": expected_chunk_id,
                "all_chunk_ids": all_chunk_ids,
                "all_page_numbers": all_page_numbers,
                "total_results": len(filtered_hits),
            }
        )

    # Write results to CSV
    write_results_to_csv(results, OUTPUT_FILE)
    logger.info("Search looper finished.")


if __name__ == "__main__":
    main()
