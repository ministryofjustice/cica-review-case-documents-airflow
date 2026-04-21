"""Module for indexing documents into OpenSearch.

Supports a single proxy/base URL which may include the path (url prefix).
"""

import logging
from collections import Counter
from typing import Any, List
from urllib.parse import urlparse

from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import ConflictError

logger = logging.getLogger(__name__)


class IndexingError(Exception):
    """Custom exception for indexing failures."""


class OpenSearchIndexer:
    """Handles bulk indexing of documents into an OpenSearch index.

    Args:
        index_name: Target index name.
        proxy_url: Full proxy/base URL, e.g. 'http://proxy:8080'
    """

    def __init__(
        self,
        *,  # Enforce keyword arguments
        index_name: str,
        proxy_url: str,
    ):
        """Initialize the indexer connection using a single proxy URL.

        Args:
            proxy_url (str): The full proxy/base URL for OpenSearch, which may include the path (url prefix).
                Example: 'http://proxy:8080' or 'https://proxy:9200/opensearch'
            index_name (str): The name of the OpenSearch index to which documents will be indexed.

        Raises:
            ValueError: If the index name is empty.
            ValueError: If the proxy URL is empty.
            ValueError: If the proxy URL is invalid.
        """
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
            timeout=30,
        )

        logger.info("Client initialised for index '%s'", self.index_name)

    def index_documents(self, documents: List[Any], id_field: str = "chunk_id"):
        """Indexes a list of Pydantic models into OpenSearch using the Bulk API.

        Deletes any existing documents with the same source_doc_id before indexing new ones.
        If any errors occur during indexing, all partially indexed documents are cleaned up.

        Args:
            documents (List[Any]): A list of Pydantic models to index (e.g., DocumentChunk or DocumentPage).
            id_field (str): The attribute name on the model to use as the document's _id.
                Defaults to "chunk_id".

        Returns:
            Tuple[int, List]: A tuple containing:
                - int: The number of successfully indexed documents.
                - List: Any errors that occurred during indexing (empty list if all succeeded).

        Raises:
            IndexingError: If bulk indexing fails or if an unexpected error occurs.
        """
        if not documents:
            logger.warning("No documents provided to index.")
            return 0, []

        source_doc_id = documents[0].source_doc_id
        if self.client.indices.exists(index=self.index_name):
            logger.info(
                f"Attempting document deletion of existing documents from index {self.index_name} before reindexing"
            )
            self.delete_documents_by_source_doc_id(source_doc_id)
        actions = self._generate_bulk_actions(documents, id_field)

        try:
            logger.info(f"Indexing {len(documents)} documents into index {self.index_name}")
            # raise_on_error=False
            # allows the function to continue and collect all errors,
            # so we can handle them (log, retry, cleanup) instead of immediately stopping on the first error.
            success, errors = helpers.bulk(self.client, actions, raise_on_error=False, chunk_size=50)

            if errors:
                logger.debug("Bulk indexing errors for index %s: %s", self.index_name, errors)
                # Clean up any partially indexed documents from this batch
                self.delete_documents_by_source_doc_id(source_doc_id)
                raise IndexingError(self._format_bulk_error_summary(errors))

            logger.info(f"Indexed {len(documents)} chunks into index {self.index_name}")
            return success, errors
        except helpers.BulkIndexError as e:
            logger.debug("BulkIndexError details for index %s: %s", self.index_name, e.errors)
            self.delete_documents_by_source_doc_id(source_doc_id)
            raise IndexingError(self._format_bulk_error_summary(e.errors)) from e
        except IndexingError:
            raise
        except Exception as e:
            logger.info(f"An unexpected exception occurred indexing removing all associated chunks: {e}")
            self.delete_documents_by_source_doc_id(source_doc_id)
            raise IndexingError(f"Failed to index: {str(e)}") from e

    def _format_bulk_error_summary(self, errors: List[Any], top_n: int = 3) -> str:
        """Create a compact summary for bulk index failures.

        This avoids logging thousands of near-identical error entries while retaining
        enough context to diagnose the failure mode.
        """
        grouped_errors: Counter[tuple[str, str, str]] = Counter()

        for item in errors:
            op_payload = next(iter(item.values()), {}) if isinstance(item, dict) else {}
            status = str(op_payload.get("status", "unknown"))
            error_payload = op_payload.get("error", {}) if isinstance(op_payload, dict) else {}
            error_type = str(error_payload.get("type", "unknown"))
            reason = str(error_payload.get("reason", "unknown"))
            grouped_errors[(status, error_type, reason)] += 1

        top_causes = []
        for (status, error_type, reason), count in grouped_errors.most_common(top_n):
            top_causes.append(f"{count}x(status={status}, type={error_type}, reason={reason})")

        top_causes_text = "; ".join(top_causes) if top_causes else "unknown"
        return f"Failed to index {len(errors)} chunk(s). Top causes: {top_causes_text}"

    def _generate_bulk_actions(self, documents: List[Any], id_field: str):
        """Generates OpenSearch bulk actions from a list of Pydantic models.

        Args:
            documents (List[Any]): List of Pydantic models to be indexed.
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

    def delete_documents_by_source_doc_id(self, source_doc_id: str):
        """Deletes all documents in the index with the given source_doc_id.

        Args:
            source_doc_id (str): The unique identifier of the source document whose
                associated documents should be deleted.

        Raises:
            Exception: If deletion fails for reasons other than version conflicts.
        """
        query = {"query": {"match": {"source_doc_id": source_doc_id}}}
        try:
            response = self.client.delete_by_query(index=self.index_name, body=query)
            deleted_count = response.get("deleted", 0)
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} documents from index {self.index_name}")
        except ConflictError as e:
            logger.debug(f"Version conflict during delete (harmless): {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to delete documents by source_doc_id: {e}", exc_info=True)
            raise
