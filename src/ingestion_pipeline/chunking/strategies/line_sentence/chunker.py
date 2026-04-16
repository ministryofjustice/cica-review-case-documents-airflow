"""Deterministic line-by-line sentence-aware chunking strategy.

This chunker operates directly on LINE blocks (not LAYOUT blocks) to avoid layout
detection issues. It prioritizes sentence integrity and vertical proximity over
complex layout-based grouping.
"""

import logging
from typing import List, Optional, Tuple

from textractor.entities.bbox import BoundingBox
from textractor.entities.line import Line

from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.line_sentence.accumulator import ChunkAccumulator
from ingestion_pipeline.chunking.strategies.line_sentence.chunk_builder import ChunkBuilder
from ingestion_pipeline.chunking.strategies.line_sentence.config import LineSentenceChunkingConfig
from ingestion_pipeline.chunking.strategies.line_sentence.line_preprocessor import filter_and_sort_lines
from ingestion_pipeline.chunking.strategies.line_sentence.sentence_detector import SentenceDetector
from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)


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
        self.config = config or LineSentenceChunkingConfig.from_settings(settings)
        self.chunk_builder = ChunkBuilder(self.config)
        self.sentence_detector = SentenceDetector()

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

        sorted_lines = filter_and_sort_lines(lines)

        chunks: List[DocumentChunk] = []
        chunk_index = chunk_index_start
        state = ChunkAccumulator()

        i = 0
        n = len(sorted_lines)
        while i < n:
            line_data = self._prepare_line_data(sorted_lines[i])
            if line_data is None:
                i += 1
                continue

            line_text, line_bbox, line_word_count = line_data

            self._log_line_debug(line_text, line_bbox)

            # Detect vertical gap before adding the line
            gap_reason = self._get_gap_reason(state.prev_line_bottom, line_bbox)

            # --- Gap break: behavior: emit current chunk, then start new chunk with gap-triggering line ---
            if gap_reason is not None:
                if state.lines:
                    chunk_index = self._emit_chunk(chunks, state.lines, page_number, metadata, chunk_index, gap_reason)
                state.start_with_line(line_text, line_bbox, line_word_count)
                i += 1
                continue

            # If not a gap break, proceed as normal
            state.add_line(line_text, line_bbox, line_word_count)

            # --- Sentence / max-words break ---
            if state.word_count >= self.config.min_words:
                should_close, reason, lookahead_count = self._check_forward_close(
                    sorted_lines, i, n, state.lines, state.word_count
                )

                if should_close and lookahead_count > 0:
                    # Absorb lookahead lines into current chunk
                    self._absorb_lookahead_lines(sorted_lines, i, lookahead_count, state)
                    i += lookahead_count

                if should_close:
                    chunk_index = self._emit_chunk(chunks, state.lines, page_number, metadata, chunk_index, reason)
                    state.reset()
                else:
                    # Try backward split: find last sentence boundary in current chunk
                    split_at = self._find_backward_split(state.lines)
                    if split_at is not None:
                        emit_lines, remaining_lines = state.split_at(split_at)
                        state.replace_lines(remaining_lines)
                        chunk_index = self._emit_chunk(
                            chunks, emit_lines, page_number, metadata, chunk_index, "backward_sentence_boundary"
                        )

            i += 1

        if state.lines:
            self._emit_chunk(chunks, state.lines, page_number, metadata, chunk_index, "final_chunk")

        logger.debug(f"Page {page_number}: Created {len(chunks)} chunks from {len(sorted_lines)} lines")

        return chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _prepare_line_data(self, line: Line) -> Optional[Tuple[str, BoundingBox, int]]:
        """Normalize and validate a line before chunking."""
        if not line.text or not line.bbox:
            return None

        line_text = line.text.strip()
        if not line_text:
            return None

        return line_text, line.bbox, len(line_text.split())

    def _log_line_debug(self, line_text: str, line_bbox: BoundingBox) -> None:
        """Emit per-line debug logs used by existing diagnostics."""
        logger.debug(
            '"%s",%s,%s,%s,%s,%s',
            line_text.replace(chr(34), chr(39)),
            line_text.split(),
            line_bbox.x,
            line_bbox.y,
            line_bbox.width,
            line_bbox.height,
        )

    def _get_gap_reason(self, prev_line_bottom: Optional[float], line_bbox: BoundingBox) -> Optional[str]:
        """Return a reason string when a vertical gap break should occur."""
        if prev_line_bottom is None:
            return None

        vertical_gap = line_bbox.y - prev_line_bottom
        if vertical_gap > self.config.max_vertical_gap_ratio:
            return f"vertical_gap={vertical_gap:.4f} > threshold={self.config.max_vertical_gap_ratio}"

        return None

    def _absorb_lookahead_lines(
        self,
        sorted_lines: List[Line],
        current_index: int,
        lookahead_count: int,
        state: ChunkAccumulator,
    ) -> None:
        """Absorb lookahead lines into state while preserving existing guards."""
        for k in range(1, lookahead_count + 1):
            line_data = self._prepare_line_data(sorted_lines[current_index + k])
            if line_data is None:
                continue
            line_text, line_bbox, line_word_count = line_data
            state.add_line(line_text, line_bbox, line_word_count)

    def _emit_chunk(
        self,
        chunks: List[DocumentChunk],
        lines: List[Tuple[str, BoundingBox]],
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
        reason: Optional[str],
    ) -> int:
        """Create and append a chunk, log the reason, and return the next chunk_index."""
        logger.debug(
            f"Creating chunk at page {page_number}, chunk_index={chunk_index}, "
            f"lines={len(lines)}, words={sum(len(t.split()) for t, _ in lines)}, reason={reason}"
        )
        chunk = self.chunk_builder.create_chunk(
            lines=lines,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
        )
        chunks.append(chunk)
        return chunk_index + 1

    def _check_forward_close(
        self,
        sorted_lines: List[Line],
        current_index: int,
        n: int,
        current_lines: List[Tuple[str, BoundingBox]],
        current_word_count: int,
    ) -> Tuple[bool, Optional[str], int]:
        """Look ahead up to 3 lines for a sentence boundary.

        Returns:
            (should_close, reason, lookahead_count) where lookahead_count is the
            number of additional lines to absorb before closing.
        """
        lookahead_limit = min(3, n - current_index - 1)
        for j in range(lookahead_limit + 1):
            if j == 0:
                candidate_text = current_lines[-1][0]
            else:
                next_line = sorted_lines[current_index + j]
                if not next_line.text:
                    continue
                candidate_text = next_line.text.strip()

            if self.sentence_detector.ends_with_sentence_terminator(candidate_text):
                extra_words = sum(
                    len(sorted_lines[current_index + k].text.strip().split())
                    for k in range(1, j + 1)
                    if sorted_lines[current_index + k].text
                )
                if current_word_count + extra_words <= self.config.max_words:
                    return True, "sentence_boundary", j
                break  # Would exceed max_words — fall through to backward/max check

        if current_word_count >= self.config.max_words:
            return True, f"max_words={current_word_count} >= {self.config.max_words}", 0

        return False, None, 0

    def _find_backward_split(self, current_lines: List[Tuple[str, BoundingBox]]) -> Optional[int]:
        """Scan backward through current_lines for the most recent sentence boundary.

        Returns the index *after* the boundary line (i.e. where the new chunk starts),
        or None if no boundary found.
        """
        for back in range(1, min(3, len(current_lines)) + 1):
            candidate_text = current_lines[-back][0]
            if self.sentence_detector.ends_with_sentence_terminator(candidate_text):
                split_at = len(current_lines) - back + 1  # include the boundary line in the emitted chunk
                if split_at > 0:
                    return split_at
        return None
