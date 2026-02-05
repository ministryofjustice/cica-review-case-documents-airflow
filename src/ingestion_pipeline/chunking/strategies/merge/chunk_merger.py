"""Merges atomic chunks into larger page-level chunks."""

import logging
from typing import List

from textractor.entities.layout import Layout

from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


class ChunkMerger:
    """Merges atomic chunks into larger page-level chunks."""

    def __init__(self, word_limit: int = 80, max_vertical_gap: float = 0.5):
        """Initializes the chunker with a word limit and spatial tolerance.

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

    def group_atomic_chunks(self, atomic_chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """Groups atomic chunks into merged chunks using word count and vertical gap criteria.

        Args:
            atomic_chunks: List of atomic (line-based) chunks.

        Returns:
            List[DocumentChunk]: List of merged chunks.
        """
        if not atomic_chunks:
            return []

        logger.info(f"Grouping {len(atomic_chunks)} atomic chunks into merged chunks with word limit {self.word_limit}")
        merged_chunks = []
        atomic_chunk_buffer = []
        buffer_word_count = 0
        current_page = atomic_chunks[0].page_number
        merged_chunk_index = 0

        for atomic_chunk in atomic_chunks:
            atomic_chunk_word_count = len(atomic_chunk.chunk_text.split())
            should_group_buffer = False
            if atomic_chunk_buffer:
                last_atomic_chunk = atomic_chunk_buffer[-1]
                inter_chunk_vertical_gap = atomic_chunk.bounding_box.top - last_atomic_chunk.bounding_box.bottom

                # Flush conditions
                if atomic_chunk.page_number != current_page:
                    should_group_buffer = True
                elif buffer_word_count + atomic_chunk_word_count > self.word_limit:
                    should_group_buffer = True
                elif abs(inter_chunk_vertical_gap) > self.max_vertical_gap:
                    should_group_buffer = True

                # Debug logging for page 3
                if atomic_chunk.page_number == 3:
                    logger.info(
                        f"[group_atomic_chunks] Page 3: merged_chunk_index={merged_chunk_index}, "
                        f"buffer_size={len(atomic_chunk_buffer)}, "
                        f"should_group_buffer={should_group_buffer}, "
                        f"inter_chunk_vertical_gap={inter_chunk_vertical_gap:.5f}, "
                        f"buffer_word_count={buffer_word_count}, "
                        f"atomic_chunk_word_count={atomic_chunk_word_count}"
                    )
                    logger.info(
                        f"  Last buffer chunk: index={last_atomic_chunk.chunk_index}, "
                        f"top={last_atomic_chunk.bounding_box.top}, "
                        f"bottom={last_atomic_chunk.bounding_box.bottom}"
                    )
                    logger.info(
                        f"  Next chunk: index={atomic_chunk.chunk_index}, "
                        f"top={atomic_chunk.bounding_box.top}, "
                        f"bottom={atomic_chunk.bounding_box.bottom}"
                    )

            if should_group_buffer:
                merged_chunks.append(self._merge_chunks(atomic_chunk_buffer, merged_chunk_index))
                merged_chunk_index += 1
                atomic_chunk_buffer = []
                buffer_word_count = 0

            if atomic_chunk.page_number != current_page:
                current_page = atomic_chunk.page_number

            atomic_chunk_buffer.append(atomic_chunk)
            buffer_word_count += atomic_chunk_word_count

        if atomic_chunk_buffer:
            merged_chunks.append(self._merge_chunks(atomic_chunk_buffer, merged_chunk_index))

        logger.info(
            f"[group_atomic_chunks] Grouped {len(merged_chunks)} merged chunks from "
            f"{len(atomic_chunks)} atomic chunks. "
            f"Word limit: {self.word_limit}, Y-tolerance-ratio: {self.max_vertical_gap}. "
        )

        for c in merged_chunks:
            logger.info(
                f"[group_atomic_chunks] Merged Chunk {c.chunk_id} (Page {c.page_number}, Words: {c.word_count}): {c.chunk_text}"
            )

        return merged_chunks

    def _merge_chunks(self, chunks: List[DocumentChunk], chunk_index: int) -> DocumentChunk:
        """Merges a list of atomic chunks into a single OpenSearchDocument.

        Args:
            chunks: List of atomic chunks to merge.
            chunk_index: Index for the new chunk.

        Returns:
            DocumentChunk: A merged OpenSearchDocument.
        """
        first_chunk = chunks[0]
        if first_chunk.page_number == 3:
            logger.info(
                f"Merging page {first_chunk.page_number} Chunk index {chunk_index} - "
                f"merging, chunk count {len(chunks)}"
            )
            for i, c in enumerate(chunks):
                bbox = c.bounding_box
                logger.info(
                    f"  Atomic chunk {i}: text='{c.chunk_text[:30]}...', "
                    f"bbox: left={bbox.left}, top={bbox.top}, width={bbox.width}, "
                    f"height={bbox.height}, right={bbox.right}, "
                    f"bottom={bbox.bottom}"
                )

        merged_text = " ".join([c.chunk_text for c in chunks]).strip()
        merged_bbox = combine_bounding_boxes([c.bounding_box.to_textractor_bbox() for c in chunks])

        if first_chunk.page_number == 3:
            logger.info(
                f"  Merged chunk {chunk_index} bbox: left={merged_bbox.x}, "
                f"top={merged_bbox.y}, width={merged_bbox.width}, "
                f"height={merged_bbox.height}, "
                f"right={merged_bbox.x + merged_bbox.width}, "
                f"bottom={merged_bbox.y + merged_bbox.height}"
            )

        first_chunk = chunks[0]
        page_number = first_chunk.page_number

        metadata = DocumentMetadata(
            page_count=first_chunk.page_count,
            source_doc_id=first_chunk.source_doc_id,
            source_file_name=first_chunk.source_file_name,
            source_file_s3_uri=first_chunk.source_file_s3_uri,
            case_ref=first_chunk.case_ref if first_chunk.case_ref is not None else "",
            received_date=first_chunk.received_date,
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
