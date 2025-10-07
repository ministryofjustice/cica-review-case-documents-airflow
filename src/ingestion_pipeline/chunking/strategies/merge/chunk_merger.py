import datetime
import logging
from typing import List

from textractor.entities.layout import Layout

from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


class ChunkMerger:
    """
    Groups atomic chunks into larger page-level chunks based on a fixed word limit
    and spatial proximity (vertical distance).
    """

    def __init__(self, word_limit: int = 80, max_vertical_gap: float = 0.5):
        """
        Initializes the chunker with a word limit and spatial tolerance.

        Args:
            word_limit: The maximum number of words allowed in a single chunk.
            max_vertical_gap: The maximum absolute vertical distance between the
                              bottom of one chunk and the top of the next. If the
                              gap is larger than this value, a new chunk group is
                              started. This handles large jumps on the page, such
                              as moving from the bottom of one column to the top
                              of another. This value is in the same units as the
                              bounding box coordinates (e.g., a normalized ratio
                              of page height).
        """
        self.word_limit = word_limit
        self.max_vertical_gap = max_vertical_gap

    def chunk(self, atomic_chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Groups atomic chunks into larger chunks per page based on word limit and
        spatial grouping.

        Args:
            atomic_chunks: A list of atomic chunks from layout block handlers.

        Returns:
            A list of grouped OpenSearchDocument chunks.
        """
        if not atomic_chunks:
            return []

        grouped_chunks = []
        buffer = []
        buffer_word_count = 0
        current_page = atomic_chunks[0].page_number
        chunk_index = 0

        for chunk in atomic_chunks:
            chunk_word_count = len(chunk.chunk_text.split())

            # Determine if we need to flush the buffer before adding the new chunk
            should_flush = False
            if buffer:
                last_chunk_in_buffer = buffer[-1]

                # Check for flush conditions in order of priority
                if chunk.page_number != current_page:
                    should_flush = True
                elif buffer_word_count + chunk_word_count > self.word_limit:
                    should_flush = True
                else:
                    # Spatially-aware check: flush if there's a large vertical gap
                    vertical_gap = chunk.bounding_box.top - last_chunk_in_buffer.bounding_box.bottom
                    if abs(vertical_gap) > self.max_vertical_gap:
                        should_flush = True

            if should_flush:
                grouped_chunks.append(self._merge_chunks(buffer, chunk_index))
                chunk_index += 1
                buffer = []
                buffer_word_count = 0

            # Update the current page if it has changed (applies after a potential flush)
            if chunk.page_number != current_page:
                current_page = chunk.page_number

            buffer.append(chunk)
            buffer_word_count += chunk_word_count

        # After the loop, flush any remaining chunks in the buffer
        if buffer:
            grouped_chunks.append(self._merge_chunks(buffer, chunk_index))

        logger.debug(
            f"Grouped {len(grouped_chunks)} page-level chunks from {len(atomic_chunks)} atomic chunks. "
            f"Word limit: {self.word_limit}, Y-tolerance-ratio: {self.max_vertical_gap}. "
        )

        for c in grouped_chunks:
            logger.debug(f"Chunk {c.chunk_id} (Page {c.page_number}, Words: {c.word_count}): {c.chunk_text}")
            # uncomment this line for ocr chunk text output checking
            # logger.info(f"CHUNK TEXT: {c.chunk_text}")

        return grouped_chunks

    def _merge_chunks(self, chunks: List[DocumentChunk], chunk_index: int) -> DocumentChunk:
        """
        Merges a list of atomic chunks into a single OpenSearchDocument.

        Args:
            chunks: List of atomic chunks to merge.
            chunk_index: Index for the new chunk.

        Returns:
            A merged OpenSearchDocument.
        """
        merged_text = " ".join([c.chunk_text for c in chunks]).strip()
        merged_bbox = combine_bounding_boxes([c.bounding_box.to_textractor_bbox() for c in chunks])

        first_chunk = chunks[0]
        page_number = first_chunk.page_number

        metadata = DocumentMetadata(
            page_count=first_chunk.page_count,
            ingested_doc_id=first_chunk.ingested_doc_id,
            source_file_name=first_chunk.source_file_name,
            case_ref=first_chunk.case_ref if first_chunk.case_ref is not None else "",
            received_date=first_chunk.received_date if first_chunk.received_date is not None else datetime.date.min,
            correspondence_type=first_chunk.correspondence_type if first_chunk.correspondence_type is not None else "",
        )

        # Use the first chunk's layout type and confidence as a placeholder
        dummy_layout = Layout(
            label=first_chunk.chunk_type,
            confidence=first_chunk.confidence,
            bbox=merged_bbox,
            entity_id=f"merged_chunk_{chunk_index}",
            reading_order=0,
        )

        return DocumentChunk.from_textractor_layout(
            block=dummy_layout,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=merged_text,
            combined_bbox=merged_bbox,
        )
