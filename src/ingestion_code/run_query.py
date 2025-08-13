from typing import Any

from opensearchpy import NotFoundError

from ingestion_code.config import settings
from ingestion_code.embed_text import embed_query_with_titan_model
from ingestion_code.index_text import get_opensearch_client

client = get_opensearch_client()


def create_search_pipeline() -> dict[str, Any]:
    """Create a hybrid search pipeline."""
    pipeline_id = "nlp-search-pipeline"
    pipeline_def = {
        "description": "Post processor for hybrid search",
        "phase_results_processors": [
            {
                "normalization-processor": {
                    "normalization": {"technique": "min_max"},
                    "combination": {
                        "technique": "arithmetic_mean",
                        "parameters": {"weights": [0.3, 0.7]},
                    },
                }
            }
        ],
    }

    # --- Create or update the pipeline ---
    client.search_pipeline.put(id=pipeline_id, body=pipeline_def)

    # --- Read it back ---
    pipeline = client.transport.perform_request(
        "GET", f"/_search/pipeline/{pipeline_id}"
    )

    # --- Set it as the index’s default search pipeline ---
    client.indices.put_settings(
        index=settings.OPENSEARCH_INDEX_NAME,
        body={"index.search.default_pipeline": pipeline_id},
    )

    return pipeline


def run_hybrid_query(query: str) -> dict[str, Any]:
    """Run a hybrid query."""
    # Check if the search pipeline already exists
    try:
        client.transport.perform_request("GET", "/_search/pipeline/nlp-search-pipeline")

    except NotFoundError:
        create_search_pipeline()

    # Embed the query
    embedding_vector = embed_query_with_titan_model(query)

    # Run a hybrid keyword and semantic search
    body = {
        "_source": {"exclude": ["embedding"]},
        "query": {
            "hybrid": {
                "queries": [
                    {"match": {"chunk_text": {"query": query}}},
                    {"knn": {"embedding": {"vector": embedding_vector, "k": 5}}},
                ]
            }
        },
    }

    return client.search(
        index=settings.OPENSEARCH_INDEX_NAME,
        body=body,
    )
