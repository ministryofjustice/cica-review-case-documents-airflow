"""Regex patterns and constants for UK medical text date extraction."""

import re

# Month name mappings (full and abbreviated) to month numbers
MONTH_MAP: dict[str, int] = {
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

# Alternation of all month names for use in regex patterns
_MONTH_NAMES = "|".join(MONTH_MAP.keys())

# Ordinal suffixes stripped from day numbers
ORDINAL_SUFFIX = r"(?:st|nd|rd|th)"

# --- Pattern groups (order matters: more specific patterns first) ---

# A1: Day-MonthName-Year with separators  e.g. "25-Aug-2021", "30-July-2021"
PAT_DAY_MNAME_YEAR_SEP = re.compile(
    rf"\b(\d{{1,2}}){ORDINAL_SUFFIX}?[/\-]({_MONTH_NAMES})[/\-](\d{{2,4}})\b",
    re.IGNORECASE,
)

# A2: Day MonthName[,] Year  e.g. "4 Aug 2021", "4th August 2021", "20 July, 2021"
#     Optional trailing time component is captured but ignored.
PAT_DAY_MNAME_YEAR_SPACE = re.compile(
    rf"\b(\d{{1,2}}){ORDINAL_SUFFIX}?\s+({_MONTH_NAMES}),?\s+(\d{{2,4}})(?:\s+\d{{1,2}}:\d{{2}}(?::\d{{2}})?)?\b",
    re.IGNORECASE,
)

# A3: MonthName Day[,] Year  e.g. "August 4, 2021"
PAT_MNAME_DAY_YEAR = re.compile(
    rf"\b({_MONTH_NAMES})\s+(\d{{1,2}}){ORDINAL_SUFFIX}?,?\s+(\d{{2,4}})\b",
    re.IGNORECASE,
)

# C1: ISO format YYYY-MM-DD or YYYY/MM/DD  e.g. "2021-08-04", "2021/08/04"
PAT_ISO = re.compile(
    r"\b(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\b",
)

# C2: Compact 8-digit YYYYMMDD  e.g. "20210720"
#     Word boundaries + negative lookbehind/ahead for longer digit runs to avoid NHS numbers.
PAT_COMPACT = re.compile(
    r"(?<!\d)(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)",
)

# B: Numeric UK dates DD/MM/YYYY or DD-MM-YYYY or DD.MM.YY  e.g. "04/08/2021", "4-8-21"
PAT_NUMERIC_UK = re.compile(
    r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b",
)

# D: Space-only numeric dates  e.g. "4 8 21", "04 08 2021", "20 7 2021"
#    Requires exactly two single-space separators between components.
PAT_SPACE_NUMERIC = re.compile(
    r"(?<!\S)(\d{1,2}) (\d{1,2}) (\d{2,4})(?!\S)",
)

# E: Yearless Day MonthName  e.g. "4 Aug", "20 July"
PAT_DAY_MNAME_NOYR = re.compile(
    rf"\b(\d{{1,2}}){ORDINAL_SUFFIX}?\s+({_MONTH_NAMES})\b",
    re.IGNORECASE,
)

# Combined removal pattern: union of all date-like substrings (used by remove_dates).
# Built at module level so it compiles once.
_REMOVAL_PATTERNS: list[re.Pattern[str]] = [
    PAT_DAY_MNAME_YEAR_SEP,
    PAT_DAY_MNAME_YEAR_SPACE,
    PAT_MNAME_DAY_YEAR,
    PAT_ISO,
    PAT_COMPACT,
    PAT_NUMERIC_UK,
    PAT_SPACE_NUMERIC,
    PAT_DAY_MNAME_NOYR,
]
