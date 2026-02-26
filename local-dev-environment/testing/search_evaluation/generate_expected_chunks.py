"""Generate expected chunk IDs for search terms based on keyword matching.

This script updates the search_terms.csv file with auto-generated expected chunk IDs
based on local keyword matching against all indexed chunks. This ensures expected
chunks stay in sync when the chunking strategy changes.

All terms (single or multi-word) use keyword matching:
- Any word in the search term appearing in the chunk is a match (case-insensitive)
- If USE_STEMMING is True, words are stemmed before matching (e.g., "injuries" matches "injury")
- For dates: if DATE_FORMAT_VARIANTS is True, matches any format variant;
  if False, searches the exact date string as a phrase match

Run from local-dev-environment directory:
    python -m testing.search_evaluation.generate_expected_chunks
"""

import csv
import logging
import re
from pathlib import Path

import snowballstemmer  # For stemming, uses Porter2 stemmer which is the same as OpenSearch's standard analyzer

from testing.search_evaluation.chunks_loader import get_chunk_details_from_opensearch
from testing.search_evaluation.date_formats import extract_dates_for_search, is_date_search

SCRIPT_DIR = Path(__file__).resolve().parent
TESTING_DIR = SCRIPT_DIR.parent  # Parent is the testing package directory
INPUT_FILE = TESTING_DIR / "testing_docs" / "search_terms.csv"
OUTPUT_FILE = INPUT_FILE  # Overwrite the same file

# When True, dates are matched against multiple format variants (e.g., 28/01/2018, 2018-01-28)
# When False, dates are searched as exact phrase matches
DATE_FORMAT_VARIANTS = False

# When True, words are stemmed before matching (e.g., "injuries" matches "injury")
# When False, exact word matching is used
USE_STEMMING = False

# Initialize stemmer for English (matches OpenSearch's English analyzer for stemming)
_stemmer = snowballstemmer.stemmer("english")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate_expected_chunks")


def find_matching_chunks(
    chunks: list[dict],
    search_term: str,
    *,
    use_date_variants: bool = False,
    use_stemming: bool = False,
) -> list[dict]:
    """Find chunks containing any keyword from the search term.

    For date searches with use_date_variants=True, matches any date format variant.
    For date searches with use_date_variants=False, searches exact phrase.
    For regular searches, any word must appear in the chunk text (case-insensitive).
    If use_stemming=True, words are stemmed before matching.

    Args:
        chunks: List of chunk dictionaries with chunk_id, chunk_text, page_number
        search_term: The search term
        use_date_variants: If True, match dates against format variants;
                          if False, search dates as exact phrase matches
        use_stemming: If True, apply stemming to search terms and chunk text

    Returns:
        List of matching chunk IDs
    """
    term = search_term.strip()
    matching_chunks = []

    if is_date_search(term):
        if use_date_variants:
            # For dates with variant matching, check if any format variant appears
            date_variants = extract_dates_for_search(term)
            for chunk in chunks:
                chunk_text_lower = chunk["chunk_text"].lower()
                if any(variant.lower() in chunk_text_lower for variant in date_variants):
                    matching_chunks.append(chunk)
        else:
            # For dates without variant matching, use exact phrase match
            term_lower = term.lower()
            for chunk in chunks:
                chunk_text_lower = chunk["chunk_text"].lower()
                if term_lower in chunk_text_lower:
                    matching_chunks.append(chunk)
    elif use_stemming:
        # For regular terms with stemming, stem the search words
        words = term.lower().split()
        stemmed_search_words = set(_stemmer.stemWords(words))
        for chunk in chunks:
            # Extract words from chunk and stem them
            chunk_words = re.findall(r"\b[a-z]+\b", chunk["chunk_text"].lower())
            stemmed_chunk_words = set(_stemmer.stemWords(chunk_words))
            # Match if any stemmed search word appears in stemmed chunk words
            if stemmed_search_words & stemmed_chunk_words:
                matching_chunks.append(chunk)
    else:
        # For regular terms without stemming, any word must appear (keyword match)
        words = term.lower().split()
        for chunk in chunks:
            chunk_text_lower = chunk["chunk_text"].lower()
            if any(word in chunk_text_lower for word in words):
                matching_chunks.append(chunk)

    return matching_chunks


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

    # Load all chunks from OpenSearch via chunks_loader
    logger.info("Loading all chunks from OpenSearch...")
    all_chunks = get_chunk_details_from_opensearch()
    if not all_chunks:
        logger.error("No chunks loaded from OpenSearch")
        return
    logger.info(f"Loaded {len(all_chunks)} chunks. Processing {len(rows)} search terms...")

    updated_rows = []
    for row in rows:
        search_term = row.get("search_term", "").strip()

        if not search_term:
            updated_rows.append(row)
            continue

        try:
            matching = find_matching_chunks(
                all_chunks,
                search_term,
                use_date_variants=DATE_FORMAT_VARIANTS,
                use_stemming=USE_STEMMING,
            )

            # Extract chunk IDs and page numbers
            chunk_ids = [chunk["chunk_id"] for chunk in matching]
            page_numbers = [str(chunk["page_number"]) for chunk in matching]

            # Always overwrite expected_chunk_id and expected_page_number
            row["expected_chunk_id"] = ", ".join(chunk_ids)
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
