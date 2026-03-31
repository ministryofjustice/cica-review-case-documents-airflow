"""Date format patterns for detecting and matching dates in search terms and chunks.

This module provides regex patterns for common date formats found in documents.
Use these patterns to identify when a search term contains a date, which may
require different matching strategies than standard text searches.

This implementation mirrors the frontend JavaScript date handling for consistency:
- extractDatesFromSearchString (JS) -> extract_dates_from_search_string (Python)
- generateDateFormatVariants (JS) -> generate_date_format_variants (Python)
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

# Month name mappings for parsing
_MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_MONTH_FULL_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

_MONTH_ABBR_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Ordinal suffixes for day numbers
_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}


def _get_ordinal(day: int) -> str:
    """Get ordinal suffix for a day number."""
    return _ORDINAL_SUFFIXES.get(day, "th")


# --------------------------------------------------------------------------
# Regex patterns matching the JavaScript implementation
# --------------------------------------------------------------------------

# Separators: space, dash, dot, slash, unicode dash (matching JS \p{Pd})
_SEPARATOR = r"[\s./\-\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]+"

# Month name pattern (matches JS implementation)
_MONTH_NAME = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

# Day patterns
_DAY_NUMBER = r"(0?[1-9]|[12][0-9]|3[01])"
_DAY_WITH_ORDINAL = (
    r"(?:0?1(?:st)?|0?2(?:nd)?|0?3(?:rd)?|0?[4-9](?:th)?|"
    r"1[0-9](?:th)?|2(?:0|[4-9])(?:th)?|21(?:st)?|22(?:nd)?|23(?:rd)?|30(?:th)?|31(?:st)?)"
)
_MONTH_NUMBER = r"(0?[1-9]|1[0-2])"
_YEAR_2_DIGIT = r"(\d{2})"
_YEAR_4_DIGIT = r"(\d{4})"
_YEAR = rf"(?:{_YEAR_4_DIGIT}|{_YEAR_2_DIGIT})"

# Combined date patterns with named groups (matching JS implementation)
_DAY_MONTH_YEAR = rf"{_DAY_WITH_ORDINAL}{_SEPARATOR}(?:{_MONTH_NAME}){_SEPARATOR}{_YEAR}"
_MONTH_YEAR = rf"(?:{_MONTH_NAME}){_SEPARATOR}{_YEAR}"
_NUMERIC = rf"{_DAY_NUMBER}{_SEPARATOR}{_MONTH_NUMBER}{_SEPARATOR}{_YEAR}"
_YEAR_MONTH_DAY = rf"{_YEAR_4_DIGIT}{_SEPARATOR}(?:{_MONTH_NUMBER}){_SEPARATOR}{_DAY_NUMBER}"

# Combined pattern with named groups (order matters: most specific first)
_DATE_PATTERN = (
    rf"(?<!\w)(?:"
    rf"(?P<dayMonthYear>{_DAY_MONTH_YEAR})|"
    rf"(?P<numeric>{_NUMERIC})|"
    rf"(?P<monthYear>{_MONTH_YEAR})|"
    rf"(?P<yearMonthDay>{_YEAR_MONTH_DAY})"
    rf")(?!\w)"
)

_DATE_REGEX = re.compile(_DATE_PATTERN, re.IGNORECASE | re.UNICODE)


# --------------------------------------------------------------------------
# Type definitions
# --------------------------------------------------------------------------


class MatchedPatterns(TypedDict, total=False):
    """Dictionary indicating which date pattern was matched."""

    dayMonthYear: bool
    numeric: bool
    monthYear: bool
    yearMonthDay: bool


@dataclass
class DateExtractionResult:
    """Result of extracting dates from a search string."""

    dates: list[str]
    remaining_text: str
    matched_patterns: list[MatchedPatterns]


# --------------------------------------------------------------------------
# Format templates matching the JavaScript possibleDateFormats
# --------------------------------------------------------------------------

_POSSIBLE_DATE_FORMATS: dict[str, list[str]] = {
    "dayMonthYear": [
        "d MMM yy",
        "d MMM yyyy",
        "d MMMM yy",
        "d MMMM yyyy",
        "dd MMM yy",
        "dd MMM yyyy",
        "dd MMMM yy",
        "dd MMMM yyyy",
    ],
    "numeric": [
        "d M yy",
        "d M yyyy",
        "d MM yy",
        "d MM yyyy",
        "dd M yy",
        "dd M yyyy",
        "dd MM yy",
        "dd MM yyyy",
    ],
    "monthYear": ["MMM yy", "MMM yyyy", "MMMM yy", "MMMM yyyy"],
    "yearMonthDay": [
        "yyyy M d",
        "yyyy M dd",
        "yyyy MM d",
        "yyyy MM dd",
        "yyyy MMM d",
        "yyyy MMM dd",
        "yyyy MMMM d",
        "yyyy MMMM dd",
    ],
}


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------


def normalise_date_string(date_string: str) -> str:
    """Normalise a date string for parsing.

    Mirrors the JavaScript normaliseDateString function:
    - Trims whitespace
    - Replaces non-alphanumeric delimiters with spaces
    - Strips ordinal suffixes from day numbers (e.g., "1st" -> "1")
    - Normalises "Sep" to "Sept" for parsing
    - Collapses multiple spaces

    Args:
        date_string: Raw date string input.

    Returns:
        A cleaned, space-normalised date string.
    """
    result = date_string.strip()
    # Replace any non-alphanumeric with space
    result = re.sub(r"[^a-zA-Z0-9]+", " ", result)
    # Strip ordinal suffixes from day numbers
    result = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", result, flags=re.IGNORECASE)
    # Normalise 'Sep' to 'Sept' for parsing consistency
    result = re.sub(r"\bSep\b", "Sept", result, flags=re.IGNORECASE)
    # Collapse multiple spaces
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _parse_date_components(normalised: str, formats: list[str]) -> tuple[int, int, int] | None:
    """Try to parse date components from normalised string using given formats.

    Args:
        normalised: Space-normalised date string.
        formats: List of format strings to try.

    Returns:
        Tuple of (day, month, year) if parsed successfully, None otherwise.
    """
    parts = normalised.split()

    for fmt in formats:
        fmt_parts = fmt.split()
        if len(parts) != len(fmt_parts):
            continue

        day, month, year = None, None, None

        try:
            for i, fmt_part in enumerate(fmt_parts):
                part = parts[i]

                if fmt_part in ("d", "dd"):
                    day = int(part)
                elif fmt_part == "M":
                    month = int(part)
                elif fmt_part == "MM":
                    month = int(part)
                elif fmt_part == "MMM":
                    # Handle Sept -> Sep normalisation for lookup
                    lookup = part.lower()
                    if lookup == "sept":
                        lookup = "sep"
                    month = _MONTH_NAMES.get(lookup[:3])
                elif fmt_part == "MMMM":
                    month = _MONTH_NAMES.get(part.lower())
                elif fmt_part == "yy":
                    y = int(part)
                    # Convert 2-digit year (00-99) assuming 2000s for simplicity
                    year = 2000 + y if y < 100 else y
                elif fmt_part == "yyyy":
                    year = int(part)

            # For monthYear pattern, default day to 1
            if day is None and month is not None and year is not None:
                day = 1

            if day is not None and month is not None and year is not None:
                # Validate the date
                datetime(year, month, day)
                return (day, month, year)

        except (ValueError, TypeError):
            continue

    return None


def _format_date(day: int, month: int, year: int, fmt: str) -> str:
    """Format date components according to format string.

    Args:
        day: Day of month (1-31).
        month: Month number (1-12).
        year: Full year.
        fmt: Format string (e.g., "d MMM yyyy").

    Returns:
        Formatted date string with space separators.
    """
    fmt_parts = fmt.split()
    result_parts = []

    for fmt_part in fmt_parts:
        if fmt_part == "d":
            result_parts.append(str(day))
        elif fmt_part == "dd":
            result_parts.append(f"{day:02d}")
        elif fmt_part == "M":
            result_parts.append(str(month))
        elif fmt_part == "MM":
            result_parts.append(f"{month:02d}")
        elif fmt_part == "MMM":
            result_parts.append(_MONTH_ABBR_NAMES[month])
        elif fmt_part == "MMMM":
            result_parts.append(_MONTH_FULL_NAMES[month])
        elif fmt_part == "yy":
            result_parts.append(f"{year % 100:02d}")
        elif fmt_part == "yyyy":
            result_parts.append(str(year))

    return " ".join(result_parts)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def is_date_search(term: str) -> bool:
    """Check if a search term contains a date pattern.

    Args:
        term: The search term to check.

    Returns:
        True if the term matches any known date pattern.
    """
    return bool(_DATE_REGEX.search(term))


def extract_dates_from_search_string(search_string: str) -> DateExtractionResult:
    """Extract date strings from a search query and return the remaining text.

    Mirrors the JavaScript extractDatesFromSearchString function.

    Supports flexible date formats with optional whitespace and common separators.
    Handles numeric, month-name, and ordinal day formats.

    Examples of supported formats:
    - Numeric: 12/05/2024, 12-05-2024, 12 / 05 / 2024, 1/2/23, 12.05.2024, 2024-05-12
    - Month name: 12 Jan 2024, 5 September 2024, Jan 24, September 2024
    - Ordinal day: 1st Jan 2024, 21st February 2024

    Args:
        search_string: The search query potentially containing date strings.

    Returns:
        DateExtractionResult containing:
        - dates: List of extracted date strings in order they appear
        - remaining_text: Original string with dates removed, whitespace normalised
        - matched_patterns: List of dicts indicating which pattern matched each date
    """
    dates: list[str] = []
    matched_patterns: list[MatchedPatterns] = []

    for match in _DATE_REGEX.finditer(search_string):
        dates.append(match.group(0))

        # Detect which named group matched
        pattern_info: MatchedPatterns = {}
        for key in ("dayMonthYear", "numeric", "monthYear", "yearMonthDay"):
            if match.group(key):
                pattern_info[key] = True  # type: ignore
                break
        matched_patterns.append(pattern_info)

    # Remove dates from remaining text and normalise whitespace
    remaining_text = _DATE_REGEX.sub("", search_string)
    remaining_text = re.sub(r"\s+", " ", remaining_text).strip()

    return DateExtractionResult(
        dates=dates,
        remaining_text=remaining_text,
        matched_patterns=matched_patterns,
    )


def generate_date_format_variants(date_string: str, matched_patterns: MatchedPatterns | None = None) -> list[str]:
    """Generate all possible formatted variants for a given date string.

    Mirrors the JavaScript generateDateFormatVariants function.

    This function:
    1. Determines relevant format templates based on matched patterns
    2. Parses the input date string using relevant formats
    3. Generates all possible variants by formatting with each template

    Output variants are space-separated only (e.g., "1 Jan 2024", not "1/Jan/2024").

    Args:
        date_string: The date string to parse and format.
        matched_patterns: Dict indicating which patterns matched (from extraction).

    Returns:
        List of unique formatted date variants. Empty if parsing fails.
    """
    if matched_patterns is None:
        matched_patterns = {}

    # Build list of relevant formats to try based on matched patterns
    relevant_formats: list[str] = []
    for pattern, is_matched in matched_patterns.items():
        if is_matched and pattern in _POSSIBLE_DATE_FORMATS:
            relevant_formats.extend(_POSSIBLE_DATE_FORMATS[pattern])

    # If no patterns specified, try all formats
    if not relevant_formats:
        for formats in _POSSIBLE_DATE_FORMATS.values():
            relevant_formats.extend(formats)

    # Normalise and parse the date
    normalised = normalise_date_string(date_string)
    parsed = _parse_date_components(normalised, relevant_formats)

    if parsed is None:
        return []

    day, month, year = parsed

    # Generate all format variants
    variants: set[str] = set()
    for fmt in relevant_formats:
        formatted = _format_date(day, month, year, fmt)
        variants.add(formatted)

        # Add Sept variant for September (mirrors JS behavior)
        if month == 9 and "Sep" in formatted:
            sept_variant = formatted.replace("Sep", "Sept")
            variants.add(sept_variant)

    return list(variants)


def generate_month_year_variants(date_string: str, matched_patterns: MatchedPatterns | None = None) -> list[str]:
    """Generate month-year only variants from a full date string.

    Used for tiered date matching in combined query mode, where we want to
    match partial dates (e.g., "December 2022") as a fallback when exact
    dates (e.g., "15 December 2022") don't match.

    Args:
        date_string: The date string to parse.
        matched_patterns: Dict indicating which patterns matched (from extraction).

    Returns:
        List of unique month-year variants (e.g., ["December 2022", "Dec 2022", "12 2022"]).
        Empty if parsing fails or if the input is already a month-year only pattern.
    """
    if matched_patterns is None:
        matched_patterns = {}

    # If the input is already month-year only, don't generate partial variants
    if matched_patterns.get("monthYear"):
        return []

    # Build list of relevant formats to try based on matched patterns
    relevant_formats: list[str] = []
    for pattern, is_matched in matched_patterns.items():
        if is_matched and pattern in _POSSIBLE_DATE_FORMATS:
            relevant_formats.extend(_POSSIBLE_DATE_FORMATS[pattern])

    # If no patterns specified, try all formats
    if not relevant_formats:
        for formats in _POSSIBLE_DATE_FORMATS.values():
            relevant_formats.extend(formats)

    # Normalise and parse the date
    normalised = normalise_date_string(date_string)
    parsed = _parse_date_components(normalised, relevant_formats)

    if parsed is None:
        return []

    _, month, year = parsed

    # Generate month-year variants using the monthYear format templates
    variants: set[str] = set()
    month_year_formats = _POSSIBLE_DATE_FORMATS.get("monthYear", [])

    for fmt in month_year_formats:
        # Use day=1 as placeholder (not included in output)
        formatted = _format_date(1, month, year, fmt)
        variants.add(formatted)

        # Add Sept variant for September
        if month == 9 and "Sep" in formatted:
            sept_variant = formatted.replace("Sep", "Sept")
            variants.add(sept_variant)

    # Also add numeric month/year format (e.g., "12/22" for December 2022)
    year_2digit = year % 100
    variants.add(f"{month}/{year_2digit:02d}")

    return list(variants)
