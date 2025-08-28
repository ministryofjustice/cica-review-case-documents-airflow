from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout


@dataclass(frozen=True)
class BoundingBoxDict:
    """Immutable bounding box representation for serialization."""

    width: float
    height: float
    left: float
    top: float

    @classmethod
    def from_textractor_bbox(cls, bbox: BoundingBox) -> "BoundingBoxDict":
        """Creates a BoundingBoxDict from a Textractor BoundingBox object."""
        return cls(
            width=bbox.width,
            height=bbox.height,
            left=bbox.x,
            top=bbox.y,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "Width": self.width,
            "Height": self.height,
            "Left": self.left,
            "Top": self.top,
        }


@dataclass(frozen=True)
class DocumentMetadata:
    """Immutable document metadata."""

    ingested_doc_id: str
    source_file_name: str
    page_count: int
    case_ref: str
    received_date: date
    correspondence_type: str

    def __post_init__(self):
        """Validate required fields."""
        if not all(
            [
                self.ingested_doc_id,
                self.source_file_name,
            ]
        ):
            raise ValueError("DocumentMetadata string fields cannot be empty.")

        if self.page_count <= 0:
            raise ValueError("DocumentMetadata.page_count must be a positive integer.")


@dataclass
class OpenSearchChunk:
    """Represents a document chunk for OpenSearch indexing."""

    chunk_id: str
    ingested_doc_id: str
    chunk_text: str
    source_file_name: str
    page_count: int
    page_number: int
    chunk_index: int
    chunk_type: str
    confidence: float
    bounding_box: BoundingBoxDict
    embedding: Optional[List[float]] = None
    case_ref: Optional[str] = None
    received_date: Optional[date] = None
    correspondence_type: Optional[str] = None
    # Add computed properties
    character_count: int = field(init=False)
    word_count: int = field(init=False)

    def __post_init__(self):
        """Compute derived fields after initialization."""
        self.character_count = len(self.chunk_text)
        self.word_count = len(self.chunk_text.split())

    @classmethod
    def from_textractor_layout(
        cls, block: Layout, page_number: int, metadata: DocumentMetadata, chunk_index: int
    ) -> "OpenSearchChunk":
        """Creates an OpenSearchChunk instance from a Textractor Layout block."""
        text_content = block.text.strip()
        chunk_id = cls._generate_chunk_id(metadata.ingested_doc_id, page_number, chunk_index)
        bounding_box_dict = BoundingBoxDict.from_textractor_bbox(block.bbox)

        return cls(
            chunk_id=chunk_id,
            ingested_doc_id=metadata.ingested_doc_id,
            chunk_text=text_content,
            source_file_name=metadata.source_file_name,
            page_count=metadata.page_count,
            page_number=page_number,
            chunk_index=chunk_index,
            chunk_type=block.layout_type,
            confidence=block.confidence,
            bounding_box=bounding_box_dict,
            case_ref=metadata.case_ref,
            received_date=metadata.received_date,
            correspondence_type=metadata.correspondence_type,
        )

    @classmethod
    def from_textractor_layout_and_text(
        cls,
        block: Layout,
        page_num: int,
        metadata: DocumentMetadata,
        chunk_index: int,
        chunk_text: str,
        combined_bbox: BoundingBox,
    ) -> "OpenSearchChunk":
        """
        Creates an OpenSearchChunk from a Textractor Layout block using pre-computed
        text and a combined bounding box, useful for splitting large blocks.
        """
        chunk_id = cls._generate_chunk_id(metadata.ingested_doc_id, page_num, chunk_index)
        bounding_box_dict = BoundingBoxDict.from_textractor_bbox(combined_bbox)

        return cls(
            chunk_id=chunk_id,
            ingested_doc_id=metadata.ingested_doc_id,
            chunk_text=chunk_text,
            source_file_name=metadata.source_file_name,
            page_count=metadata.page_count,
            page_number=page_num,
            chunk_index=chunk_index,
            chunk_type=block.layout_type,
            confidence=block.confidence,
            bounding_box=bounding_box_dict,
            case_ref=metadata.case_ref,
            received_date=metadata.received_date,
            correspondence_type=metadata.correspondence_type,
        )

    @staticmethod
    def _generate_chunk_id(ingested_doc_id: str, page_num: int, chunk_index: int) -> str:
        """Generate consistent chunk ID."""
        return f"{ingested_doc_id}_p{page_num}_c{chunk_index}"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization to OpenSearch."""
        return {
            "chunk_id": self.chunk_id,
            "ingested_doc_id": self.ingested_doc_id,
            "chunk_text": self.chunk_text,
            "source_file_name": self.source_file_name,
            "page_count": self.page_count,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "chunk_type": self.chunk_type,
            "confidence": self.confidence,
            "bounding_box": self.bounding_box.to_dict(),
            "character_count": self.character_count,
            "word_count": self.word_count,
            "embedding": self.embedding,
            "case_ref": self.case_ref,
            "received_date": self.received_date.isoformat() if self.received_date else None,
            "correspondence_type": self.correspondence_type,
        }
