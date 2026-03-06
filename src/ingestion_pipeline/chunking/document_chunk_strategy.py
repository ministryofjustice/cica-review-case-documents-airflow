"""Base class for chunk strategies.

This module defines the abstract interface that all chunk strategy implementations
must follow, ensuring consistency across different chunking strategies.
"""

from abc import ABC, abstractmethod

from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import DocumentMetadata, ProcessedDocument


class ChunkError(Exception):
    """Custom exception for chunking failures."""


class ChunkStrategy(ABC):
    """Abstract base class for chunk strategies.

    All chunk strategy implementations must inherit from this class and implement
    the chunk() method. This ensures a consistent interface across different
    chunking strategies (layout-based, line-based, etc.).
    """

    @abstractmethod
    def chunk(self, doc: Document, metadata: DocumentMetadata) -> ProcessedDocument:
        """Parses a Textractor Document or part of a document and extracts structured chunks.

        Args:
            doc: Textractor Document containing pages and content to process.
            metadata: Document metadata including source file information.

        Returns:
            ProcessedDocument: Container with the list of extracted DocumentChunk objects.

        Raises:
            ValueError: If the document is None or contains no pages.
            ChunkError: If chunk extraction fails during processing.
        """
        pass
