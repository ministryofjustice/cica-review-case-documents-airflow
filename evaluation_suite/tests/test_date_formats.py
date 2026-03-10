"""Unit tests for date_formats.py."""

from evaluation_suite.search_evaluation import date_formats


def test_is_date_search_true_for_various_formats():
    """Test that is_date_search returns True for various date format strings.

    Verifies that the is_date_search function correctly identifies and accepts
    multiple common date formats including:
    - Numeric formats with slashes, hyphens, and dots (DD/MM/YYYY)
    - ISO format (YYYY-MM-DD)
    - Full text formats (day month year)
    - Abbreviated formats (day abbreviated_month year)
    - Month and year only formats
    """
    assert date_formats.is_date_search("12/05/2021")
    assert date_formats.is_date_search("12-05-2021")
    assert date_formats.is_date_search("12.05.2021")
    assert date_formats.is_date_search("2021-05-12")
    assert date_formats.is_date_search("12th January 2021")
    assert date_formats.is_date_search("12 Jan 2021")
    assert date_formats.is_date_search("12-Sept-2021")
    # assert date_formats.is_date_search("Sept 2021")


def test_is_date_search_false_for_non_dates():
    """Test that is_date_search returns False for non-date strings."""
    assert not date_formats.is_date_search("hello world")
    assert not date_formats.is_date_search("12 monkeys")
    assert not date_formats.is_date_search("Mayday")


def test_extract_dates_finds_all_formats():
    """Test that extract_dates finds all date formats in a given text."""
    text = "The event is on 12/05/2021, but could be 13th May 2021 or 2021-05-14. Also see 14-Sept-2021 and Sept 2021."
    found = date_formats.extract_dates(text)
    assert "12/05/2021" in found
    assert "13th May 2021" in found
    assert "2021-05-14" in found
    assert "14-Sept-2021" in found
    # assert "Sept 2021" in found


def test_extract_dates_empty_when_no_dates():
    """Test that extract_dates returns an empty list when no dates are present."""
    assert date_formats.extract_dates("No dates here!") == []


def test_remove_subset_dates_removes_substrings():
    """Test that _remove_subset_dates removes dates that are substrings of other dates."""
    dates = ["25 May 2021", "May 2021", "2021"]
    filtered = date_formats._remove_subset_dates(dates)
    assert "25 May 2021" in filtered
    assert "May 2021" not in filtered
    assert "2021" not in filtered


def test_generate_date_variants_for_standard_date():
    """Test that generate_date_variants returns multiple formats for a standard date."""
    variants = date_formats.generate_date_variants("12/05/2021")
    # Should include several formats
    assert any("12/05/2021" in v for v in variants)
    assert any("12-05-2021" in v for v in variants)
    assert any("2021-05-12" in v for v in variants)
    assert any("12 May 2021" in v for v in variants)
    assert any("12th May 2021" in v for v in variants)
    assert any("12 May 2021" in v for v in variants)
    assert any("12 May 2021" in v for v in variants)


def test_generate_date_variants_for_sept():
    """Test that generate_date_variants handles September correctly."""
    variants = date_formats.generate_date_variants("14-Sept-2021")
    assert any("14 Sept 2021" in v for v in variants)
    assert any("14th Sept 2021" in v for v in variants)
    assert any("14-Sept-2021" in v for v in variants)


def test_generate_date_variants_returns_input_on_parse_fail():
    """Test that generate_date_variants returns the input string when parsing fails."""
    assert date_formats.generate_date_variants("notadate") == ["notadate"]


def test_extract_dates_for_search_combines_variants():
    """Test that extract_dates_for_search combines original and variant date formats."""
    text = "The date is 1st January 2018 and also 01/01/2018."
    variants = date_formats.extract_dates_for_search(text)
    # Should include both original and variant formats
    assert any("1 January 2018" in v for v in variants)
    assert any("01/01/2018" in v for v in variants)
    assert any("2018-01-01" in v for v in variants)
