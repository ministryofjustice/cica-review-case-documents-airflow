"""Tests for the date extraction module."""

from unittest.mock import patch

from ingestion_pipeline.date_extraction.extractor import extract_and_clean, extract_dates, remove_dates

# ── A: Month-name formats ────────────────────────────────────────────────────


class TestMonthNameFormats:
    """Date patterns using written month names."""

    def test_day_dash_monthname_dash_four_digit_year(self):
        assert extract_dates("Seen on 25-Aug-2021 by GP") == ["2021-08-25"]

    def test_day_dash_full_monthname_dash_four_digit_year(self):
        assert extract_dates("Letter dated 30-July-2021") == ["2021-07-30"]

    def test_day_space_abbrev_month_space_four_digit_year(self):
        assert extract_dates("4 Aug 2021 clinic visit") == ["2021-08-04"]

    def test_day_space_abbrev_month_space_two_digit_year(self):
        assert extract_dates("29 Jul 21 follow-up") == ["2021-07-29"]

    def test_day_space_full_month_space_four_digit_year(self):
        assert extract_dates("4 August 2021 referral") == ["2021-08-04"]

    def test_ordinal_day_space_full_month_space_four_digit_year(self):
        assert extract_dates("4th August 2021") == ["2021-08-04"]

    def test_ordinal_st(self):
        assert extract_dates("1st January 2020") == ["2020-01-01"]

    def test_ordinal_nd(self):
        assert extract_dates("2nd February 2019") == ["2019-02-02"]

    def test_ordinal_rd(self):
        assert extract_dates("3rd March 2018") == ["2018-03-03"]

    def test_day_month_comma_year(self):
        assert extract_dates("20 July, 2021 report") == ["2021-07-20"]

    def test_day_month_year_with_time_component_ignored(self):
        assert extract_dates("20 Jul 2021 15:00 appointment") == ["2021-07-20"]

    def test_monthname_day_year(self):
        assert extract_dates("August 4, 2021") == ["2021-08-04"]

    def test_monthname_day_year_no_comma(self):
        assert extract_dates("August 4 2021") == ["2021-08-04"]


# ── B: Numeric UK formats ────────────────────────────────────────────────────


class TestNumericUKFormats:
    """DD/MM/YYYY and similar numeric patterns with UK day-first convention."""

    def test_slash_four_digit_year(self):
        assert extract_dates("Date: 04/08/2021") == ["2021-08-04"]

    def test_slash_two_digit_year(self):
        assert extract_dates("4/8/21") == ["2021-08-04"]

    def test_dash_four_digit_year(self):
        assert extract_dates("04-08-2021") == ["2021-08-04"]

    def test_dash_two_digit_year(self):
        assert extract_dates("4-8-21") == ["2021-08-04"]

    def test_dot_two_digit_year(self):
        assert extract_dates("04.08.21") == ["2021-08-04"]

    def test_dot_four_digit_year(self):
        assert extract_dates("04.08.2021") == ["2021-08-04"]


# ── C: ISO-like / system formats ─────────────────────────────────────────────


class TestISOFormats:
    """YYYY-MM-DD, YYYY/MM/DD, and compact YYYYMMDD."""

    def test_iso_dash(self):
        assert extract_dates("2021-08-04") == ["2021-08-04"]

    def test_iso_slash(self):
        assert extract_dates("2021/08/04") == ["2021-08-04"]

    def test_compact_yyyymmdd(self):
        assert extract_dates("Reference 20210720 created") == ["2021-07-20"]

    def test_compact_does_not_match_longer_digit_run(self):
        """An 8-digit sequence inside a longer number must not match."""
        assert extract_dates("ID: 282107202") == []

    def test_compact_month_boundaries(self):
        assert extract_dates("20210101") == ["2021-01-01"]
        assert extract_dates("20211231") == ["2021-12-31"]
        assert extract_dates("20211301") == []  # month 13 invalid


# ── D: Space-only numeric formats ────────────────────────────────────────────


class TestSpaceNumericFormats:
    """Dates separated only by spaces, common in GP notes."""

    def test_single_digit_day_month_two_digit_year(self):
        assert extract_dates("4 8 21") == ["2021-08-04"]

    def test_zero_padded_four_digit_year(self):
        assert extract_dates("04 08 2021") == ["2021-08-04"]

    def test_mixed_padding(self):
        assert extract_dates("20 7 2021") == ["2021-07-20"]

    def test_space_numeric_not_matched_inside_sentence(self):
        """Words adjacent to the digits should prevent matching."""
        assert extract_dates("abc4 8 21def") == []


