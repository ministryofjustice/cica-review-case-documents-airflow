"""Central exception hierarchy for the ingestion pipeline.

This module has no dependencies on other pipeline components so every module can
import from it without creating import cycles. All recoverable, per-document
failures raised anywhere in the pipeline inherit from :class:`PipelineError`,
giving the runner a single base type to catch.

Each error carries enough context to (a) decide whether the source job should be
redriven or is terminal, and (b) enrich downstream failure records — the SQS DLQ
and a future OpenSearch failure/status metadata index. Neither sink is built yet;
the exceptions simply carry the information both will need.
"""

from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Import for type-checking only. Keeping it out of runtime preserves this
    # module's zero-dependency property (see module docstring), so any component
    # can import errors without risking an import cycle.
    from ingestion_pipeline.chunking.schemas import DocumentMetadata


class DlqCategory(str, Enum):
    """Classification of a document processing failure.

    Used to categorise failures for operational triage (e.g. in a metadata index
    or DLQ message). String-valued so it serialises cleanly into JSON/logs.
    """

    TEXTRACT_FAILED = "textract_failed"
    EMPTY_TEXTRACT_RESPONSE = "empty_textract_response"
    # Zero chunks were produced across the *entire* document (all pages combined),
    # not merely a single page yielding no chunks.
    ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT = "zero_chunks_extracted_from_document"
    PAGE_PROCESSING_FAILED = "page_processing_failed"
    CHUNKING_FAILED = "chunking_failed"
    EMBEDDING_FAILED = "embedding_failed"
    INDEXING_FAILED = "indexing_failed"
    UNEXPECTED = "unexpected"


class PipelineError(Exception):
    """Base exception for all per-document pipeline failures.

    The runner catches this single type. Subclasses set a default
    :attr:`category` and :attr:`retryable` describing the failure so a sink (DLQ
    redrive decision, metadata index record) can act on it without inspecting the
    concrete type.

    Attributes:
        category (DlqCategory): The failure classification.
        retryable (bool): Whether redriving the source job could plausibly succeed.
            Terminal failures (e.g. a document Textract cannot read) set this False.
        source_doc_id (Optional[str]): The deterministic document UUID, if known.
        case_ref (Optional[str]): The CICA case reference, if known.
        s3_uri (Optional[str]): The source document S3 URI, if known.
    """

    #: Default classification for this error type. Subclasses override.
    category: DlqCategory = DlqCategory.UNEXPECTED
    #: Default retry disposition for this error type. Subclasses override.
    retryable: bool = True

    def __init__(
        self,
        message: str,
        *,
        source_doc_id: Optional[str] = None,
        case_ref: Optional[str] = None,
        s3_uri: Optional[str] = None,
    ):
        """Initialise the error with a message and optional document context.

        Args:
            message (str): Human-readable description of the failure.
            source_doc_id (Optional[str]): The deterministic document UUID.
            case_ref (Optional[str]): The CICA case reference.
            s3_uri (Optional[str]): The source document S3 URI.
        """
        super().__init__(message)
        self.source_doc_id = source_doc_id
        self.case_ref = case_ref
        self.s3_uri = s3_uri

    @classmethod
    def from_metadata(
        cls,
        message: str,
        metadata: "DocumentMetadata",
        **kwargs,
    ) -> "PipelineError":
        """Build an error, sourcing document context from a metadata object.

        Convenience constructor for raise sites that hold a ``DocumentMetadata``.
        Avoids repeating the field-by-field mapping (source_doc_id, case_ref,
        s3_uri) at every call site.

        Args:
            message (str): Human-readable description of the failure.
            metadata (DocumentMetadata): The document's metadata to draw context from.
            **kwargs: Any additional keyword arguments accepted by ``__init__``.

        Returns:
            PipelineError: An instance of the concrete subclass with document
                context populated from ``metadata``.
        """
        return cls(
            message,
            source_doc_id=metadata.source_doc_id,
            case_ref=metadata.case_ref,
            s3_uri=metadata.source_file_s3_uri,
            **kwargs,
        )

    def enrich_from_metadata(self, metadata: "DocumentMetadata") -> None:
        """Backfill any missing document context from a metadata object, in place.

        Most errors are raised deep in the pipeline with only a message, so they
        reach the orchestrator with no document context. This fills the gaps from
        ``metadata`` without overwriting any value the error already carries (a
        terminal error that set its own context is left untouched).

        Args:
            metadata (DocumentMetadata): The document's metadata to draw context from.
        """
        if self.source_doc_id is None:
            self.source_doc_id = metadata.source_doc_id
        if self.case_ref is None:
            self.case_ref = metadata.case_ref
        if self.s3_uri is None:
            self.s3_uri = metadata.source_file_s3_uri

    def failure_context(self) -> dict:
        """Return a serialisable summary of the failure for logging or a sink.

        Returns:
            dict: Failure classification and document context. Keys with no value
                are still present (set to None) so records have a stable shape.
        """
        return {
            "category": self.category.value,
            "retryable": self.retryable,
            "error_type": type(self).__name__,
            "message": str(self),
            "source_doc_id": self.source_doc_id,
            "case_ref": self.case_ref,
            "s3_uri": self.s3_uri,
        }


class EmptyTextractResponseError(PipelineError):
    """Textract returned an empty response (no document); nothing downstream ran.

    Terminal: redriving the same source document will not produce a document, so
    this needs investigation rather than automatic retry.
    """

    category = DlqCategory.EMPTY_TEXTRACT_RESPONSE
    retryable = False


class ZeroChunksError(PipelineError):
    """A document was processed but produced zero chunks; nothing searchable indexed.

    Terminal: the document read successfully but yielded no chunkable content, so
    it warrants investigation rather than automatic retry.
    """

    category = DlqCategory.ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT
    retryable = False
