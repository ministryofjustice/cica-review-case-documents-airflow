"""Generate expected chunk IDs for search terms based on simple keyword/match_phrase searches.

This script updates the search_terms.csv file with auto-generated expected chunk IDs
based on actual search results. This ensures expected chunks stay in sync when the
chunking strategy changes.

For single-word terms: uses a simple keyword match
For multi-word terms: uses match_phrase for exact phrase matching

Run from local-dev-environment directory:
    python -m testing.generate_expected_chunks
"""

import csv
import logging
import os
import sys
from pathlib import Path

# Add the project 'src' directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "src"))

from opensearchpy import OpenSearch

from ingestion_pipeline.config import settings
from testing.date_formats import extract_dates_for_search, is_date_search

os.environ["AWS_ACCESS_KEY_ID"] = settings.AWS_ACCESS_KEY_ID
os.environ["AWS_SECRET_ACCESS_KEY"] = settings.AWS_SECRET_ACCESS_KEY
os.environ["AWS_SESSION_TOKEN"] = settings.AWS_SESSION_TOKEN
os.environ["AWS_REGION"] = settings.AWS_REGION

# OpenSearch connection settings
USER = "admin"
PASSWORD = "really-secure-passwordAa!1"  # noqa: S105
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_FILE = SCRIPT_DIR / "testing_docs" / "search_terms.csv"
OUTPUT_FILE = INPUT_FILE  # Overwrite the same file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate_expected_chunks")


def get_opensearch_client() -> OpenSearch:
    """Create and return an OpenSearch client."""
    return OpenSearch(
        hosts=[settings.OPENSEARCH_PROXY_URL],
        http_auth=(USER, PASSWORD),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
    )


def search_for_term(client: OpenSearch, search_term: str, max_results: int = 200) -> list[dict]:
    """Search for a term using keyword match (single word) or match_phrase (multi-word/date).

    For dates, searches for all format variants and deduplicates results.

    Args:
        client: OpenSearch client
        search_term: The search term
        max_results: Maximum number of results to return

    Returns:
        List of hits from OpenSearch
    """
    term = search_term.strip()
    words = term.split()

    # For date searches, use match_phrase with all format variants
    if is_date_search(term):
        date_variants = extract_dates_for_search(term)
        should_clauses = [{"match_phrase": {"chunk_text": variant}} for variant in date_variants]
        query = {"bool": {"should": should_clauses}}
    elif len(words) > 1:
        # Multi-word non-date: use match_phrase
        query = {"match_phrase": {"chunk_text": term}}
    else:
        # Single word: use simple match
        query = {"match": {"chunk_text": term}}

    response = client.search(
        index=CHUNK_INDEX_NAME,
        body={
            "query": query,
            "size": max_results,
            "_source": ["page_number"],
        },
    )

    return response["hits"]["hits"]


def generate_expected_chunks() -> None:
    """Read search terms, generate expected chunks, and update the CSV."""
    if not INPUT_FILE.exists():
        logger.error(f"Input file not found: {INPUT_FILE}")
        return

    # Read existing CSV (handle potential encoding issues)
    with open(INPUT_FILE, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames:
        logger.error("CSV has no headers")
        return

    client = get_opensearch_client()
    logger.info(f"Processing {len(rows)} search terms...")

    updated_rows = []
    for row in rows:
        search_term = row.get("search_term", "").strip()

        if not search_term:
            updated_rows.append(row)
            continue

        try:
            hits = search_for_term(client, search_term)

            # Extract chunk IDs and page numbers
            chunk_ids = [hit["_id"] for hit in hits]
            page_numbers = [str(hit["_source"].get("page_number", "")) for hit in hits]

            # Only update expected_chunk_id if it's empty (preserve manual entries)
            if not row.get("expected_chunk_id", "").strip():
                row["expected_chunk_id"] = ", ".join(chunk_ids)

            # Only update expected_page_number if it's empty (preserve manual entries)
            if not row.get("expected_page_number", "").strip():
                row["expected_page_number"] = ", ".join(page_numbers)

            logger.info(f"'{search_term}': found {len(chunk_ids)} chunks")

        except Exception as e:
            logger.error(f"Search failed for '{search_term}': {e}")

        updated_rows.append(row)

    # Write updated CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

    logger.info(f"Updated {OUTPUT_FILE}")


def main() -> None:
    """Main entry point."""
    logger.info("Generating expected chunks from OpenSearch...")
    generate_expected_chunks()
    logger.info("Done!")


if __name__ == "__main__":
    main()
