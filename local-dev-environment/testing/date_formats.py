"""Date format patterns for detecting and matching dates in search terms and chunks.

This module provides regex patterns for common date formats found in documents.
Use these patterns to identify when a search term contains a date, which may
require different matching strategies than standard text searches.
"""

import re

import dateparser

# Regex components for building date patterns
_FULL_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_ABBR_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_ORDINAL = r"(?:st|nd|rd|th)"

# Date format patterns mapping format name to regex pattern
_DATE_PATTERNS_RAW: dict[str, str] = {
    # Numeric formats
    "dd/mm/yyyy": r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    "dd-mm-yyyy": r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
    "dd.mm.yyyy": r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
    "yyyy-mm-dd": r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    # Full month name formats (more specific first)
    "ddth month yyyy": rf"\b\d{{1,2}}{_ORDINAL}\s+{_FULL_MONTHS}\s+\d{{4}}\b",
    "dd month yyyy": rf"\b\d{{1,2}}\s+{_FULL_MONTHS}\s+\d{{4}}\b",
    "month yyyy": rf"\b{_FULL_MONTHS}\s+\d{{4}}\b",
    # Abbreviated month name formats (more specific first)
    "ddth mon yyyy": rf"\b\d{{1,2}}{_ORDINAL}\s+{_ABBR_MONTHS}\s+\d{{4}}\b",
    "dd mon yyyy": rf"\b\d{{1,2}}\s+{_ABBR_MONTHS}\s+\d{{4}}\b",
    "mon dd, yyyy": rf"\b{_ABBR_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}\b",
    "mon yyyy": rf"\b{_ABBR_MONTHS}\s+\d{{4}}\b",
}

# Pre-compiled patterns for better performance
_COMPILED_PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.IGNORECASE) for name, pattern in _DATE_PATTERNS_RAW.items()
}

# Dateparser settings for UK date format (day first)
_DATEPARSER_SETTINGS: dict[str, str | bool] = {
    "DATE_ORDER": "DMY",
    "PREFER_DAY_OF_MONTH": "first",
    "STRICT_PARSING": True,
}

# Ordinal suffixes for day numbers
_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}


def _get_ordinal(day: int) -> str:
    """Get ordinal suffix for a day number."""
    return _ORDINAL_SUFFIXES.get(day, "th")


def is_date_search(term: str) -> bool:
    """Check if a search term contains a date pattern.

    Args:
        term: The search term to check.

    Returns:
        True if the term matches any known date pattern.
    """
    return any(pattern.search(term) for pattern in _COMPILED_PATTERNS.values())


def extract_dates(text: str) -> list[str]:
    """Extract all unique dates from text matching known patterns.

    Args:
        text: The text to search for dates.

    Returns:
        List of unique matched date strings.
    """
    dates: set[str] = set()
    for pattern in _COMPILED_PATTERNS.values():
        matches = pattern.findall(text)
        dates.update(matches)
    return list(dates)


def _remove_subset_dates(dates: list[str]) -> list[str]:
    """Remove dates that are substrings of other dates.

    For example, if both "25 May 2021" and "May 2021" are found,
    only "25 May 2021" is kept.
    """
    if len(dates) <= 1:
        return dates

    sorted_dates = sorted(dates, key=len, reverse=True)
    result: list[str] = []
    for date in sorted_dates:
        if not any(date.lower() in existing.lower() for existing in result):
            result.append(date)
    return result


def generate_date_variants(date_str: str) -> list[str]:
    """Generate alternative format representations of a date for searching.

    Uses dateparser to parse the date string and generates multiple format variants
    including numeric (slashes/hyphens) and text (full/abbreviated month names).
    """
    parsed = dateparser.parse(date_str, settings=_DATEPARSER_SETTINGS)
    if not parsed:
        return [date_str]

    day = parsed.day
    month = parsed.month
    year = parsed.year
    ordinal = _get_ordinal(day)
    full_month = parsed.strftime("%B")
    abbr_month = parsed.strftime("%b")

    # Generate all format variants (using string formatting for cross-platform compatibility)
    variants = {
        date_str,
        # Numeric formats with slashes
        f"{day}/{month}/{year}",  # 1/1/2018
        f"{day:02d}/{month:02d}/{year}",  # 01/01/2018
        # Numeric formats with hyphens
        f"{day}-{month}-{year}",  # 1-1-2018
        f"{day:02d}-{month:02d}-{year}",  # 01-01-2018
        # ISO format
        f"{year}-{month:02d}-{day:02d}",  # 2018-01-01
        # Full month name formats
        f"{day} {full_month} {year}",  # 1 January 2018
        f"{day}{ordinal} {full_month} {year}",  # 1st January 2018
        # Abbreviated month name formats
        f"{day} {abbr_month} {year}",  # 1 Jan 2018
        f"{day}{ordinal} {abbr_month} {year}",  # 1st Jan 2018
    }

    return list(variants)


def remove_dates_from_text(text: str) -> str:
    """Remove all date patterns from text, returning the remaining text.

    Args:
        text: The text to process.

    Returns:
        Text with all date patterns removed and extra whitespace collapsed.
    """
    result = text
    for pattern in _COMPILED_PATTERNS.values():
        result = pattern.sub("", result)
    # Collapse multiple spaces and strip
    return " ".join(result.split())


def extract_dates_for_search(text: str) -> list[str]:
    """Extract dates and generate format variants for searching.

    Combines extraction, subset removal, and variant generation.
    """
    raw_dates = extract_dates(text)
    filtered_dates = _remove_subset_dates(raw_dates)

    all_variants: set[str] = set()
    for date in filtered_dates:
        all_variants.update(generate_date_variants(date))

    return list(all_variants)