# ── E: Yearless formats ──────────────────────────────────────────────────────


class TestYearlessFormats:
    """Day MonthName without a year component."""

    def test_yearless_rejected_by_default(self):
        assert extract_dates("4 Aug something") == []

    @patch("ingestion_pipeline.date_extraction.extractor.datetime")
    def test_yearless_accepted_when_enabled(self, mock_dt):
        mock_dt.now.return_value.year = 2025
        assert extract_dates("4 Aug", allow_yearless=True) == ["2025-08-04"]

    @patch("ingestion_pipeline.date_extraction.extractor.datetime")
    def test_yearless_full_month_name(self, mock_dt):
        mock_dt.now.return_value.year = 2025
        assert extract_dates("20 July", allow_yearless=True) == ["2025-07-20"]


# ── F: False positive avoidance ──────────────────────────────────────────────


class TestFalsePositiveAvoidance:
    """NHS numbers, hospital IDs, and out-of-range values must be skipped."""

    def test_nhs_number_eight_digits_rejected(self):
        assert extract_dates("28083201") == []

    def test_nhs_number_eight_digits_rejected_2(self):
        assert extract_dates("20122003") == []

    def test_short_six_digit_id_rejected(self):
        assert extract_dates("302020") == []

    def test_year_below_1900_rejected(self):
        assert extract_dates("01/01/1899") == []

    def test_year_above_2060_rejected(self):
        assert extract_dates("01/01/2061") == []

    def test_month_13_rejected(self):
        assert extract_dates("01/13/2021") == []

    def test_day_32_rejected(self):
        assert extract_dates("32/01/2021") == []

    def test_feb_30_rejected(self):
        assert extract_dates("30/02/2021") == []


# ── Short year normalisation ─────────────────────────────────────────────────


class TestShortYearNormalisation:
    """Two-digit year expansion: 01–limit → 20YY, limit+1–99 → 19YY, 00 → 2000."""

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_short_year_within_limit(self, _mock):
        assert extract_dates("4/8/21") == ["2021-08-04"]

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_short_year_05(self, _mock):
        assert extract_dates("29 Jul 05") == ["2005-07-29"]

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_short_year_00_becomes_2000(self, _mock):
        assert extract_dates("04-08-00") == ["2000-08-04"]

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_short_year_above_limit_becomes_19yy(self, _mock):
        assert extract_dates("30/07/27") == ["1927-07-30"]

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_short_year_98_becomes_1998(self, _mock):
        assert extract_dates("15-Sept-98") == ["1998-09-15"]

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_short_year_99_becomes_1999(self, _mock):
        assert extract_dates("31/12/99") == ["1999-12-31"]

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_short_year_at_limit_accepted(self, _mock):
        assert extract_dates("01/01/26") == ["2026-01-01"]


# ── Integration: multi-date extraction ────────────────────────────────────────


class TestMultiDateExtraction:
    """End-to-end extraction of multiple dates from realistic text blocks."""

    @patch("ingestion_pipeline.date_extraction.extractor._current_two_digit_year_limit", return_value=26)
    def test_nhs_trust_text_block(self, _mock):
        text = (
            "NHS Foundation Trust\n"
            "25-Aug-2021 consultation\n"
            "04-Aug-2021 blood test\n"
            "30-July-2021 referral\n"
            "20 Jul 2021 15:00 appointment\n"
            "29-Jul-21 follow-up\n"
        )
        assert extract_dates(text) == [
            "2021-07-20",
            "2021-07-29",
            "2021-07-30",
            "2021-08-04",
            "2021-08-25",
        ]

    def test_mixed_format_text(self):
        text = "Admitted 2021-08-04, discharged 04/08/2021, reviewed 4 Aug 2021"
        result = extract_dates(text)
        assert result == ["2021-08-04"]

    def test_returns_unique_sorted(self):
        text = "01/01/2020 01/01/2020 31/12/2019"
        assert extract_dates(text) == ["2019-12-31", "2020-01-01"]

    def test_empty_string(self):
        assert extract_dates("") == []

    def test_no_dates_in_text(self):
        assert extract_dates("Patient presented with mild symptoms.") == []


# ── remove_dates ──────────────────────────────────────────────────────────────


