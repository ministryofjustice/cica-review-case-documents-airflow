"""Pydantic schemas for document chunking and metadata."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field
from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout


class DocumentBoundingBox(BaseModel):
    """Immutable bounding box representation for serialization using Pydantic."""

    model_config = ConfigDict(frozen=True)

    width: float = Field(alias="Width")
    height: float = Field(alias="Height")
    left: float = Field(alias="Left")
    top: float = Field(alias="Top")

    @classmethod
    def from_textractor_bbox(cls, bbox: BoundingBox) -> "DocumentBoundingBox":
        """Creates a DocumentBoundingBox from a Textractor BoundingBox.

        Args:
            bbox (BoundingBox): The Textractor BoundingBox to convert.

        Returns:
            DocumentBoundingBox: The converted DocumentBoundingBox.
        """
        return cls(Width=bbox.width, Height=bbox.height, Left=bbox.x, Top=bbox.y)

    def to_textractor_bbox(self) -> BoundingBox:
        """Converts this DocumentBoundingBox back to a Textractor BoundingBox."""
        return BoundingBox(
            width=self.width,
            height=self.height,
            x=self.left,
            y=self.top,
        )

    @computed_field
    @property
    def right(self) -> float:
        """Calculates the right edge of the bounding box.

        Returns:
            float: The x-coordinate of the right edge.
        """
        return self.left + self.width

    @computed_field
    @property
    def bottom(self) -> float:
        """Calculates the bottom edge of the bounding box.

        Returns:
            float: The y-coordinate of the bottom edge.
        """
        return self.top + self.height


class DocumentMetadata(BaseModel):
    """Immutable document metadata with Pydantic validation."""

    model_config = ConfigDict(frozen=True)

    ingested_doc_id: str = Field(min_length=1)
    source_file_name: str = Field(min_length=1)
    page_count: int = Field(gt=0)
    case_ref: str
    received_date: datetime
    correspondence_type: str


class DocumentChunk(BaseModel):
    """Represents a document chunk for OpenSearch, built with Pydantic."""

    chunk_id: str
    ingested_doc_id: str
    chunk_text: str
    source_file_name: str
    page_count: int
    page_number: int
    chunk_index: int
    # TODO add page_id
    # TODO This was initially representing an AWS layout type.
    # It may be redundant, review!
    chunk_type: str
    confidence: float
    bounding_box: DocumentBoundingBox
    embedding: Optional[List[float]] = None
    case_ref: Optional[str] = None
    received_date: Optional[datetime] = None
    correspondence_type: Optional[str] = None

    @computed_field
    @property
    def character_count(self) -> int:
        """Calculates the number of characters in the chunk text.

        Returns:
            int: The number of characters in the chunk text.
        """
        return len(self.chunk_text)

    @computed_field
    @property
    def word_count(self) -> int:
        """Calculates the number of words in the chunk text.

        Returns:
            int: The number of words in the chunk text.
        """
        return len(self.chunk_text.split())

    @staticmethod
    def _generate_chunk_id(ingested_doc_id: str, page_num: int, chunk_index: int) -> str:
        """Generate consistent chunk ID."""
        return f"{ingested_doc_id}_p{page_num}_c{chunk_index}"

    @classmethod
    def from_textractor_layout(
        cls,
        block: Layout,  # TODO consider only passing in layout_type and confidence
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
        chunk_text: str,
        combined_bbox: BoundingBox,
    ) -> "DocumentChunk":
        """Creates a DocumentChunk from a Textractor Layout block.

        using pre-computed text and a combined bounding box, useful for splitting large blocks.

        Args:
            block (Layout): The Textractor Layout block.
            page_number (int): The page number of the chunk (1-based).
            metadata (DocumentMetadata): The document metadata.
            chunk_index (int): The index of the chunk on the page (0-based).
            chunk_text (str): The text content of the chunk.
            combined_bbox (BoundingBox): The combined bounding box for the chunk.

        Returns:
            DocumentChunk: The created DocumentChunk instance.
        """
        chunk_id = cls._generate_chunk_id(metadata.ingested_doc_id, page_number, chunk_index)
        bounding_box_model = DocumentBoundingBox.from_textractor_bbox(combined_bbox)

        # Pydantic validates the data upon instantiation here
        # We will need to identify whether chunk is/contains HANDWRITTEN elements
        return cls(
            chunk_id=chunk_id,
            ingested_doc_id=metadata.ingested_doc_id,
            chunk_text=chunk_text,
            source_file_name=metadata.source_file_name,
            page_count=metadata.page_count,
            page_number=page_number,
            chunk_index=chunk_index,
            chunk_type=block.layout_type,
            confidence=block.confidence,  # TODO does this need recalculated for combined chunks
            bounding_box=bounding_box_model,
            case_ref=metadata.case_ref,
            received_date=metadata.received_date,
            correspondence_type=metadata.correspondence_type,
        )


class DocumentPage(BaseModel):
    """Represents a single page's metadata for indexing."""

    document_id: str = Field(..., description="The unique ID of the source document.")
    page_num: int = Field(..., description="The page number (1-based).")
    page_id: str = Field(..., description="UUID for the index.")
    text: str = Field(..., description="Structured ocr content for the front end rendering")
    page_width: float
    page_height: float


class ProcessedDocument(BaseModel):
    """Holds all structured data extracted from a single source document."""

    chunks: List[DocumentChunk]
    pages: List[DocumentPage]
    metadata: DocumentMetadata
