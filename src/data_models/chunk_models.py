# your_project/models.py
from dataclasses import dataclass
from datetime import date
from typing import List

from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout
from textractor.entities.page import Page


@dataclass
class BoundingBoxDict:
    Width: float
    Height: float
    Left: float
    Top: float

    @staticmethod
    def from_textractor_bbox(bbox: BoundingBox) -> "BoundingBoxDict":
        """Creates a BoundingBoxDict from a Textractor BoundingBox object."""
        return BoundingBoxDict(
            Width=bbox.width,
            Height=bbox.height,
            Left=bbox.x,
            Top=bbox.y,
        )


@dataclass
class DocumentMetadata:
    ingested_doc_id: str
    s3_page_image_uri: str
    source_file_name: str
    page_count: int
    case_ref: str
    received_date: date
    correspondence_type: str


@dataclass
class OpenSearchChunk:
    chunk_id: str
    ingested_doc_id: str
    chunk_text: str
    source_file_name: str
    s3_page_image_uri: str
    page_count: int
    page_number: int
    chunk_index: int
    chunk_type: str
    confidence: float
    bounding_box: BoundingBoxDict
    embedding: List[float] | None = None
    case_ref: str | None = None
    received_date: date | None = None
    correspondence_type: str | None = None

    @classmethod
    def from_textractor_layout(
        cls, block: Layout, page: Page, metadata: DocumentMetadata, chunk_index: int
    ) -> "OpenSearchChunk":
        """
        Creates an OpenSearchChunk instance from a Textractor Layout block.
        """
        text_content = block.text.strip()
        chunk_id = f"{metadata.ingested_doc_id}_p{page.page_num}_c{chunk_index}"
        bounding_box_dict = BoundingBoxDict.from_textractor_bbox(block.bbox)

        return cls(
            chunk_id=chunk_id,
            ingested_doc_id=metadata.ingested_doc_id,
            chunk_text=text_content,
            source_file_name=metadata.source_file_name,
            s3_page_image_uri=metadata.s3_page_image_uri,
            page_count=metadata.page_count,
            page_number=page.page_num,
            chunk_index=chunk_index,
            chunk_type=block.layout_type,
            confidence=block.confidence,
            bounding_box=bounding_box_dict,
            case_ref=metadata.case_ref,
            received_date=metadata.received_date,
            correspondence_type=metadata.correspondence_type,
        )
