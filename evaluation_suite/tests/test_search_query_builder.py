"""Unit tests for search_query_builder.py."""

from unittest.mock import patch

from evaluation_suite.search_evaluation import search_query_builder
from evaluation_suite.search_evaluation.date_formats import DateExtractionResult


def sample_hits():
    """Helper to provide sample OpenSearch hits for testing."""
    return [
        {
            "_id": "c1",
            "_score": 10.0,
            "_source": {
                "chunk_text": "fractured arm",
                "page_number": 1,
                "case_ref": "REF001",
                "document_id": "doc1",
            },
        },
        {
            "_id": "c2",
            "_score": 5.0,
            "_source": {"chunk_text": "injury report", "page_number": 2, "case_ref": "REF002", "document_id": "doc2"},
        },
        {
            "_id": "c3",
            "_score": 2.0,
            "_source": {
                "chunk_text": "no relevant info",
                "page_number": 3,
                "case_ref": "REF003",
                "document_id": "doc3",
            },
        },
    ]


# --- Tests for _build_hybrid_clauses ---


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_hybrid_clauses_all_boosts_active(mock_settings):
    """Test _build_hybrid_clauses returns all clauses when all boosts are active."""
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 1.0
    mock_settings.FUZZY_BOOST = 1.0
    mock_settings.WILDCARD_BOOST = 1.0
    mock_settings.SEMANTIC_BOOST = 1.0
    mock_settings.FUZZINESS = "AUTO"
    mock_settings.MAX_EXPANSIONS = 10
    mock_settings.PREFIX_LENGTH = 1

    clauses = search_query_builder._build_hybrid_clauses("test", [0.1, 0.2], result_size=5)
    clause_keys = [list(c.keys())[0] for c in clauses]

    assert "match" in clause_keys
    assert "fuzzy" in clause_keys
    assert "wildcard" in clause_keys
    assert "knn" in clause_keys
    assert len(clauses) == 5


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_hybrid_clauses_all_boosts_zero(mock_settings):
    """Test _build_hybrid_clauses returns empty list when all boosts are zero."""
    mock_settings.KEYWORD_BOOST = 0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0

    clauses = search_query_builder._build_hybrid_clauses("test", [0.1, 0.2], result_size=5)
    assert clauses == []


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_hybrid_clauses_keyword_only(mock_settings):
    """Test _build_hybrid_clauses returns only keyword clause when only KEYWORD_BOOST is set."""
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0

    clauses = search_query_builder._build_hybrid_clauses("test", [0.1, 0.2], result_size=5)
    assert len(clauses) == 1
    assert "match" in clauses[0]


# --- Tests for create_hybrid_query ---


@patch("evaluation_suite.search_evaluation.search_query_builder.generate_date_format_variants")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_with_dates(mock_settings, mock_extract, mock_variants):
    """Test create_hybrid_query uses match_phrase when dates are detected."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.DATE_QUERY_BOOST = 2.0
    mock_settings.CASE_FILTER = "TEST-123"

    # Mock the extraction result
    mock_extract.return_value = DateExtractionResult(
        dates=["12/05/2021"], remaining_text="", matched_patterns=[{"numeric": True}]
    )
    mock_variants.return_value = ["12 05 2021", "12 May 2021"]

    query = search_query_builder.create_hybrid_query("12/05/2021", [0.1, 0.2], result_size=5)

    assert "bool" in query["query"]
    clauses = query["query"]["bool"]["should"]
    # Should have match_phrase clauses for date variants
    match_phrase_clauses = [c for c in clauses if "match_phrase" in c]
    assert len(match_phrase_clauses) == 2
    assert query["query"]["bool"].get("minimum_should_match") == 1


@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_no_dates_simple_mode(mock_settings, mock_extract):
    """Test create_hybrid_query uses flat hybrid clauses in simple mode when no dates detected."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.QUERY_MODE = "simple"
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0
    mock_settings.CASE_FILTER = "TEST-123"

    mock_extract.return_value = DateExtractionResult(dates=[], remaining_text="fracture", matched_patterns=[])

    query = search_query_builder.create_hybrid_query("fracture", [0.1, 0.2], result_size=5)

    assert "bool" in query["query"]
    clauses = query["query"]["bool"]["should"]
    assert len(clauses) == 1
    assert "match" in clauses[0]
    assert "minimum_should_match" not in query["query"]["bool"]


