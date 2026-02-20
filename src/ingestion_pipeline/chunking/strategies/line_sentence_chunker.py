"""Deterministic line-by-line sentence-aware chunking strategy.

This chunker operates directly on LINE blocks (not LAYOUT blocks) to avoid layout
detection issues. It prioritizes sentence integrity and vertical proximity over
complex layout-based grouping.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from textractor.entities.bbox import BoundingBox
from textractor.entities.line import Line

from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


@dataclass
class LineSentenceChunkingConfig:
    """Configuration for line-by-line sentence-aware chunking."""

    # Word count limits
    min_words: int = 60  # Lowered to allow more flexibility
    max_words: int = 120  # Increased to allow more tolerance for sentence breaks

    # Vertical spacing threshold for forcing chunk breaks
    # This is relative to page height (0.0 to 1.0)
    max_vertical_gap_ratio: float = 0.05

    # Whether to enable verbose debug logging
    debug: bool = False


class LineSentenceChunker:
    """Implements deterministic line-by-line sentence-aware chunking.

    This chunker:
    1. Sorts LINE blocks by vertical position (top)
    2. Accumulates text line-by-line
    3. Tracks word count (not character count)
    4. Closes chunks at sentence boundaries (. ? !) after min_words
    5. Forces chunk breaks at max_words or on large vertical gaps
    6. Generates tight bounding boxes for each chunk
    """

    def __init__(self, config: Optional[LineSentenceChunkingConfig] = None):
        """Initialize the chunker with configuration.

        Args:
            config: Configuration for chunking behavior
        """
        self.config = config or LineSentenceChunkingConfig()

    def chunk_page(
        self,
        lines: List[Line],
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int = 0,
    ) -> List[DocumentChunk]:
        """Chunk a page's lines into sentence-aware chunks.

        Args:
            lines: List of LINE blocks from the page
            page_number: The page number (1-indexed)
            metadata: Document metadata
            chunk_index_start: Starting index for chunk numbering

        Returns:
            List of DocumentChunk objects
        """
        if not lines:
            return []

        # Exclude likely footer lines: those near the bottom or matching page number patterns
        footer_threshold = 0.95  # Exclude lines with bbox.y > 0.95 (bottom 5% of page)
        page_number_pattern = re.compile(r"^Page\\s*\\d+", re.IGNORECASE)
        filtered_lines = [
            line for line in lines
            if line.bbox and line.bbox.y < footer_threshold
            and not (line.text and page_number_pattern.match(line.text.strip()))
        ]

        # Sort lines by vertical position (top of bounding box)
        sorted_lines = sorted(filtered_lines, key=lambda line: line.bbox.y if line.bbox else 0)

        chunks = []
        chunk_index = chunk_index_start

        # Current chunk state
        current_lines: List[Tuple[str, BoundingBox]] = []  # (text, bbox)
        current_word_count = 0
        prev_line_bottom: Optional[float] = None

        i = 0
        n = len(sorted_lines)
        while i < n:
            line = sorted_lines[i]
            # Skip lines without text or bounding box
            if not line.text or not line.bbox:
                i += 1
                continue

            line_text = line.text.strip()
            if not line_text:
                i += 1
                continue

            line_bbox = line.bbox
            line_words = line_text.split()
            line_word_count = len(line_words)

            # Check for vertical gap that should force a break
            should_break_on_gap = False
            if prev_line_bottom is not None and line_bbox.y is not None:
                vertical_gap = line_bbox.y - prev_line_bottom
                if vertical_gap > self.config.max_vertical_gap_ratio:
                    should_break_on_gap = True
                    if self.config.debug:
                        logger.debug(
                            f"Page {page_number}: Vertical gap {vertical_gap:.4f} exceeds "
                            f"threshold {self.config.max_vertical_gap_ratio}, forcing chunk break"
                        )

            # Add current line to accumulator
            current_lines.append((line_text, line_bbox))
            current_word_count += line_word_count
            prev_line_bottom = line_bbox.y + line_bbox.height

            # Look ahead for best sentence break if over min_words
            should_close = False
            found_sentence_break = False
            if current_word_count >= self.config.min_words:
                # Try to look ahead up to 3 lines for a sentence break
                lookahead_limit = min(3, n - i - 1)
                for j in range(lookahead_limit + 1):
                    if j == 0:
                        candidate_text = line_text
                    else:
                        next_line = sorted_lines[i + j]
                        if not next_line.text:
                            continue
                        candidate_text = next_line.text.strip()
                    if self._ends_with_sentence_terminator(candidate_text):
                        extra_words = 0
                        for k in range(1, j + 1):
                            next_line = sorted_lines[i + k]
                            if next_line.text:
                                extra_words += len(next_line.text.strip().split())
                        if current_word_count + extra_words <= self.config.max_words:
                            for k in range(1, j + 1):
                                next_line = sorted_lines[i + k]
                                if next_line.text and next_line.bbox:
                                    current_lines.append((next_line.text.strip(), next_line.bbox))
                                    current_word_count += len(next_line.text.strip().split())
                                    prev_line_bottom = next_line.bbox.y + next_line.bbox.height
                            i += j
                            found_sentence_break = True
                        break
                if not found_sentence_break:
                    # Look backward up to 2 lines for a sentence boundary
                    for back in range(1, min(2, len(current_lines)) + 1):
                        candidate_text = current_lines[-back][0]
                        if self._ends_with_sentence_terminator(candidate_text):
                            # Split chunk at this point
                            split_at = len(current_lines) - back
                            if split_at > 0:
                                chunk = self._create_chunk(
                                    lines=current_lines[:split_at],
                                    page_number=page_number,
                                    metadata=metadata,
                                    chunk_index=chunk_index,
                                )
                                chunks.append(chunk)
                                chunk_index += 1
                                current_lines = current_lines[split_at:]
                                current_word_count = sum(len(text.split()) for text, _ in current_lines)
                            should_close = False
                            found_sentence_break = True
                            break
                if found_sentence_break:
                    should_close = True
                elif current_word_count >= self.config.max_words:
                    should_close = True
            elif should_break_on_gap:
                should_close = True

            if should_close and current_lines:
                chunk = self._create_chunk(
                    lines=current_lines,
                    page_number=page_number,
                    metadata=metadata,
                    chunk_index=chunk_index,
                )
                chunks.append(chunk)
                chunk_index += 1
                current_lines = []
                current_word_count = 0

            i += 1

        # Create final chunk if there are remaining lines
        if current_lines:
            chunk = self._create_chunk(
                lines=current_lines,
                page_number=page_number,
                metadata=metadata,
                chunk_index=chunk_index,
            )
            chunks.append(chunk)

        if self.config.debug:
            logger.debug(f"Page {page_number}: Created {len(chunks)} chunks from {len(sorted_lines)} lines")

        return chunks

    def _should_close_chunk(
        self,
        current_word_count: int,
        new_line_word_count: int,
        current_lines: List[Tuple[str, BoundingBox]],
        force_gap_break: bool = False,
    ) -> bool:
        """Determine if the current chunk should be closed.

        Args:
            current_word_count: Current accumulated word count
            new_line_word_count: Word count of the line to be added
            current_lines: Current accumulated lines
            force_gap_break: Whether to force a break due to vertical gap

        Returns:
            True if chunk should be closed, False otherwise
        """
        if not current_lines:
            return False

        # Force break on large vertical gap
        if force_gap_break:
            return True

        # If adding this line would exceed max_words, close now
        if current_word_count + new_line_word_count > self.config.max_words:
            return True

        # If we haven't reached min_words yet, don't close
        if current_word_count < self.config.min_words:
            return False

        # We're between min and max words - check for sentence boundary
        # Look at the last line's ending
        last_line_text = current_lines[-1][0]
        return self._ends_with_sentence_terminator(last_line_text)

    def _ends_with_sentence_terminator(self, text: str) -> bool:
        """Check if text ends with a sentence terminator.

        Args:
            text: Text to check

        Returns:
            True if text ends with . ? or !
        """
        # Strip trailing whitespace and check last character
        text = text.rstrip()
        if not text:
            return False

        # Check for sentence-ending punctuation
        return text[-1] in {".", "?", "!"}

    def _create_chunk(
        self,
        lines: List[Tuple[str, BoundingBox]],
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> DocumentChunk:
        """Create a DocumentChunk from accumulated lines.

        Args:
            lines: List of (text, bbox) tuples
            page_number: Page number
            metadata: Document metadata
            chunk_index: Index for this chunk

        Returns:
            DocumentChunk instance
        """
        # Combine text with spaces
        chunk_text = " ".join(text for text, _ in lines)

        # Extract bounding boxes and create enclosing bbox
        bboxes = [bbox for _, bbox in lines]
        combined_bbox = combine_bounding_boxes(bboxes)

        if self.config.debug:
            word_count = len(chunk_text.split())
            logger.debug(
                f"Page {page_number}, Chunk {chunk_index}: "
                f"{len(lines)} lines, {word_count} words, text='{chunk_text[:50]}...'"
            )

        # Create a mock layout block for compatibility with existing schema
        # Since we're not using layout blocks, we use a synthetic chunk type

        # Calculate average confidence from bounding boxes if available
        # Note: We're working with bboxes directly, confidence comes from the original Line objects
        # For simplicity, use a default confidence of 95.0
        avg_confidence = 95.0

        # Create a minimal object that satisfies the Layout interface
        class SyntheticBlock:
            """Synthetic block to maintain API compatibility with Layout interface."""

            def __init__(self) -> None:
                self.layout_type = "LINE_SENTENCE_CHUNK"
                self.confidence = avg_confidence

        return DocumentChunk.from_textractor_layout(
            block=SyntheticBlock(),  # type: ignore[arg-type]
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )
