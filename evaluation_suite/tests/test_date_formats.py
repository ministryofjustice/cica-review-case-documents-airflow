"""Unit tests for date_formats.py.

Tests mirror the JavaScript implementation behavior for consistency
between frontend and backend date handling.
"""

from evaluation_suite.search_evaluation import date_formats


class TestIsDateSearch:
    """Tests for is_date_search function."""

    def test_numeric_formats(self):
        """Test detection of numeric date formats."""
        assert date_formats.is_date_search("12/05/2021")
        assert date_formats.is_date_search("12-05-2021")
        assert date_formats.is_date_search("12.05.2021")
        assert date_formats.is_date_search("1/2/24")
        assert date_formats.is_date_search("01-02-2024")

    def test_iso_format(self):
        """Test detection of ISO date format (yyyy-mm-dd)."""
        assert date_formats.is_date_search("2021-05-12")
        assert date_formats.is_date_search("2024-01-01")

    def test_month_name_formats(self):
        """Test detection of month name formats."""
        assert date_formats.is_date_search("12 January 2021")
        assert date_formats.is_date_search("12 Jan 2021")
        assert date_formats.is_date_search("5 September 2024")
        assert date_formats.is_date_search("12 Sept 2021")

    def test_ordinal_formats(self):
        """Test detection of ordinal day formats."""
        assert date_formats.is_date_search("1st Jan 2024")
        assert date_formats.is_date_search("21st February 2024")
        assert date_formats.is_date_search("2nd March 2024")
        assert date_formats.is_date_search("3rd April 2024")

    def test_month_year_only(self):
        """Test detection of month-year only formats."""
        assert date_formats.is_date_search("January 2024")
        assert date_formats.is_date_search("Jan 2024")
        assert date_formats.is_date_search("Sept 2021")

    def test_non_dates_return_false(self):
        """Test that non-date strings return False."""
        assert not date_formats.is_date_search("hello world")
        assert not date_formats.is_date_search("12 monkeys")
        assert not date_formats.is_date_search("Mayday")
        assert not date_formats.is_date_search("17102024")  # No separators


class TestExtractDatesFromSearchString:
    """Tests for extract_dates_from_search_string function."""

    def test_extracts_numeric_dates(self):
        """Test extraction of numeric format dates."""
        result = date_formats.extract_dates_from_search_string("report 12/05/2024 meeting")
        assert result.dates == ["12/05/2024"]
        assert result.remaining_text == "report meeting"
        assert result.matched_patterns == [{"numeric": True}]

    def test_extracts_multiple_dates(self):
        """Test extraction of multiple dates."""
        result = date_formats.extract_dates_from_search_string("from 01/01/2024 to 31/12/2024")
        assert len(result.dates) == 2
        assert "01/01/2024" in result.dates
        assert "31/12/2024" in result.dates
        assert result.remaining_text == "from to"

    def test_extracts_day_month_year_format(self):
        """Test extraction of day-month-year format with month name."""
        result = date_formats.extract_dates_from_search_string("Appointment 1st Jan 2024 scheduled")
        assert result.dates == ["1st Jan 2024"]
        assert result.remaining_text == "Appointment scheduled"
        assert result.matched_patterns == [{"dayMonthYear": True}]

    def test_extracts_month_year_only(self):
        """Test extraction of month-year only format."""
        result = date_formats.extract_dates_from_search_string("review for January 2024")
        assert result.dates == ["January 2024"]
        assert result.remaining_text == "review for"
        assert result.matched_patterns == [{"monthYear": True}]

    def test_extracts_iso_format(self):
        """Test extraction of ISO format (yyyy-mm-dd)."""
        result = date_formats.extract_dates_from_search_string("deadline 2024-05-12 urgent")
        assert result.dates == ["2024-05-12"]
        assert result.remaining_text == "deadline urgent"
        assert result.matched_patterns == [{"yearMonthDay": True}]

    def test_no_dates_returns_empty(self):
        """Test that no dates returns empty list and original text."""
        result = date_formats.extract_dates_from_search_string("no dates here")
        assert result.dates == []
        assert result.remaining_text == "no dates here"
        assert result.matched_patterns == []

    def test_handles_unicode_separators(self):
        """Test handling of unicode dash separators."""
        # Unicode en-dash
        result = date_formats.extract_dates_from_search_string("date 12–05–2024 here")
        assert len(result.dates) == 1
        assert result.matched_patterns == [{"numeric": True}]


class TestGenerateDateFormatVariants:
    """Tests for generate_date_format_variants function."""

    def test_numeric_date_generates_variants(self):
        """Test that numeric dates generate expected variants."""
        variants = date_formats.generate_date_format_variants("12/05/2024", {"numeric": True})
        # Numeric patterns generate numeric format variants only
        assert len(variants) > 0
        # Should include various numeric formats
        assert any("12" in v and "5" in v and "2024" in v for v in variants)
        assert any("12" in v and "05" in v for v in variants)

    def test_day_month_year_generates_variants(self):
        """Test that day-month-year dates generate variants."""
        variants = date_formats.generate_date_format_variants("1st Jan 2024", {"dayMonthYear": True})
        assert len(variants) > 0
        # Should include full month name variants
        assert any("January" in v for v in variants)
        assert any("Jan" in v for v in variants)

    def test_month_year_generates_variants(self):
        """Test that month-year dates generate variants."""
        variants = date_formats.generate_date_format_variants("January 2024", {"monthYear": True})
        assert len(variants) > 0
        assert any("Jan" in v for v in variants)
        assert any("January" in v for v in variants)

    def test_september_includes_sept_variant(self):
        """Test that September dates include Sept variant."""
        variants = date_formats.generate_date_format_variants("14 September 2021", {"dayMonthYear": True})
        assert any("Sept" in v for v in variants)
        assert any("Sep" in v for v in variants)

    def test_invalid_date_returns_empty(self):
        """Test that invalid dates return empty list."""
        variants = date_formats.generate_date_format_variants("notadate", {})
        assert variants == []

    def test_variants_are_space_separated(self):
        """Test that all variants use space separators (matching JS behavior)."""
        variants = date_formats.generate_date_format_variants("12/05/2024", {"numeric": True})
        for variant in variants:
            # Should not contain slashes, hyphens, or dots as separators
            assert "/" not in variant
            assert "-" not in variant
            assert "." not in variant


class TestNormaliseDateString:
    """Tests for normalise_date_string function."""

    def test_strips_ordinal_suffixes(self):
        """Test that ordinal suffixes are stripped."""
        assert date_formats.normalise_date_string("1st") == "1"
        assert date_formats.normalise_date_string("2nd") == "2"
        assert date_formats.normalise_date_string("3rd") == "3"
        assert date_formats.normalise_date_string("4th") == "4"
        assert date_formats.normalise_date_string("21st") == "21"

    def test_replaces_delimiters_with_spaces(self):
        """Test that delimiters are replaced with spaces."""
        assert date_formats.normalise_date_string("12/05/2024") == "12 05 2024"
        assert date_formats.normalise_date_string("12-05-2024") == "12 05 2024"
        assert date_formats.normalise_date_string("12.05.2024") == "12 05 2024"

    def test_normalises_sep_to_sept(self):
        """Test that Sep is normalised to Sept for parsing."""
        assert "Sept" in date_formats.normalise_date_string("12 Sep 2024")

    def test_collapses_multiple_spaces(self):
        """Test that multiple spaces are collapsed."""
        assert date_formats.normalise_date_string("12  /  05  /  2024") == "12 05 2024"


class TestIntegration:
    """Integration tests combining extraction and variant generation."""

    def test_full_workflow_numeric_date(self):
        """Test full workflow with numeric date."""
        result = date_formats.extract_dates_from_search_string("report 12/05/2024 meeting")
        assert len(result.dates) == 1
        assert result.matched_patterns == [{"numeric": True}]

        variants = date_formats.generate_date_format_variants(result.dates[0], result.matched_patterns[0])
        # Numeric pattern generates numeric variants only (matching JS behavior)
        assert len(variants) > 0
        # Should include various numeric space-separated formats
        assert any("12" in v and "5" in v and "2024" in v for v in variants)

    def test_full_workflow_preserves_remaining_text(self):
        """Test that remaining text is preserved correctly."""
        result = date_formats.extract_dates_from_search_string("injury on 12/05/2024 to head")
        assert result.remaining_text == "injury on to head"


class TestGenerateMonthYearVariants:
    """Tests for generate_month_year_variants function."""

    def test_generates_month_year_from_full_date(self):
        """Test that month-year variants are generated from full date."""
        variants = date_formats.generate_month_year_variants("15/12/2022", {"numeric": True})
        assert len(variants) > 0
        # Should include text month variants
        assert any("December" in v for v in variants)
        assert any("Dec" in v for v in variants)
        # Should include numeric month/year
        assert any("12/22" in v for v in variants)

    def test_generates_from_day_month_year(self):
        """Test month-year variants from day-month-year format."""
        variants = date_formats.generate_month_year_variants("15 December 2022", {"dayMonthYear": True})
        assert len(variants) > 0
        assert any("December 2022" in v or "December 22" in v for v in variants)
        assert any("Dec 2022" in v or "Dec 22" in v for v in variants)

    def test_returns_empty_for_month_year_input(self):
        """Test that month-year only input returns empty (no partial for partial)."""
        variants = date_formats.generate_month_year_variants("December 2022", {"monthYear": True})
        assert variants == []

    def test_september_includes_sept_variant(self):
        """Test that September dates include Sept variant in month-year."""
        variants = date_formats.generate_month_year_variants("15/09/2022", {"numeric": True})
        assert any("Sept" in v for v in variants)
        assert any("Sep" in v for v in variants)

    def test_invalid_date_returns_empty(self):
        """Test that invalid dates return empty list."""
        variants = date_formats.generate_month_year_variants("notadate", {})
        assert variants == []
