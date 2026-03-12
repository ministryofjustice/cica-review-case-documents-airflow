"""Date extraction, normalisation, and cleaning for page chunk free-text fields.

Detects date-like patterns in UK medical text, parses them into Python date
objects, normalises to YYYY-MM-DD, and optionally removes them from the source
text.
"""

import logging
import re
from datetime import date, datetime

from ingestion_pipeline.date_extraction.patterns import (
    _REMOVAL_PATTERNS,
    MONTH_MAP,
    PAT_COMPACT,
    PAT_DAY_MNAME_NOYR,
    PAT_DAY_MNAME_YEAR_SEP,
    PAT_DAY_MNAME_YEAR_SPACE,
    PAT_ISO,
    PAT_MNAME_DAY_YEAR,
    PAT_NUMERIC_UK,
    PAT_SPACE_NUMERIC,
)

logger = logging.getLogger(__name__)

# Sanity bounds for extracted dates
_MIN_YEAR = 1900
_MAX_YEAR = 2060


def _current_two_digit_year_limit() -> int:
    """Return the max two-digit year that maps to 20YY (inclusive).

    E.g. in 2026 this returns 26, meaning 01–26 → 2001–2026; 27–99 → 1927–1999;
    00 → 2000.
    """
    return datetime.now().year % 100


def _expand_short_year(yy: int) -> int:
    """Convert a two-digit year to four digits using the short-year rule.

    - 00         → 2000
    - 01–limit   → 20YY  (e.g. 21 → 2021 when limit=26)
    - limit+1–99 → 19YY  (e.g. 27 → 1927, 98 → 1998)
    """
    if yy == 0:
        return 2000
    limit = _current_two_digit_year_limit()
    if 1 <= yy <= limit:
        return 2000 + yy
    return 1900 + yy


def _resolve_year(raw: str) -> int | None:
    """Parse a year string (2 or 4 digits) into a four-digit year.

    Returns None when the value is invalid or out of the sanity range.
    """
    value = int(raw)
    if len(raw) == 2:
        return _expand_short_year(value)
    if _MIN_YEAR <= value <= _MAX_YEAR:
        return value
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    """Build a date object if the components are calendrically valid."""
    if not (_MIN_YEAR <= year <= _MAX_YEAR):
        return None
    if not (1 <= month <= 12):
        return None
    if not (1 <= day <= 31):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_from_name(name: str) -> int | None:
    """Look up a month number from a full or abbreviated month name."""
    return MONTH_MAP.get(name.lower())