@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_no_dates_combined_mode(mock_settings, mock_extract):
    """Test create_hybrid_query uses tiered text query in combined mode when no dates detected."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.QUERY_MODE = "combined"
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0
    mock_settings.TEXT_TIER1_BOOST = 3
    mock_settings.TEXT_TIER2_BOOST = 2
    mock_settings.TEXT_TIER3_BOOST = 1
    mock_settings.TEXT_MINIMUM_SHOULD_MATCH = "55%"
    mock_settings.CASE_FILTER = "TEST-123"

    mock_extract.return_value = DateExtractionResult(
        dates=[], remaining_text="head injury treatment", matched_patterns=[]
    )

    query = search_query_builder.create_hybrid_query("head injury treatment", [0.1, 0.2], result_size=5)

    clauses = query["query"]["bool"]["should"]
    assert len(clauses) == 3  # Three tiers

    # Tier 1: operator "and"
    assert clauses[0]["match"]["chunk_text"]["operator"] == "and"
    assert clauses[0]["match"]["chunk_text"]["boost"] == 3

    # Tier 2: minimum_should_match
    assert clauses[1]["match"]["chunk_text"]["minimum_should_match"] == "55%"
    assert clauses[1]["match"]["chunk_text"]["boost"] == 2

    # Tier 3: operator "or"
    assert clauses[2]["match"]["chunk_text"]["operator"] == "or"
    assert clauses[2]["match"]["chunk_text"]["boost"] == 1


@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_date_detection_disabled(mock_settings, mock_extract):
    """Test create_hybrid_query skips date detection when DATE_FORMAT_DETECTION is False."""
    mock_settings.DATE_FORMAT_DETECTION = False
    mock_settings.QUERY_MODE = "simple"
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0
    mock_settings.CASE_FILTER = "TEST-123"

    search_query_builder.create_hybrid_query("12/05/2021", [0.1, 0.2], result_size=5)

    mock_extract.assert_not_called()


@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_contains_source_fields(mock_settings, mock_extract):
    """Test create_hybrid_query always includes correct _source fields."""
    mock_settings.DATE_FORMAT_DETECTION = False
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0
    mock_settings.CASE_FILTER = "TEST-123"

    query = search_query_builder.create_hybrid_query("fracture", [0.1, 0.2], result_size=5)

    assert "_source" in query
    assert "chunk_text" in query["_source"]
    assert "document_id" in query["_source"]
    assert "page_number" in query["_source"]
    assert "case_ref" in query["_source"]


@patch("evaluation_suite.search_evaluation.search_query_builder.generate_date_format_variants")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_with_remaining_text(mock_settings, mock_extract, mock_variants):
    """Test create_hybrid_query includes match clause for remaining text."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.DATE_QUERY_BOOST = 2.0
    mock_settings.CASE_FILTER = "TEST-123"

    mock_extract.return_value = DateExtractionResult(
        dates=["12/05/2021"], remaining_text="injury report", matched_patterns=[{"numeric": True}]
    )
    mock_variants.return_value = ["12 May 2021"]

    query = search_query_builder.create_hybrid_query("injury report 12/05/2021", [0.1, 0.2], result_size=5)

    clauses = query["query"]["bool"]["should"]
    # Should have match_phrase for date + match for remaining text
    match_clauses = [c for c in clauses if "match" in c and "match_phrase" not in c]
    assert len(match_clauses) == 1
    assert match_clauses[0]["match"]["chunk_text"]["query"] == "injury report"
    assert match_clauses[0]["match"]["chunk_text"]["operator"] == "or"


