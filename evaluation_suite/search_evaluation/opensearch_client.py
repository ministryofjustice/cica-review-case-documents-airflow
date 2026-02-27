"""Shared OpenSearch client configuration for the search evaluation framework.

This module provides a centralized OpenSearch client factory and connection settings.
All modules in the search_evaluation package should import from here instead of
creating their own clients.
"""

import logging
import os

from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

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


def get_opensearch_client() -> OpenSearch:
    """Create and return an OpenSearch client.

    Returns:
        Configured OpenSearch client for the local development environment.
    """
    return OpenSearch(
        hosts=[settings.OPENSEARCH_PROXY_URL],
        http_auth=(USER, PASSWORD),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
    )


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
        raise ConnectionError(
            f"OpenSearch is not reachable at {settings.OPENSEARCH_PROXY_URL}. "
            "Is the local environment running? Try: docker compose up -d\n"
            f"Details: {e}"
        ) from e


__all__ = [
    "get_opensearch_client",
    "check_opensearch_health",
    "OpenSearchConnectionError",
    "CHUNK_INDEX_NAME",
    "USER",
    "PASSWORD",
]
