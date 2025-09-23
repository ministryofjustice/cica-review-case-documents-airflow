# src/chunking/strategies/key_value/key_value_chunker.py

import logging
from typing import List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.key_value import KeyValue
from textractor.entities.layout import Layout
from textractor.entities.line import Line  # Import the Line entity

from src.chunking.schemas import DocumentMetadata, OpenSearchDocument
from src.chunking.strategies.base import ChunkingStrategyHandler
from src.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


class KeyValueChunker(ChunkingStrategyHandler):
    """
    Handles LAYOUT_KEY_VALUE blocks, creating chunks for both KeyValue pairs
    and individual Line objects found within the block.
    """

    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[OpenSearchDocument]:
        """
        Processes a layout block, creating distinct chunks for KeyValue pairs
        and standalone Line objects.
        """
        logger.debug(f"++++++++ Processing mixed Key-Value block: {layout_block.id} ++++++++")

        chunks = []

        for child_block in layout_block.children:
            if isinstance(child_block, KeyValue):
                if child_block.key and child_block.value:
                    key_text = " ".join([word.text for word in child_block.key]).strip().rstrip(":")
                    value_text = child_block.value.text.strip()
                    chunk_text = f"{key_text}: {value_text}"
                    bboxes = [child_block.bbox]

                    chunk = self._create_chunk(
                        chunk_text=chunk_text,
                        bboxes=bboxes,
                        layout_block=layout_block,
                        page_number=page_number,
                        metadata=metadata,
                        chunk_index=chunk_index_start + len(chunks),
                    )
                    chunks.append(chunk)

            elif isinstance(child_block, Line):
                chunk_text = child_block.text.strip()
                if chunk_text:  # Only process non-empty lines
                    bboxes = [child_block.bbox]

                    chunk = self._create_chunk(
                        chunk_text=chunk_text,
                        bboxes=bboxes,
                        layout_block=layout_block,
                        page_number=page_number,
                        metadata=metadata,
                        chunk_index=chunk_index_start + len(chunks),
                    )
                    chunks.append(chunk)

            else:
                logger.warning(
                    f"Skipping unexpected child block of type "
                    f"'{type(child_block).__name__}' in LAYOUT_KEY_VALUE block {layout_block.id}"
                )

        logger.debug(f"Created {len(chunks)} chunks from mixed block {layout_block.id}")
        return chunks

    def _create_chunk(
        self,
        chunk_text: str,
        bboxes: List[BoundingBox],
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> OpenSearchDocument:
        """
        A helper method to create an OpenSearchDocument from chunk data.
        This centralizes the creation logic.
        """
        # Combine multiple bounding boxes into a single one that envelops them all.
        combined_bbox = combine_bounding_boxes(bboxes) if len(bboxes) > 1 else bboxes[0]

        logger.debug(f"Layout {layout_block.layout_type} chunk : {chunk_text}")

        return OpenSearchDocument.from_textractor_layout(
            block=layout_block,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text.strip(),
            combined_bbox=combined_bbox,
        )