def _extract_raw(text: str, *, allow_yearless: bool = False) -> list[date]:
    """Run all regex patterns against *text* and return a list of parsed dates.

    Patterns are tried in priority order. Each match location is tracked so
    overlapping matches from later (less specific) patterns are skipped.
    """
    results: list[date] = []
    # Track character spans already claimed by a higher-priority pattern
    claimed: list[tuple[int, int]] = []

    def _is_claimed(start: int, end: int) -> bool:
        return any(cs <= start < ce or cs < end <= ce for cs, ce in claimed)

    def _claim(start: int, end: int) -> None:
        claimed.append((start, end))

    # --- A1: Day-MonthName-Year with separators ---
    for m in PAT_DAY_MNAME_YEAR_SEP.finditer(text):
        if _is_claimed(m.start(), m.end()):
            continue
        day_s, mon_s, yr_s = m.group(1), m.group(2), m.group(3)
        month = _month_from_name(mon_s)
        year = _resolve_year(yr_s) if month else None
        if month and year:
            d = _safe_date(year, month, int(day_s))
            if d:
                results.append(d)
                _claim(m.start(), m.end())

    # --- A2: Day MonthName[,] Year (space-separated) ---
    for m in PAT_DAY_MNAME_YEAR_SPACE.finditer(text):
        if _is_claimed(m.start(), m.end()):
            continue
        day_s, mon_s, yr_s = m.group(1), m.group(2), m.group(3)
        month = _month_from_name(mon_s)
        year = _resolve_year(yr_s) if month else None
        if month and year:
            d = _safe_date(year, month, int(day_s))
            if d:
                results.append(d)
                _claim(m.start(), m.end())

    # --- A3: MonthName Day Year ---
    for m in PAT_MNAME_DAY_YEAR.finditer(text):
        if _is_claimed(m.start(), m.end()):
            continue
        mon_s, day_s, yr_s = m.group(1), m.group(2), m.group(3)
        month = _month_from_name(mon_s)
        year = _resolve_year(yr_s) if month else None
        if month and year:
            d = _safe_date(year, month, int(day_s))
            if d:
                results.append(d)
                _claim(m.start(), m.end())

    # --- C1: ISO YYYY-MM-DD / YYYY/MM/DD ---
    for m in PAT_ISO.finditer(text):
        if _is_claimed(m.start(), m.end()):
            continue
        yr_s, mon_s, day_s = m.group(1), m.group(2), m.group(3)
        year = _resolve_year(yr_s)
        if year:
            d = _safe_date(year, int(mon_s), int(day_s))
            if d:
                results.append(d)
                _claim(m.start(), m.end())

    # --- C2: Compact YYYYMMDD ---
    for m in PAT_COMPACT.finditer(text):
        if _is_claimed(m.start(), m.end()):
            continue
        yr_s, mon_s, day_s = m.group(1), m.group(2), m.group(3)
        year = _resolve_year(yr_s)
        if year:
            d = _safe_date(year, int(mon_s), int(day_s))
            if d:
                results.append(d)
                _claim(m.start(), m.end())

    # --- B: Numeric UK DD/MM/YYYY or DD-MM-YYYY or DD.MM.YY ---
    for m in PAT_NUMERIC_UK.finditer(text):
        if _is_claimed(m.start(), m.end()):
            continue
        day_s, mon_s, yr_s = m.group(1), m.group(2), m.group(3)
        year = _resolve_year(yr_s)
        if year:
            d = _safe_date(year, int(mon_s), int(day_s))
            if d:
                results.append(d)
                _claim(m.start(), m.end())

    # --- D: Space-only numeric DD MM YYYY ---
    for m in PAT_SPACE_NUMERIC.finditer(text):
        if _is_claimed(m.start(), m.end()):
            continue
        day_s, mon_s, yr_s = m.group(1), m.group(2), m.group(3)
        year = _resolve_year(yr_s)
        if year:
            d = _safe_date(year, int(mon_s), int(day_s))
            if d:
                results.append(d)
                _claim(m.start(), m.end())

    # --- E: Yearless Day MonthName ---
    if allow_yearless:
        for m in PAT_DAY_MNAME_NOYR.finditer(text):
            if _is_claimed(m.start(), m.end()):
                continue
            day_s, mon_s = m.group(1), m.group(2)
            month = _month_from_name(mon_s)
            if month:
                current_year = datetime.now().year
                d = _safe_date(current_year, month, int(day_s))
                if d:
                    results.append(d)
                    _claim(m.start(), m.end())

    return results


# ── Public API ───────────────────────────────────────────────────────────────


def extract_dates(text: str, *, allow_yearless: bool = False) -> list[str]:
    """Return sorted unique ISO dates extracted from *text*.

    Args:
        text: Free-text string potentially containing dates.
        allow_yearless: When True, patterns like "4 Aug" are matched and
            the current year is assumed.

    Returns:
        A list of unique date strings in ascending YYYY-MM-DD order.
    """
    dates = _extract_raw(text, allow_yearless=allow_yearless)
    unique = sorted({d.isoformat() for d in dates})
    return unique


def remove_dates(text: str) -> str:
    """Return *text* with all recognised date substrings removed.

    Consecutive whitespace left by removal is collapsed to a single space
    and leading/trailing whitespace is stripped.
    """
    result = text
    for pattern in _REMOVAL_PATTERNS:
        result = pattern.sub("", result)
    # Normalise whitespace
    result = re.sub(r"\s{2,}", " ", result).strip()
    return result


def extract_and_clean(chunk: dict, *, allow_yearless: bool = False) -> dict:
    """Add a ``dates`` field to a page_chunk dict.

    Reads ``chunk["chunk_text"]``, extracts and normalises all dates found,
    and writes them into ``chunk["dates"]`` as a sorted list of ISO strings.
    The original ``chunk_text`` is **not** modified.

    Args:
        chunk: A dict with at least a ``chunk_text`` key.
        allow_yearless: Forward to :func:`extract_dates`.

    Returns:
        The same dict reference, mutated with the new ``dates`` key.
    """
    text = chunk.get("chunk_text", "")
    chunk["dates"] = extract_dates(text, allow_yearless=allow_yearless)
    return chunk
