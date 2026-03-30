"""Generate expected chunk IDs for search terms based on keyword matching."""

import csv
import logging
import re
from pathlib import Path

import snowballstemmer

from evaluation_suite.search_evaluation.chunks_loader import get_chunk_details_from_opensearch
from evaluation_suite.search_evaluation.date_formats import (
    extract_dates_from_search_string,
    generate_date_format_variants,
    is_date_search,
)
from evaluation_suite.search_evaluation.evaluation_settings import (
    EXP_CHUNK_DATE_VARIANTS,
    EXP_CHUNK_USE_STEMMING,
)

SCRIPT_DIR = Path(__file__).resolve().parent
TESTING_DIR = SCRIPT_DIR.parent
INPUT_FILE = TESTING_DIR / "testing_docs" / "search_terms.csv"
OUTPUT_FILE = INPUT_FILE

CHUNKING_STRATEGY = ""  # Placeholder for chunking strategy, will be added once chunking strategy has a location

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
    """Find chunks containing any keyword from the search term."""
    term = search_term.strip()
    matching_chunks = []

    if not term:
        return matching_chunks

    if is_date_search(term):
        if use_date_variants:
            extraction = extract_dates_from_search_string(term)
            all_variants: set[str] = set()
            for i, date in enumerate(extraction.dates):
                matched_pattern = extraction.matched_patterns[i] if i < len(extraction.matched_patterns) else {}
                variants = generate_date_format_variants(date, matched_pattern)
                if variants:
                    all_variants.update(variants)
                else:
                    all_variants.add(date)
            for chunk in chunks:
                chunk_text_lower = chunk["chunk_text"].lower()
                if any(variant.lower() in chunk_text_lower for variant in all_variants):
                    matching_chunks.append(chunk)
        else:
            term_lower = term.lower()
            for chunk in chunks:
                chunk_text_lower = chunk["chunk_text"].lower()
                if term_lower in chunk_text_lower:
                    matching_chunks.append(chunk)
    elif use_stemming:
        words = term.lower().split()
        stemmed_search_words = set(_stemmer.stemWords(words))
        for chunk in chunks:
            chunk_words = re.findall(r"\b[a-z]+\b", chunk["chunk_text"].lower())
            stemmed_chunk_words = set(_stemmer.stemWords(chunk_words))
            if stemmed_search_words & stemmed_chunk_words:
                matching_chunks.append(chunk)
    else:
        words = term.lower().split()
        for chunk in chunks:
            chunk_text_lower = chunk["chunk_text"].lower()
            if any(word in chunk_text_lower for word in words):
                matching_chunks.append(chunk)

    return matching_chunks


def _read_csv_file(file_path: Path) -> tuple[list[str] | None, list[dict]]:
    """Read CSV file and return fieldnames and rows.

    Returns:
        Tuple of (fieldnames, rows). Returns (None, []) if fieldnames are missing.
    """
    with open(file_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else None
        rows = list(reader)

    return fieldnames, rows


def _write_csv_file(
    file_path: Path,
    fieldnames: list[str],
    rows: list[dict],
    *,
    use_date_variants: bool = False,
    use_stemming: bool = False,
    chunking_strategy: str = "",
) -> None:
    """Write rows to CSV file with metadata in extra columns.

    Metadata columns are added/replaced in the first data row on every write.

    Args:
        file_path: Path to write the CSV file.
        fieldnames: List of column names.
        rows: List of data rows.
        use_date_variants: Whether date variant matching was used for chunk generation.
        use_stemming: Whether stemming was used for chunk generation.
        chunking_strategy: Identifier for the chunking strategy used.
    """
    # Metadata columns - always add/replace
    output_fieldnames = list(fieldnames)
    metadata_cols = [
        "chunks_generated_with_date_variants",
        "chunks_generated_with_stemming",
        "chunking_strategy",
    ]
    for col in metadata_cols:
        if col not in output_fieldnames:
            output_fieldnames.append(col)

    # Always overwrite metadata in first row
    if rows:
        rows[0]["chunks_generated_with_date_variants"] = str(use_date_variants)
        rows[0]["chunks_generated_with_stemming"] = str(use_stemming)
        rows[0]["chunking_strategy"] = chunking_strategy

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _process_search_terms(
    rows: list[dict],
    all_chunks: list[dict],
    *,
    use_date_variants: bool = False,
    use_stemming: bool = False,
) -> list[dict]:
    """Process search terms and update rows with matching chunks.

    Args:
        rows: List of CSV rows with search_term column
        all_chunks: List of all chunks from OpenSearch
        use_date_variants: Whether date variant matching was used
        use_stemming: Whether stemming was used

    Returns:
        Updated rows with expected_chunk_id and expected_page_number populated
    """
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
                use_date_variants=use_date_variants,
                use_stemming=use_stemming,
            )

            chunk_ids = [chunk["chunk_id"] for chunk in matching]
            page_numbers = [str(chunk["page_number"]) for chunk in matching]

            row["expected_chunk_id"] = ", ".join(chunk_ids)
            row["expected_page_number"] = ", ".join(page_numbers)

            logger.info(f"'{search_term}': found {len(chunk_ids)} chunks")

        except Exception as e:
            logger.error(f"Search failed for '{search_term}': {e}")

        updated_rows.append(row)

    return updated_rows


def generate_expected_chunks() -> None:
    """Read search terms, generate expected chunks, and update the CSV."""
    if not INPUT_FILE.exists():
        logger.error(f"Input file not found: {INPUT_FILE}")
        return

    # Read CSV
    fieldnames, rows = _read_csv_file(INPUT_FILE)

    if not fieldnames:
        logger.error("CSV has no headers")
        return

    # Load chunks from OpenSearch
    logger.info("Loading all chunks from OpenSearch...")
    all_chunks = get_chunk_details_from_opensearch()

    if not all_chunks:
        logger.error("No chunks loaded from OpenSearch")
        return

    logger.info(f"Loaded {len(all_chunks)} chunks. Processing {len(rows)} search terms...")

    # Process search terms with current settings
    updated_rows = _process_search_terms(
        rows,
        all_chunks,
        use_date_variants=EXP_CHUNK_DATE_VARIANTS,
        use_stemming=EXP_CHUNK_USE_STEMMING,
    )

    # Write updated CSV with metadata header
    _write_csv_file(
        OUTPUT_FILE,
        fieldnames,
        updated_rows,
        use_date_variants=EXP_CHUNK_DATE_VARIANTS,
        use_stemming=EXP_CHUNK_USE_STEMMING,
        chunking_strategy=CHUNKING_STRATEGY,
    )

    logger.info(f"Updated {OUTPUT_FILE}")


def main() -> None:
    """Main entry point."""
    logger.info("Generating expected chunk IDs...")
    generate_expected_chunks()
    logger.info("Done!")


if __name__ == "__main__":
    main()
