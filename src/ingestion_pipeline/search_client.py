import logging
from datetime import datetime
from pathlib import Path

import xlsxwriter
from opensearchpy import OpenSearch

from ingestion_pipeline.config import settings
from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator

# --- 1. CONFIGURE YOUR RUNNING LOCALSTACK OPENSEARCH CONNECTION ---
# These values should match your LocalStack setup

HOST = "localhost"
PORT = 9200
USER = "admin"
PASSWORD = "really-secure-passwordAa!1"
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

# --- 2. Choose your search term and variables for testing ---

SEARCH_TERM = "gaba"
K_QUERIES = 200  # Number of nearest neighbors to retrieve
SCORE_FILTER = 0.4  # Minimum score threshold for filtering results

#  Set either boost as zero to return only the other type of search
KEYWORD_BOOST = 1  # Boost factor for keyword matching in hybrid search
SEMANTIC_BOOST = 2  # Boost factor for semantic vector search in hybrid search

# --- 3. DEFINE K-NN SEARCH QUERY ---


def create_hybrid_query(query_text, query_vector, k=5):
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


# --- 4. Execute results and write to Excel ---
def local_search_client():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("embedding_search_client")

    embedding_generator = EmbeddingGenerator(settings.BEDROCK_EMBEDDING_MODEL_ID)
    embedding = embedding_generator.generate_embedding(SEARCH_TERM)
    logger.info(f"Generated embedding for search term: '{SEARCH_TERM}'")

    client = OpenSearch(
        hosts=[{"host": HOST, "port": PORT}],
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


def write_hits_to_xlsx(hits, score_filter=SCORE_FILTER, search_term=SEARCH_TERM):
    today_folder = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path("output/hybrid-test-results") / today_folder
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_search_term = str(search_term).replace("/", "_").replace(" ", "_")
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_path = output_dir / f"{timestamp_str}_{safe_search_term}_search_results.xlsx"
    workbook = xlsxwriter.Workbook(str(output_path))
    worksheet = workbook.add_worksheet()
    # Write search parameters in the first row
    worksheet.write(0, 0, "Search term:")
    worksheet.write(1, 0, search_term)
    worksheet.write(0, 1, "K_queries:")
    worksheet.write(1, 1, K_QUERIES)
    worksheet.write(0, 2, "Score filter:")
    worksheet.write(1, 2, score_filter)
    worksheet.write(0, 3, "Keyword boost:")
    worksheet.write(1, 3, KEYWORD_BOOST)
    worksheet.write(0, 4, "Semantic boost:")
    worksheet.write(1, 4, SEMANTIC_BOOST)
    worksheet.write(0, 5, "No of results")
    worksheet.write(1, 5, len(hits))

    headers = ["Score", "Case Ref", "Chunk ID", "Page", "Text Snippet"]
    for col, header in enumerate(headers):
        worksheet.write(2, col, header)
    filtered_hits = [hit for hit in hits if hit["_score"] >= score_filter]
    for row, hit in enumerate(filtered_hits, start=0):
        score = hit["_score"]
        source = hit["_source"]
        worksheet.write(row + 3, 0, score)
        worksheet.write(row + 3, 1, source.get("case_ref", "N/A"))
        worksheet.write(row + 3, 2, str(hit.get("_id", "N/A")))
        worksheet.write(row + 3, 3, source.get("page_number", "N/A"))
        text_snippet = source.get("chunk_text", "")
        worksheet.write(row + 3, 4, text_snippet)
    workbook.close()
    logging.info(f"Results written to {output_path.resolve()}")


if __name__ == "__main__":
    hits = local_search_client()
    write_hits_to_xlsx(hits, search_term=SEARCH_TERM)