class TestRemoveDates:
    """Verify date substrings are stripped and whitespace normalised."""

    def test_removes_iso_date(self):
        result = remove_dates("Seen on 2021-08-04 at clinic")
        assert "2021-08-04" not in result
        assert "  " not in result

    def test_removes_uk_numeric(self):
        result = remove_dates("Date: 04/08/2021 was entered")
        assert "04/08/2021" not in result

    def test_removes_month_name_format(self):
        result = remove_dates("Letter 25-Aug-2021 received")
        assert "25-Aug-2021" not in result

    def test_normalises_whitespace_after_removal(self):
        result = remove_dates("A 2021-08-04 B")
        assert result == "A B"

    def test_empty_string(self):
        assert remove_dates("") == ""


# ── extract_and_clean ─────────────────────────────────────────────────────────


class TestExtractAndClean:
    """Integration with page_chunk dict structure."""

    def test_adds_dates_field(self):
        chunk = {"chunk_text": "Seen 25-Aug-2021", "chunk_id": "abc"}
        result = extract_and_clean(chunk)
        assert result["dates"] == ["2021-08-25"]
        assert result["chunk_text"] == "Seen 25-Aug-2021"

    def test_returns_same_dict_reference(self):
        chunk = {"chunk_text": "No dates here"}
        result = extract_and_clean(chunk)
        assert result is chunk
        assert result["dates"] == []

    def test_preserves_existing_fields(self):
        chunk = {"chunk_text": "01/01/2020", "chunk_id": "x", "embedding": [0.1]}
        result = extract_and_clean(chunk)
        assert result["chunk_id"] == "x"
        assert result["embedding"] == [0.1]
        assert result["dates"] == ["2020-01-01"]

    def test_multiple_chunks_independently(self):
        chunks = [
            {"chunk_text": "25-Aug-2021 note"},
            {"chunk_text": "2022-01-15 record"},
        ]
        results = [extract_and_clean(c) for c in chunks]
        assert results[0]["dates"] == ["2021-08-25"]
        assert results[1]["dates"] == ["2022-01-15"]

    def test_missing_chunk_text_key(self):
        chunk = {"other_field": "value"}
        result = extract_and_clean(chunk)
        assert result["dates"] == []

    @patch("ingestion_pipeline.date_extraction.extractor.datetime")
    def test_yearless_toggle_forwarded(self, mock_dt):
        mock_dt.now.return_value.year = 2025
        chunk = {"chunk_text": "4 Aug meeting"}
        result = extract_and_clean(chunk, allow_yearless=True)
        assert result["dates"] == ["2025-08-04"]


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Boundary and unusual input handling."""

    def test_leap_year_feb_29_valid(self):
        assert extract_dates("29/02/2020") == ["2020-02-29"]

    def test_non_leap_year_feb_29_rejected(self):
        assert extract_dates("29/02/2021") == []

    def test_date_at_start_of_string(self):
        assert extract_dates("2021-08-04 start") == ["2021-08-04"]

    def test_date_at_end_of_string(self):
        assert extract_dates("end 2021-08-04") == ["2021-08-04"]

    def test_adjacent_dates(self):
        text = "2021-01-01 2021-01-02"
        assert extract_dates(text) == ["2021-01-01", "2021-01-02"]

    def test_september_abbreviated_as_sept(self):
        assert extract_dates("15-Sept-2021") == ["2021-09-15"]

    def test_compact_date_not_confused_with_nhs_number_20122003(self):
        # 20122003: year=2012, month=20 → invalid month → rejected
        assert extract_dates("20122003") == []

    def test_compact_28083201(self):
        # 28083201: year=2808, month=32 → invalid → rejected
        assert extract_dates("28083201") == []

    def test_overlapping_pattern_claimed_by_higher_priority(self):
        """25-Aug-2021 is claimed by PAT_DAY_MNAME_YEAR_SEP; the numeric
        pattern should not re-match the same span.
        """
        result = extract_dates("25-Aug-2021")
        assert result == ["2021-08-25"]

    def test_iso_date_claims_span_before_numeric_uk(self):
        """2021-08-04 is claimed by PAT_ISO, so PAT_NUMERIC_UK skips it."""
        assert extract_dates("2021-08-04") == ["2021-08-04"]

    def test_compact_date_claims_span_before_numeric_uk(self):
        """20210804 is claimed by PAT_COMPACT, no duplicate from other patterns."""
        assert extract_dates("20210804") == ["2021-08-04"]

    def test_day_space_month_year_claims_before_space_numeric(self):
        """'4 Aug 2021' is claimed by month-name pattern, space-numeric skips."""
        assert extract_dates("4 Aug 2021") == ["2021-08-04"]

    def test_monthname_day_year_claims_before_others(self):
        """'August 4 2021' is claimed by PAT_MNAME_DAY_YEAR."""
        assert extract_dates("August 4 2021") == ["2021-08-04"]
