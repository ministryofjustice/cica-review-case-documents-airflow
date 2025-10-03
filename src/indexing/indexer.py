import logging
from typing import List

from opensearchpy import OpenSearch, helpers

from src.chunking.schemas import OpenSearchDocument

logger = logging.getLogger(__name__)


class OpenSearchIndexer:
    """Handles bulk indexing of documents into an OpenSearch index."""

    def __init__(
        self, host: str, port: int, index_name: str, user: str = "admin", password: str = "really-secure-passwordAa!1"
    ):
        """
        Initializes the OpenSearch client and sets the target index.

        Args:
            host: The OpenSearch host.
            port: The OpenSearch port.
            index_name: The name of the index to write documents to.
            user: The username for authentication.
            password: The password for authentication.
        """
        if not index_name:
            raise ValueError("Index name cannot be empty.")

        self.index_name = index_name
        self.client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=(user, password),
            use_ssl=False,
            verify_certs=False,
            ssl_assert_hostname=False,
        )
        logger.info(f"OpenSearchIndexer initialized for index '{self.index_name}' at {host}:{port}")

    def index_documents(self, documents: List[OpenSearchDocument], id_field: str = "chunk_id"):
        """
        Indexes a list of Pydantic models into OpenSearch using the Bulk API.

        Args:
            documents: A list of Pydantic models (e.g., OpenSearchDocument).
            id_field: The attribute name on the model to use as the document's _id.

        Returns:
            A tuple containing the number of successfully indexed documents and any errors.
        """
        if not documents:
            logger.warning("No documents provided to index.")
            return 0, []

        actions = self._generate_bulk_actions(documents, id_field)

        try:
            success, errors = helpers.bulk(self.client, actions, raise_on_error=False)
            logger.info(f"Successfully indexed {success} documents into '{self.index_name}'.")
            if errors:
                logger.error(f"Encountered {len(errors)} errors during bulk indexing: {errors}")
            return success, errors
        except Exception as e:
            logger.error(f"An exception occurred during the bulk indexing operation: {e}")
            raise

    def _generate_bulk_actions(self, documents: List[OpenSearchDocument], id_field: str):
        """Converts a list of Pydantic models to OpenSearch bulk actions."""
        for doc in documents:
            if not hasattr(doc, id_field):
                raise AttributeError(f"Document model is missing the required id_field '{id_field}'.")

            yield {
                "_op_type": "index",
                "_index": self.index_name,
                "_id": getattr(doc, id_field),
                "_source": doc.model_dump(),
            }
