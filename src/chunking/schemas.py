from datetime import date
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
        return cls(Width=bbox.width, Height=bbox.height, Left=bbox.x, Top=bbox.y)


class DocumentMetadata(BaseModel):
    """Immutable document metadata with Pydantic validation."""

    model_config = ConfigDict(frozen=True)

    ingested_doc_id: str = Field(min_length=1)
    source_file_name: str = Field(min_length=1)
    page_count: int = Field(gt=0)
    case_ref: str
    received_date: date
    correspondence_type: str


class OpenSearchDocument(BaseModel):
    """Represents a document chunk for OpenSearch, built with Pydantic."""

    chunk_id: str
    ingested_doc_id: str
    chunk_text: str
    source_file_name: str
    page_count: int
    page_number: int
    chunk_index: int
    chunk_type: str
    confidence: float
    bounding_box: DocumentBoundingBox
    embedding: Optional[List[float]] = None
    case_ref: Optional[str] = None
    received_date: Optional[date] = None
    correspondence_type: Optional[str] = None

    @computed_field
    @property
    def character_count(self) -> int:
        return len(self.chunk_text)

    @computed_field
    @property
    def word_count(self) -> int:
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
    ) -> "OpenSearchDocument":
        """
        Creates an OpenSearchChunk from a Textractor Layout block using pre-computed
        text and a combined bounding box, useful for splitting large blocks.
        """
        chunk_id = cls._generate_chunk_id(metadata.ingested_doc_id, page_number, chunk_index)
        bounding_box_model = DocumentBoundingBox.from_textractor_bbox(combined_bbox)

        # Pydantic validates the data upon instantiation here
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