# --- Tests for apply_adaptive_score_filter ---


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_above_threshold(mock_settings):
    """Test apply_adaptive_score_filter returns only hits above threshold."""
    mock_settings.ADAPTIVE_SCORE_FILTER = False
    hits = sample_hits()

    filtered, effective_filter, semantic_added = search_query_builder.apply_adaptive_score_filter(
        hits, score_filter=6.0
    )

    assert len(filtered) == 1
    assert filtered[0]["_id"] == "c1"
    assert effective_filter == 6.0
    assert semantic_added == 0


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_no_hits_above_threshold(mock_settings):
    """Test apply_adaptive_score_filter returns empty when no hits above threshold."""
    mock_settings.ADAPTIVE_SCORE_FILTER = False
    hits = sample_hits()

    filtered, _, semantic_added = search_query_builder.apply_adaptive_score_filter(hits, score_filter=100.0)

    assert filtered == []
    assert semantic_added == 0


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_fallback_adds_semantic(mock_settings):
    """Test apply_adaptive_score_filter supplements with semantic hits when below MIN_RESULTS."""
    mock_settings.ADAPTIVE_SCORE_FILTER = True
    mock_settings.MIN_RESULTS_BEFORE_FALLBACK = 2
    mock_settings.SEMANTIC_SCORE_FILTER = 1.0
    mock_settings.MAX_SEMANTIC_RESULTS = 5
    hits = sample_hits()

    filtered, _, semantic_added = search_query_builder.apply_adaptive_score_filter(hits, score_filter=6.0)

    assert semantic_added > 0
    assert any(h["_id"] == "c1" for h in filtered)


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_no_duplicates_in_fallback(mock_settings):
    """Test apply_adaptive_score_filter does not add duplicate hits in fallback."""
    mock_settings.ADAPTIVE_SCORE_FILTER = True
    mock_settings.MIN_RESULTS_BEFORE_FALLBACK = 5
    mock_settings.SEMANTIC_SCORE_FILTER = 1.0
    mock_settings.MAX_SEMANTIC_RESULTS = 10
    hits = sample_hits()

    filtered, _, _ = search_query_builder.apply_adaptive_score_filter(hits, score_filter=6.0)
    ids = [h["_id"] for h in filtered]

    assert len(ids) == len(set(ids))


# --- Tests for combined query mode ---


