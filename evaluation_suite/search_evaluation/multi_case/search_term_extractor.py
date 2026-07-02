"""Extract per-case search terms from the combined case-attributes Word document.

Produces per-case ``search_terms.csv`` files in::

    testing_docs/cases/<case_ref>/search_terms.csv

Each CSV contains a curated set of benchmark terms (shared across all cases)
followed by case-specific terms extracted from the source document.

Case number mapping
-------------------
The source document uses "Case N" labels.  Case 0 is a training case and is
excluded.  Cases 1–30 map directly to S3 case refs ``26-700001``–``26-700030``.
"""

import csv
import re
from pathlib import Path

import docx

# ---------------------------------------------------------------------------
# Benchmark terms — included in every case CSV.
# These general queries benchmark result counts uniformly across all 30 cases
# so that configuration changes (e.g. stop-word filter) can be compared easily.
# ---------------------------------------------------------------------------
BENCHMARK_TERMS: list[str] = [
    "date of incident",
    "previous injury",
    "pre-existing medical history",
    "mental health treatment records",
    "injuries",
    "treatment",
    "medical records",
]

_CSV_FIELDNAMES = ["search_term", "expected_chunk_id", "expected_page_number"]

# Questions to include when extracting case-specific terms (matched against Col 1).
_INCLUDE_QUESTIONS = ("tags", "categor", "contextual")

# Terms longer than this many words are sentence fragments, not search terms.
_MAX_TERM_WORDS = 6

# Maximum total search terms written per case (benchmark + case-specific).
# Benchmarks are always preserved; excess case-specific terms are dropped.
_MAX_TERMS_PER_CASE = 25


def _split_cell_to_terms(cell_text: str) -> list[str]:
    """Split a cell's text into individual search-term candidates.

    The source document contains free-text assessor notes so the splitting
    strategy must handle several real-world patterns:

    * Comma-separated and newline-separated lists (standard case)
    * Full stops mid-cell: ``"skull fracture. Ongoing treatments"``
    * Forward-slash alternatives: ``"Sexual assault/ abuse"``
    * Inline hyphens used as bullets:
      ``"back injury- possible exacerbation"`` or
      ``"care or supervision -answered yes"``
    * Leading qualifiers: ``"ie mental health"`` → ``"mental health"``

    Compound words such as ``"pre-existing"`` and ``"5-8 years"`` are
    preserved because their hyphens have no adjacent whitespace.

    Terms shorter than 4 characters or longer than :data:`_MAX_TERM_WORDS`
    words are discarded.
    """
    # Strip leading "ie / eg / i.e. / e.g." qualifiers before splitting.
    text = re.sub(r"\b(?:ie|eg|i\.e\.?|e\.g\.?)\b\.?\s*", "", cell_text, flags=re.IGNORECASE)

    # Split on: comma, newline, full stop, forward slash,
    # space+hyphen (` -word`) and hyphen+space (`word- `).
    raw = re.split(r"[,\n./]|\s+[-–]|[-–]\s+", text)

    terms: list[str] = []
    for t in raw:
        t = t.strip(" \t-–•*")
        t = re.sub(r"\s+", " ", t)
        if len(t) < 4:
            continue
        if len(t.split()) > _MAX_TERM_WORDS:
            continue
        terms.append(t)
    return terms


def extract_and_write_search_terms(
    docx_path: Path,
    output_dir: Path,
    case_numbers: list[int] | None = None,
) -> dict[str, int]:
    """Extract search terms for each case and write per-case ``search_terms.csv`` files.

    Scans all tables in the source Word document for rows belonging to the
    requested cases, extracts terms from the tags/categories and contextual-info
    rows (both assessor columns), and writes a CSV combining benchmark terms with
    case-specific terms.

    Args:
        docx_path: Path to the combined source ``.docx`` file.
        output_dir: Root directory under which ``<case_ref>/search_terms.csv``
            files are written.  Subdirectories are created as needed.
        case_numbers: Case numbers to extract (1–30).  Defaults to all 30.

    Returns:
        Mapping of ``case_ref`` → number of search terms written to that CSV.
    """
    doc = docx.Document(str(docx_path))
    target = set(case_numbers or range(1, 31))

    # Accumulate raw terms per case number before deduplication.
    raw_by_case: dict[int, list[str]] = {n: [] for n in target}

    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 4:
                continue
            # Col 0 may contain newlines (e.g. "Case 1\n\n\nCase Attribute").
            case_text = cells[0].split("\n")[0].strip()
            m = re.match(r"Case\s+(\d+)$", case_text)
            if not m:
                continue
            case_number = int(m.group(1))
            if case_number not in target:
                continue
            question = cells[1].lower()
            if any(kw in question for kw in _INCLUDE_QUESTIONS):
                raw_by_case[case_number].extend(_split_cell_to_terms(cells[2]))
                raw_by_case[case_number].extend(_split_cell_to_terms(cells[3]))

    results: dict[str, int] = {}
    for case_number in sorted(target):
        case_ref = f"26-700{case_number:03d}"

        # Deduplicate case-specific terms while preserving order.
        seen: set[str] = set()
        specific: list[str] = []
        for t in raw_by_case[case_number]:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                specific.append(t)

        all_terms = (BENCHMARK_TERMS + specific)[:_MAX_TERMS_PER_CASE]

        case_dir = output_dir / case_ref
        case_dir.mkdir(parents=True, exist_ok=True)
        csv_path = case_dir / "search_terms.csv"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
            writer.writeheader()
            for term in all_terms:
                writer.writerow(
                    {
                        "search_term": term,
                        "expected_chunk_id": "",
                        "expected_page_number": "",
                    }
                )

        results[case_ref] = len(all_terms)

    return results


__all__ = ["BENCHMARK_TERMS", "extract_and_write_search_terms"]
