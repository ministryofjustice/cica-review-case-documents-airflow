"""Hybrid search client for querying a local OpenSearch instance and exporting results to Excel.

This module provides functions to perform hybrid (keyword and semantic) searches using OpenSearch,
filter results, and write them to an Excel file for analysis.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the project 'src' directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "src"))

import xlsxwriter
from opensearchpy import OpenSearch

# Import the OpenSearch-specific ConnectionError
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from ingestion_pipeline.config import settings
from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator
from testing import evaluation_settings as eval_settings
from testing.evaluation_config import get_active_search_type

os.environ["AWS_MOD_PLATFORM_ACCESS_KEY_ID"] = settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID
os.environ["AWS_MOD_PLATFORM_SECRET_ACCESS_KEY"] = settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY
os.environ["AWS_MOD_PLATFORM_SESSION_TOKEN"] = settings.AWS_MOD_PLATFORM_SESSION_TOKEN
os.environ["AWS_REGION"] = settings.AWS_REGION

# --- 1. CONFIGURE YOUR RUNNING LOCALSTACK OPENSEARCH CONNECTION ---
# These values should match your LocalStack setup

USER = "admin"
PASSWORD = "really-secure-passwordAa!1"
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

# --- 2. Choose your search term and output name and location---

SEARCH_TERM = "bone"

# Edit the output directory and path if needed
# Use path relative to testing folder (parent of this file)
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIRECTORY = SCRIPT_DIR / "output" / "single-search-results" / datetime.now().strftime("%Y-%m-%d")
SAFE_SEARCH_TERM = str(SEARCH_TERM).replace("/", "_").replace(" ", "_")
TIMESTAMP_STR = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_PATH = OUTPUT_DIRECTORY / f"{TIMESTAMP_STR}_{SAFE_SEARCH_TERM}_search_results.xlsx"

# --- 3. DEFINE K-NN SEARCH QUERY ---


def create_hybrid_query(query_text: str, query_vector: list[float], k: int = 5) -> dict:
    """Create a hybrid search query combining keyword, fuzzy, and semantic vector search.

    Each search type is only included if its boost value is greater than 0.
    """
    should_clauses = []

    # Add keyword match if boost > 0
    if eval_settings.KEYWORD_BOOST > 0:
        should_clauses.append({"match": {"chunk_text": {"query": query_text, "boost": eval_settings.KEYWORD_BOOST}}})

    # Add English analyzer match if boost > 0
    # Uses the chunk_text.english multi-field which is indexed with the English analyzer
    if eval_settings.ANALYSER_BOOST > 0:
        should_clauses.append(
            {
                "match": {
                    "chunk_text.english": {
                        "query": query_text,
                        "boost": eval_settings.ANALYSER_BOOST,
                    }
                }
            }
        )

    # Add fuzzy match if boost > 0
    if eval_settings.FUZZY_BOOST > 0:
        should_clauses.append(
            {
                "fuzzy": {
                    "chunk_text": {
                        "value": query_text,
                        "fuzziness": eval_settings.FUZZINESS,
                        "max_expansions": eval_settings.MAX_EXPANSIONS,
                        "boost": eval_settings.FUZZY_BOOST,
                    }
                }
            }
        )

    # Add wildcard match if boost > 0
    if eval_settings.WILDCARD_BOOST > 0:
        should_clauses.append(
            {
                "wildcard": {
                    "chunk_text": {
                        "value": f"*{query_text}*",
                        "boost": eval_settings.WILDCARD_BOOST,
                    }
                }
            }
        )

    # Add semantic/knn search if boost > 0
    if eval_settings.SEMANTIC_BOOST > 0:
        should_clauses.append(
            {"knn": {"embedding": {"vector": query_vector, "k": k, "boost": eval_settings.SEMANTIC_BOOST}}}
        )

    return {
        "size": k,
        "_source": ["document_id", "page_number", "chunk_text", "case_ref"],
        "query": {"bool": {"should": should_clauses}},
    }


# --- 4. Execute results and write to Excel ---
def local_search_client(search_term: str = SEARCH_TERM) -> list[dict]:
    """Execute a hybrid search on the local OpenSearch instance and return the hits.

    :param search_term: The search term to query. Defaults to SEARCH_TERM constant.
    :return: List of search hits.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("embedding_search_client")
    try:
        embedding_generator = EmbeddingGenerator(settings.BEDROCK_EMBEDDING_MODEL_ID)
        embedding = embedding_generator.generate_embedding(search_term)
        logger.info(f"Generated embedding for search term: '{search_term}'")

        client = OpenSearch(
            hosts=[settings.OPENSEARCH_PROXY_URL],
            http_auth=(USER, PASSWORD),
            use_ssl=False,
            verify_certs=False,
            ssl_assert_hostname=False,
        )

        search_query = create_hybrid_query(search_term, embedding, k=eval_settings.K_QUERIES)
        logger.info(f"Performing hybrid search for {eval_settings.K_QUERIES} neighbors in '{CHUNK_INDEX_NAME}'...")
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
    score_filter: float = eval_settings.SCORE_FILTER,
    search_term: str = SEARCH_TERM,
) -> None:
    """Write the search hits to an Excel file, filtering by score."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(OUTPUT_PATH))
    worksheet = workbook.add_worksheet()
    filtered_hits = [hit for hit in hits if hit["_score"] >= score_filter]

    # Get active search type from config
    search_type_str = get_active_search_type()

    # Write search parameters in the first row
    worksheet.write(0, 0, "Search term:")
    worksheet.write(1, 0, search_term)
    worksheet.write(0, 1, "Search type:")
    worksheet.write(1, 1, search_type_str)
    worksheet.write(0, 2, "K_queries:")
    worksheet.write(1, 2, eval_settings.K_QUERIES)
    worksheet.write(0, 3, "Score filter:")
    worksheet.write(1, 3, score_filter)
    worksheet.write(0, 4, "Keyword boost:")
    worksheet.write(1, 4, eval_settings.KEYWORD_BOOST)
    worksheet.write(0, 5, "Analyser boost:")
    worksheet.write(1, 5, eval_settings.ANALYSER_BOOST)
    worksheet.write(0, 6, "Semantic boost:")
    worksheet.write(1, 6, eval_settings.SEMANTIC_BOOST)
    worksheet.write(0, 7, "Fuzzy boost:")
    worksheet.write(1, 7, eval_settings.FUZZY_BOOST)
    worksheet.write(0, 8, "No of results")
    worksheet.write(1, 8, len(filtered_hits))

    headers = ["Score", "Term Freq", "Case Ref", "Chunk ID", "Page", "Text Snippet"]
    for col, header in enumerate(headers):
        worksheet.write(2, col, header)

    for row, hit in enumerate(filtered_hits, start=0):
        score = hit["_score"]
        source = hit["_source"]
        text_snippet = source.get("chunk_text", "")
        term_freq = count_term_occurrences(text_snippet, search_term)
        worksheet.write(row + 3, 0, score)
        worksheet.write(row + 3, 1, term_freq)
        worksheet.write(row + 3, 2, source.get("case_ref", "N/A"))
        worksheet.write(row + 3, 3, str(hit.get("_id", "N/A")))
        # "_id" is a top-level key in each hit, while other fields are in "_source"
        worksheet.write(row + 3, 4, source.get("page_number", "N/A"))
        worksheet.write(row + 3, 5, text_snippet)
    workbook.close()
    logging.info(f"Results written to {OUTPUT_PATH.resolve()}({len(filtered_hits)} results)")


if __name__ == "__main__":
    hits = local_search_client()
    write_hits_to_xlsx(hits, search_term=SEARCH_TERM)