@patch("evaluation_suite.search_evaluation.search_query_builder.generate_month_year_variants")
@patch("evaluation_suite.search_evaluation.search_query_builder.generate_date_format_variants")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_combined_mode(mock_settings, mock_extract, mock_variants, mock_partial):
    """Test create_hybrid_query in combined mode creates tiered query."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.QUERY_MODE = "combined"
    mock_settings.DATE_QUERY_BOOST = 2.0
    mock_settings.CASE_FILTER = "TEST-123"
    mock_settings.COMBINED_PHRASE_BOOST = 6
    mock_settings.COMBINED_PHRASE_SLOP = 1
    mock_settings.COMBINED_EXACT_DATE_BOOST = 10
    mock_settings.COMBINED_PARTIAL_DATE_BOOST = 6
    mock_settings.COMBINED_TIER1_BOOST = 3
    mock_settings.COMBINED_TIER2_BOOST = 2
    mock_settings.TEXT_MINIMUM_SHOULD_MATCH = "55%"

    mock_extract.return_value = DateExtractionResult(
        dates=["15/12/2022"], remaining_text="unable to work", matched_patterns=[{"numeric": True}]
    )
    mock_variants.return_value = ["15 December 2022", "15 Dec 2022"]
    mock_partial.return_value = ["December 2022", "Dec 2022", "12/22"]

    query = search_query_builder.create_hybrid_query("unable to work 15/12/2022", [0.1, 0.2], result_size=5)

    clauses = query["query"]["bool"]["should"]

    # Should have 5 clauses: tier1 + tier2 + 2 date variant match_phrase + 1 text match
    assert len(clauses) == 5

    # Tier 1: bool with must containing phrase + exact dates
    tier1 = clauses[0]
    assert "bool" in tier1
    assert "must" in tier1["bool"]
    assert tier1["bool"]["boost"] == 3  # COMBINED_TIER1_BOOST

    # Tier 2: bool with must containing partial text match + exact dates
    tier2 = clauses[1]
    assert "bool" in tier2
    assert "must" in tier2["bool"]
    assert tier2["bool"]["boost"] == 2  # COMBINED_TIER2_BOOST
    # Text part uses match (not match_phrase) with minimum_should_match
    text_clause = tier2["bool"]["must"][0]
    assert "match" in text_clause
    assert "minimum_should_match" in text_clause["match"]["chunk_text"]

    # Tier 3 fallback: date variant match_phrase clauses + remaining text match
    tier3_clauses = clauses[2:]
    match_phrase_clauses = [c for c in tier3_clauses if "match_phrase" in c]
    match_clauses = [c for c in tier3_clauses if "match" in c and "match_phrase" not in c]
    assert len(match_phrase_clauses) == 2  # Two date variants
    assert len(match_clauses) == 1  # Remaining text
    assert match_clauses[0]["match"]["chunk_text"]["operator"] == "or"


@patch("evaluation_suite.search_evaluation.search_query_builder.generate_date_format_variants")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_simple_mode_default(mock_settings, mock_extract, mock_variants):
    """Test create_hybrid_query uses simple mode by default (flat OR query)."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.QUERY_MODE = "simple"
    mock_settings.DATE_QUERY_BOOST = 2.0
    mock_settings.CASE_FILTER = "TEST-123"

    mock_extract.return_value = DateExtractionResult(
        dates=["15/12/2022"], remaining_text="unable to work", matched_patterns=[{"numeric": True}]
    )
    mock_variants.return_value = ["15 December 2022", "15 Dec 2022"]

    query = search_query_builder.create_hybrid_query("unable to work 15/12/2022", [0.1, 0.2], result_size=5)

    clauses = query["query"]["bool"]["should"]

    # Simple mode: flat match_phrase + match clauses
    match_phrase_clauses = [c for c in clauses if "match_phrase" in c]
    match_clauses = [c for c in clauses if "match" in c and "match_phrase" not in c]

    assert len(match_phrase_clauses) == 2  # Two date variants
    assert len(match_clauses) == 1  # Remaining text


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_combined_date_query_structure(mock_settings):
    """Test _build_combined_date_query creates correct structure."""
    mock_settings.COMBINED_PHRASE_BOOST = 6
    mock_settings.COMBINED_PHRASE_SLOP = 1
    mock_settings.COMBINED_EXACT_DATE_BOOST = 10
    mock_settings.COMBINED_PARTIAL_DATE_BOOST = 6
    mock_settings.COMBINED_TIER1_BOOST = 3
    mock_settings.COMBINED_TIER2_BOOST = 2
    mock_settings.TEXT_MINIMUM_SHOULD_MATCH = "55%"
    mock_settings.DATE_QUERY_BOOST = 2.0

    clauses = search_query_builder._build_combined_date_query(
        remaining_text="unable to work",
        exact_variants=["15 December 2022"],
        partial_variants=["December 2022"],
        query_text="unable to work 15/12/2022",
    )

    # Should have 4 clauses: tier1 + tier2 + 1 date variant match_phrase + 1 text match
    assert len(clauses) == 4

    # Verify tier 1 structure: phrase + exact date
    tier1 = clauses[0]["bool"]
    assert "must" in tier1
    assert len(tier1["must"]) == 2  # phrase + date bool
    assert tier1["must"][0]["match_phrase"]["chunk_text"]["query"] == "unable to work"
    assert tier1["must"][0]["match_phrase"]["chunk_text"]["slop"] == 1

    # Verify tier 2 structure: partial text match + exact date
    tier2 = clauses[1]["bool"]
    assert "must" in tier2
    assert len(tier2["must"]) == 2  # match + date bool
    text_match = tier2["must"][0]["match"]["chunk_text"]
    assert text_match["query"] == "unable to work"
    assert "minimum_should_match" in text_match
    # Date should clause uses exact variants
    date_bool = tier2["must"][1]["bool"]
    assert date_bool["minimum_should_match"] == 1

    # Verify fallback: date variant match_phrase + remaining text match (OR)
    tier3_clauses = clauses[2:]
    assert "match_phrase" in tier3_clauses[0]
    assert tier3_clauses[0]["match_phrase"]["chunk_text"]["query"] == "15 December 2022"
    assert "match" in tier3_clauses[1]
    assert tier3_clauses[1]["match"]["chunk_text"]["query"] == "unable to work"
    assert tier3_clauses[1]["match"]["chunk_text"]["operator"] == "or"


