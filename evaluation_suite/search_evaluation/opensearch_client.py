"""Shared OpenSearch client configuration for the search evaluation framework.

This module provides a centralized OpenSearch client factory and connection settings.
All modules in the search_evaluation package should import from here instead of
creating their own clients.
"""

import logging
import os

from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from evaluation_suite.search_evaluation import evaluation_settings
from ingestion_pipeline.config import settings

# Set AWS environment variables from settings (MOD_PLATFORM variants)
os.environ["AWS_MOD_PLATFORM_ACCESS_KEY_ID"] = settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID
os.environ["AWS_MOD_PLATFORM_SECRET_ACCESS_KEY"] = settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY
os.environ["AWS_MOD_PLATFORM_SESSION_TOKEN"] = settings.AWS_MOD_PLATFORM_SESSION_TOKEN
os.environ["AWS_REGION"] = settings.AWS_REGION

# OpenSearch connection settings
USER = "admin"
PASSWORD = "really-secure-passwordAa!1"  # noqa: S105
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

logger = logging.getLogger(__name__)

# Suppress per-request INFO logs from the opensearch-py HTTP transport
logging.getLogger("opensearch").setLevel(logging.WARNING)
# Suppress urllib3 retry noise (connection errors are re-raised explicitly)
logging.getLogger("urllib3").setLevel(logging.WARNING)

BEDROCK_ML_MODEL_NAME = "bedrock-titan-embed-text-v2"


def get_opensearch_client() -> OpenSearch:
    """Create and return an OpenSearch client with retry configuration.

    Returns:
        Configured OpenSearch client with exponential backoff retry logic
        for transient failures (timeouts, connection errors, 5xx responses).

    Note:
        - Timeout is set to 30 seconds to accommodate port-forwarded remote connections.
        - Retries are configured for transient failures with exponential backoff.
    """
    return OpenSearch(
        hosts=[settings.OPENSEARCH_PROXY_URL],
        http_auth=(USER, PASSWORD),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
        timeout=evaluation_settings.OPENSEARCH_TIMEOUT,
        max_connections=100,
        retry_on_timeout=True,  # Enable retry on timeout
        max_retries=evaluation_settings.OPENSEARCH_MAX_RETRIES,  # Retry count for transient failures
    )


def get_deployed_ml_model_id(client: OpenSearch, model_name: str = BEDROCK_ML_MODEL_NAME) -> str:
    """Look up the ML Commons model ID for a deployed model by name.

    The model ID is assigned dynamically when the Bedrock connector is set up, so
    it changes on every environment rebuild. This function resolves the current ID
    at runtime by querying ML Commons, so callers never need to hard-code it.

    Args:
        client: An active OpenSearch client.
        model_name: The registered model name to look up.

    Returns:
        The ML Commons model ID string (a UUID-like value).

    Raises:
        ValueError: If no deployed model with the given name is found.
    """
    response = client.transport.perform_request(
        "GET",
        "/_plugins/_ml/models/_search",
        body={
            "query": {"match": {"name.keyword": model_name}},
            "sort": [{"last_updated_time": {"order": "desc"}}],
            "size": 1,
        },
    )
    hits = response.get("hits", {}).get("hits", [])
    if not hits:
        raise ValueError(
            f"No ML Commons model named '{model_name}' found. "
            "Has the Bedrock connector setup script run successfully?"
        )
    return hits[0]["_id"]


def check_opensearch_health() -> None:
    """Verify OpenSearch is reachable before starting an evaluation run.

    Raises:
        ConnectionError: If OpenSearch cannot be reached, with a clear
            message indicating the endpoint and remediation steps.
    """
    try:
        client = get_opensearch_client()
        client.cluster.health()
        logger.info(f"OpenSearch healthcheck passed: {settings.OPENSEARCH_PROXY_URL}")
    except OpenSearchConnectionError as e:
        # Log the original error for debugging without creating verbose tracebacks
        logger.debug(f"OpenSearch connection failed: {e}")
        # Raise without exception chain to avoid printing the full opensearchpy traceback
        raise ConnectionError(
            f"OpenSearch is not reachable at {settings.OPENSEARCH_PROXY_URL}. "
            "Is the local environment running? Try: docker compose up -d"
        ) from None


__all__ = [
    "get_opensearch_client",
    "get_deployed_ml_model_id",
    "check_opensearch_health",
    "OpenSearchConnectionError",
    "CHUNK_INDEX_NAME",
    "BEDROCK_ML_MODEL_NAME",
    "USER",
    "PASSWORD",
]
