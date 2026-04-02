"""Search client for executing hybrid searches against OpenSearch.

This module provides the search execution layer used by the evaluation pipeline.
Query building logic lives in search_query_builder.py.

For ad-hoc exploration, run this module directly editing the search term in the __main__ block.:
    python -m evaluation_suite.search_evaluation.search_client
"""

import logging
from datetime import datetime
from pathlib import Path

import xlsxwriter

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.evaluation_config import get_active_search_type
from evaluation_suite.search_evaluation.opensearch_client import (
    CHUNK_INDEX_NAME,
    OpenSearchConnectionError,
    get_opensearch_client,
)
from evaluation_suite.search_evaluation.search_query_builder import apply_adaptive_score_filter, create_hybrid_query
from ingestion_pipeline.config import settings
from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator

SCRIPT_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("search_client")


def local_search_client(search_term: str) -> list[dict]:
    """Execute a hybrid search on the local OpenSearch instance and return the hits.

    Args:
        search_term: The search term to query.

    Returns:
        List of search hits from OpenSearch.
    """
    try:
        embedding_generator = EmbeddingGenerator(settings.BEDROCK_EMBEDDING_MODEL_ID)
        embedding = embedding_generator.generate_embedding(search_term)
        logger.debug(f"Generated embedding for search term: '{search_term}'")

        client = get_opensearch_client()

        search_query = create_hybrid_query(search_term, embedding, result_size=eval_settings.RESULT_SIZE)
        logger.debug(
            f"Hybrid search: '{search_term}', result_size={eval_settings.RESULT_SIZE}, index='{CHUNK_INDEX_NAME}'"
        )
        response = client.search(index=CHUNK_INDEX_NAME, body=search_query)

        hits = response["hits"]["hits"]

        return hits

    except OpenSearchConnectionError as ce:
        logger.error("Could not connect to OpenSearch. Is the OpenSearch DB running locally?")
        logger.error(f"OpenSearch ConnectionError details: {ce}")
        raise  # Rethrow the exception

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise  # Rethrow the exception


def count_term_occurrences(text: str, search_term: str) -> int:
    """Count occurrences of search term in text (case-insensitive)."""
    if not text or not search_term:
        return 0
    return text.lower().count(search_term.lower())


def write_hits_to_xlsx(
    hits: list[dict],
    search_term: str,
    score_filter: float = eval_settings.SCORE_FILTER,
    output_dir: Path | None = None,
) -> None:
    """Write the search hits to an Excel file, with additive semantic fallback.

    Uses adaptive filtering if enabled: if too few keyword results pass the
    primary score_filter, supplements with semantic results.

    Args:
        hits: List of raw OpenSearch hits.
        search_term: The search term used (written into the spreadsheet header).
        score_filter: Score threshold to apply. Defaults to SCORE_FILTER setting.
        output_dir: Directory to write the Excel file. Defaults to output/single-search-results/<date>/.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_term = search_term.replace("/", "_").replace(" ", "_")
    resolved_output_dir = output_dir or (SCRIPT_DIR / "output" / "single-search-results" / date_str)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = resolved_output_dir / f"{timestamp}_{safe_term}_search_results.xlsx"
    workbook = xlsxwriter.Workbook(str(output_path))
    worksheet = workbook.add_worksheet()

    # Apply additive semantic fallback filtering
    filtered_hits, effective_filter, semantic_added = apply_adaptive_score_filter(hits, score_filter)
    initial_search_results = len(filtered_hits) - semantic_added
    adaptive_filter_used = semantic_added > 0

    # Get active search type from config
    search_type_str = get_active_search_type()

    # Write search parameters in the first row
    worksheet.write(0, 0, "Search term:")
    worksheet.write(1, 0, search_term)
    worksheet.write(0, 1, "Search type:")
    worksheet.write(1, 1, search_type_str)
    worksheet.write(0, 2, "result_size:")
    worksheet.write(1, 2, eval_settings.RESULT_SIZE)
    worksheet.write(0, 3, "Score filter:")
    worksheet.write(1, 3, effective_filter)
    worksheet.write(0, 4, "Keyword boost:")
    worksheet.write(1, 4, eval_settings.KEYWORD_BOOST)
    worksheet.write(0, 5, "Analyser boost:")
    worksheet.write(1, 5, eval_settings.ANALYSER_BOOST)
    worksheet.write(0, 6, "Semantic boost:")
    worksheet.write(1, 6, eval_settings.SEMANTIC_BOOST)
    worksheet.write(0, 7, "Fuzzy boost:")
    worksheet.write(1, 7, eval_settings.FUZZY_BOOST)
    worksheet.write(0, 8, "Total results:")
    worksheet.write(1, 8, len(filtered_hits))
    worksheet.write(0, 9, "Initial results:")
    worksheet.write(1, 9, initial_search_results)
    worksheet.write(0, 10, "Adaptive filter used:")
    worksheet.write(1, 10, adaptive_filter_used)
    worksheet.write(0, 11, "Query mode:")
    worksheet.write(1, 11, eval_settings.QUERY_MODE)

    headers = ["Score", "Type", "Term Freq", "Case Ref", "Chunk ID", "Page", "Text Snippet"]
    for col, header in enumerate(headers):
        worksheet.write(2, col, header)

    for row, hit in enumerate(filtered_hits, start=0):
        score = hit["_score"]
        source = hit["_source"]
        text_snippet = source.get("chunk_text", "")
        term_freq = count_term_occurrences(text_snippet, search_term)
        # Determine result type based on search configuration and adaptive filter
        if adaptive_filter_used:
            # Adaptive filter added semantic results after initial results
            result_type = search_type_str if row < initial_search_results else "Semantic Fallback"
        else:
            # All results are from the configured search type
            result_type = search_type_str
        worksheet.write(row + 3, 0, score)
        worksheet.write(row + 3, 1, result_type)
        worksheet.write(row + 3, 2, term_freq)
        worksheet.write(row + 3, 3, source.get("case_ref", "N/A"))
        worksheet.write(row + 3, 4, str(hit.get("_id", "N/A")))
        # "_id" is a top-level key in each hit, while other fields are in "_source"
        worksheet.write(row + 3, 5, source.get("page_number", "N/A"))
        worksheet.write(row + 3, 6, text_snippet)
    workbook.close()
    logger.info(f"Results written to {output_path.resolve()} ({len(filtered_hits)} results)")


if __name__ == "__main__":
    _search_term = "acute 28-Nov-2022"  # Change this to explore a different term
    _hits = local_search_client(_search_term)
    write_hits_to_xlsx(_hits, search_term=_search_term)