# --- Tests for _build_tiered_text_query ---


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_tiered_text_query_structure(mock_settings):
    """Test _build_tiered_text_query creates 3 tiers with correct operators and boosts."""
    mock_settings.TEXT_TIER1_BOOST = 3
    mock_settings.TEXT_TIER2_BOOST = 2
    mock_settings.TEXT_TIER3_BOOST = 1
    mock_settings.TEXT_MINIMUM_SHOULD_MATCH = "55%"

    clauses = search_query_builder._build_tiered_text_query("head injury treatment")

    assert len(clauses) == 3

    # Tier 1: All terms required
    assert clauses[0]["match"]["chunk_text"]["operator"] == "and"
    assert clauses[0]["match"]["chunk_text"]["boost"] == 3
    assert clauses[0]["match"]["chunk_text"]["query"] == "head injury treatment"

    # Tier 2: Most terms required
    assert clauses[1]["match"]["chunk_text"]["minimum_should_match"] == "55%"
    assert clauses[1]["match"]["chunk_text"]["boost"] == 2

    # Tier 3: Any term (fallback)
    assert clauses[2]["match"]["chunk_text"]["operator"] == "or"
    assert clauses[2]["match"]["chunk_text"]["boost"] == 1


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_tiered_text_query_single_term(mock_settings):
    """Test _build_tiered_text_query works for single-term queries."""
    mock_settings.TEXT_TIER1_BOOST = 3
    mock_settings.TEXT_TIER2_BOOST = 2
    mock_settings.TEXT_TIER3_BOOST = 1
    mock_settings.TEXT_MINIMUM_SHOULD_MATCH = "55%"

    clauses = search_query_builder._build_tiered_text_query("fracture")

    assert len(clauses) == 3
    assert all(c["match"]["chunk_text"]["query"] == "fracture" for c in clauses)


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_tiered_text_query_boost_ordering(mock_settings):
    """Test _build_tiered_text_query has descending boost order."""
    mock_settings.TEXT_TIER1_BOOST = 3
    mock_settings.TEXT_TIER2_BOOST = 2
    mock_settings.TEXT_TIER3_BOOST = 1
    mock_settings.TEXT_MINIMUM_SHOULD_MATCH = "55%"

    clauses = search_query_builder._build_tiered_text_query("mental health")

    boosts = [c["match"]["chunk_text"]["boost"] for c in clauses]
    assert boosts == [3, 2, 1]


@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_from_search_string")
@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_create_hybrid_query_combined_mode_with_semantic(mock_settings, mock_extract):
    """Test combined mode includes supplementary semantic clause alongside tiered text."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.QUERY_MODE = "combined"
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 1.0
    mock_settings.TEXT_TIER1_BOOST = 3
    mock_settings.TEXT_TIER2_BOOST = 2
    mock_settings.TEXT_TIER3_BOOST = 1
    mock_settings.TEXT_MINIMUM_SHOULD_MATCH = "55%"
    mock_settings.CASE_FILTER = "TEST-123"

    mock_extract.return_value = DateExtractionResult(dates=[], remaining_text="brain injury", matched_patterns=[])

    query = search_query_builder.create_hybrid_query("brain injury", [0.1, 0.2], result_size=5)

    clauses = query["query"]["bool"]["should"]
    # 3 tiered text clauses + 1 knn (semantic)
    assert len(clauses) == 4
    assert any("knn" in c for c in clauses)
