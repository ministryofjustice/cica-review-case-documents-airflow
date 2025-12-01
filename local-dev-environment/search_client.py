"""Hybrid search client for querying a local OpenSearch instance and exporting results to Excel.

This module provides functions to perform hybrid (keyword and semantic) searches using OpenSearch,
filter results, and write them to an Excel file for analysis.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import xlsxwriter
from opensearchpy import OpenSearch

# Import the OpenSearch-specific ConnectionError
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

# Add the project 'src' directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from ingestion_pipeline.config import settings
from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator

os.environ["AWS_ACCESS_KEY_ID"] = settings.AWS_ACCESS_KEY_ID
os.environ["AWS_SECRET_ACCESS_KEY"] = settings.AWS_SECRET_ACCESS_KEY
os.environ["AWS_SESSION_TOKEN"] = settings.AWS_SESSION_TOKEN
os.environ["AWS_REGION"] = settings.AWS_REGION

# --- 1. CONFIGURE YOUR RUNNING LOCALSTACK OPENSEARCH CONNECTION ---
# These values should match your LocalStack setup

USER = "admin"
PASSWORD = "really-secure-passwordAa!1"
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

# --- 2. Choose your search term, variables for testing and output name and location---

SEARCH_TERM = "concussion"
K_QUERIES = 100  # Number of nearest neighbors to retrieve
SCORE_FILTER = 0.56  # Minimum score threshold for filtering results
FUZZY = False  # Enable fuzzy matching

#  Set boosts to refine search behaviour and adjust fuzzy matching parameters
KEYWORD_BOOST = 1  # Boost factor for keyword matching in hybrid search
SEMANTIC_BOOST = 1  # Boost factor for semantic vector search in hybrid search
FUZZY_BOOST = 1  # Boost factor for fuzzy matching in hybrid search
FUZZINESS = "Auto"  # Fuzziness level for fuzzy matching, Auto chooses based on term length but can be set to an integer
MAX_EXPANSIONS = 50  # Maximum expansions for fuzzy matching

# Edit the output directory and path if needed

OUTPUT_DIRECTORY = Path("local-dev-environment/output/hybrid-test-results") / datetime.now().strftime("%Y-%m-%d")
SAFE_SEARCH_TERM = str(SEARCH_TERM).replace("/", "_").replace(" ", "_")
TIMESTAMP_STR = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_PATH = OUTPUT_DIRECTORY / f"{TIMESTAMP_STR}_{SAFE_SEARCH_TERM}_search_results.xlsx"

# --- 3. DEFINE K-NN SEARCH QUERY ---


def create_hybrid_query(query_text: str, query_vector: list[float], k: int = 5) -> dict:
    """Create a hybrid search query combining keyword and semantic vector search."""
    if not FUZZY:
        return {
            "size": k,
            "_source": ["document_id", "page_number", "chunk_text", "case_ref"],
            "query": {
                "bool": {
                    "should": [
                        {"match": {"chunk_text": {"query": query_text, "boost": KEYWORD_BOOST}}},
                        {"knn": {"embedding": {"vector": query_vector, "k": k, "boost": SEMANTIC_BOOST}}},
                    ]
                }
            },
        }
    else:
        return {
            "size": k,
            "_source": ["document_id", "page_number", "chunk_text", "case_ref"],
            "query": {
                "bool": {
                    "should": [
                        {
                            "fuzzy": {
                                "chunk_text": {
                                    "value": query_text,
                                    "fuzziness": FUZZINESS,
                                    "max_expansions": MAX_EXPANSIONS,
                                    "boost": FUZZY_BOOST,
                                }
                            }
                        },
                        {"knn": {"embedding": {"vector": query_vector, "k": k, "boost": SEMANTIC_BOOST}}},
                    ]
                }
            },
        }


# --- 4. Execute results and write to Excel ---
def local_search_client() -> list[dict]:
    """Execute a hybrid search on the local OpenSearch instance and return the hits."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("embedding_search_client")
    try:
        embedding_generator = EmbeddingGenerator(settings.BEDROCK_EMBEDDING_MODEL_ID)
        embedding = embedding_generator.generate_embedding(SEARCH_TERM)
        logger.info(f"Generated embedding for search term: '{SEARCH_TERM}'")

        client = OpenSearch(
            hosts=[settings.OPENSEARCH_PROXY_URL],
            http_auth=(USER, PASSWORD),
            use_ssl=False,
            verify_certs=False,
            ssl_assert_hostname=False,
        )

        search_query = create_hybrid_query(SEARCH_TERM, embedding, k=K_QUERIES)
        logger.info(f"Performing hybrid search for {K_QUERIES} neighbors in '{CHUNK_INDEX_NAME}'...")
        response = client.search(index=CHUNK_INDEX_NAME, body=search_query)

        hits = response["hits"]["hits"]

        # print(f"hits: {hits}")
        return hits

    except OpenSearchConnectionError as ce:
        logger.error("Could not connect to OpenSearch. Is the OpenSearch DB running locally?")
        logger.error(f"OpenSearch ConnectionError details: {ce}")
        raise  # Rethrow the exception

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise  # Rethrow the exception


def write_hits_to_xlsx(hits: list[dict], score_filter: float = SCORE_FILTER, search_term: str = SEARCH_TERM) -> None:
    """Write the search hits to an Excel file, filtering by score."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(OUTPUT_PATH))
    worksheet = workbook.add_worksheet()
    filtered_hits = [hit for hit in hits if hit["_score"] >= score_filter]
    # Write search parameters in the first row
    worksheet.write(0, 0, "Search term:")
    worksheet.write(1, 0, search_term)
    worksheet.write(0, 1, "Search type:")
    worksheet.write(1, 1, "Fuzzy" if FUZZY else "Keyword")
    worksheet.write(0, 2, "K_queries:")
    worksheet.write(1, 2, K_QUERIES)
    worksheet.write(0, 3, "Score filter:")
    worksheet.write(1, 3, score_filter)
    worksheet.write(0, 4, "Keyword boost:")
    worksheet.write(1, 4, KEYWORD_BOOST)
    worksheet.write(0, 5, "Semantic boost:")
    worksheet.write(1, 5, SEMANTIC_BOOST)
    worksheet.write(0, 6, "Fuzzy boost:")
    worksheet.write(1, 6, FUZZY_BOOST)
    worksheet.write(0, 7, "No of results")
    worksheet.write(1, 7, len(filtered_hits))

    headers = ["Score", "Case Ref", "Chunk ID", "Page", "Text Snippet"]
    for col, header in enumerate(headers):
        worksheet.write(2, col, header)

    for row, hit in enumerate(filtered_hits, start=0):
        score = hit["_score"]
        source = hit["_source"]
        worksheet.write(row + 3, 0, score)
        worksheet.write(row + 3, 1, source.get("case_ref", "N/A"))
        worksheet.write(row + 3, 2, str(hit.get("_id", "N/A")))
        # "_id" is a top-level key in each hit, while other fields are in "_source"
        worksheet.write(row + 3, 3, source.get("page_number", "N/A"))
        text_snippet = source.get("chunk_text", "")
        worksheet.write(row + 3, 4, text_snippet)
    workbook.close()
    logging.info(f"Results written to {OUTPUT_PATH.resolve()}({len(filtered_hits)} results)")


if __name__ == "__main__":
    hits = local_search_client()
    write_hits_to_xlsx(hits, search_term=SEARCH_TERM)
