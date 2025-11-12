"""Module for indexing documents into OpenSearch.

Supports a single proxy/base URL which may include the path (url prefix).
"""

import logging
from typing import List
from urllib.parse import urlparse

from opensearchpy import OpenSearch, helpers

from ingestion_pipeline.chunking.schemas import DocumentChunk

logger = logging.getLogger(__name__)


class IndexingError(Exception):
    """Custom exception for indexing failures."""


class OpenSearchIndexer:
    """Handles bulk indexing of documents into an OpenSearch index.

    Args:
        index_name: Target index name.
        proxy_url: Full proxy/base URL, e.g.,
                   'http://proxy:8080'
    """

    def __init__(
        self,
        *,  # Enforce keyword arguments
        index_name: str,
        proxy_url: str,
    ):
        """Initialize the indexer connection using a single proxy URL."""
        if not index_name:
            raise ValueError("Index name cannot be empty.")
        self.index_name = index_name

        if not proxy_url:
            raise ValueError("The OpenSearch proxy URL cannot be empty.")

        parsed = urlparse(proxy_url)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError(f"Invalid OpenSearch proxy URL: {proxy_url}")

        host_entry = {
            "host": parsed.hostname,
            "port": parsed.port or (443 if parsed.scheme == "https" else 80),
            "scheme": parsed.scheme,
        }

        hosts = [host_entry]
        logger.info(
            "OpenSearchIndexer using proxy URL host=%s port=%s",
            host_entry["host"],
            host_entry["port"],
        )

        self.client = OpenSearch(
            hosts=hosts,
            http_auth=(),
            use_ssl=host_entry["scheme"] == "https",
            verify_certs=False,
            ssl_assert_hostname=False,
        )

        logger.info("Client initialised for index '%s'", self.index_name)

    def index_documents(self, documents: List[DocumentChunk], id_field: str = "chunk_id"):
        """Indexes a list of Pydantic models into OpenSearch using the Bulk API.

        Args:
            documents: A list of Pydantic models (e.g., OpenSearchDocument).
            id_field: The attribute name on the model to use as the document's _id.

        Returns:
            A tuple containing the number of successfully indexed documents and any errors.
        """
        if not documents:
            logger.warning("No documents provided to index.")
            return 0, []

        source_doc_id = documents[0].source_doc_id
        self._delete_documents_by_source_doc_id(source_doc_id)
        actions = self._generate_bulk_actions(documents, id_field)

        try:
            success, errors = helpers.bulk(self.client, actions, raise_on_error=False)

            if errors:
                logger.error(
                    f"Encountered {len(errors)} errors during bulk indexing cleaning up partially indexed chunks"
                )
                # Clean up any partially indexed documents from this batch
                self._delete_documents_by_source_doc_id(source_doc_id)
                raise IndexingError(f"Failed to index all chunks: {errors}")

            logger.info(f"Successfully indexed chunks into index {self.index_name}")
            return success, errors
        except helpers.BulkIndexError as e:
            logger.error(f"A BulkIndexError occurred. Removing all associated chunks: {e.errors}")
            self._delete_documents_by_source_doc_id(source_doc_id)
            raise IndexingError(f"Failed to index documents due to bulk errors: {str(e)}") from e
        except Exception as e:
            logger.error(f"An unexpected exception occurred. Removing all associated chunks: {e}")
            self._delete_documents_by_source_doc_id(source_doc_id)
            raise IndexingError(f"Failed to index: {str(e)}") from e

    def _generate_bulk_actions(self, documents: List[DocumentChunk], id_field: str):
        """Generates OpenSearch bulk actions from a list of document chunks.

        Args:
            documents (List[DocumentChunk]): List of DocumentChunk instances to be indexed.
            id_field (str): Attribute name to use as the document's unique identifier.

        Raises:
            AttributeError: Raised if a document does not have the specified id_field.

        Yields:
            dict: Bulk action dictionaries for OpenSearch indexing.
        """
        for doc in documents:
            if not hasattr(doc, id_field):
                raise AttributeError(f"Document model is missing the required id_field '{id_field}'.")

            yield {
                "_op_type": "index",
                "_index": self.index_name,
                "_id": getattr(doc, id_field),
                "_source": doc.model_dump(),
            }

    def _delete_documents_by_source_doc_id(self, source_doc_id: str):
        """Deletes all documents in the index with the given source_doc_id."""
        query = {"query": {"match": {"source_doc_id": source_doc_id}}}
        response = self.client.delete_by_query(index=self.index_name, body=query)
        logger.info(f"Deleted {response.get('deleted', 0)} chunks from index {self.index_name}")
