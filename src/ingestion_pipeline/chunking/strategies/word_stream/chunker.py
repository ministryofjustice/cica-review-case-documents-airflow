"""Chunking logic based on Textractor get_text_and_words() ordered words."""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.word import Word

from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.line_sentence.sentence_detector import SentenceDetector
from ingestion_pipeline.chunking.strategies.word_stream.config import WordStreamChunkingConfig
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes
from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)


@dataclass
class WordChunkState:
    """Mutable chunk accumulation state for word-stream chunking."""

    tokens: List[str] = field(default_factory=list)
    bboxes: List[BoundingBox] = field(default_factory=list)
    word_count: int = 0
    prev_bottom: Optional[float] = None

    def reset(self) -> None:
        """Reset the chunk state."""
        self.tokens.clear()
        self.bboxes.clear()
        self.word_count = 0
        self.prev_bottom = None


class TextractorWordStreamChunker:
    """Chunker that uses Textractor's reading-order word stream as source of truth."""

    _MULTI_SPACE_RE = re.compile(r"\s+")
    _PAGE_FOOTER_NUMBER_RE = re.compile(r"^\d+[\).,:;]?$")

    def __init__(self, config: Optional[WordStreamChunkingConfig] = None):
        """Initialize with optional configuration."""
        self.config = config or WordStreamChunkingConfig.from_settings(settings)
        self.sentence_detector = SentenceDetector()

    def chunk_page(
        self,
        words: List[Word],
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int = 0,
    ) -> List[DocumentChunk]:
        """Chunk a page's ordered words into sentence-aware chunks.

        Args:
            words: Reading-order words from Page.get_text_and_words().
            page_number: The page number (1-based).
            metadata: Document metadata.
            chunk_index_start: Starting index for chunk numbering.
        """
        if not words:
            return []

        words = self._filter_standalone_page_footer_words(words)
        if not words:
            return []

        chunks: List[DocumentChunk] = []
        state = WordChunkState()
        chunk_index = chunk_index_start

        i = 0
        n = len(words)
        while i < n:
            word = words[i]
            word_text = self._normalize_word_text(getattr(word, "text", ""))
            word_bbox = getattr(word, "bbox", None)
            word_count = len(word_text.split())

            if not word_text or word_bbox is None:
                i += 1
                continue

            gap_reason = self._get_gap_reason(state.prev_bottom, word_bbox)
            if gap_reason and state.tokens:
                if state.word_count > 1:
                    chunk_index = self._emit_chunk(chunks, state, page_number, metadata, chunk_index, gap_reason)
                    state.reset()

            if state.tokens and (state.word_count + word_count) > self.config.max_words:
                chunk_index = self._split_or_emit_at_hard_max(chunks, state, page_number, metadata, chunk_index)

            state.tokens.append(word_text)
            state.bboxes.append(word_bbox)
            state.word_count += word_count
            state.prev_bottom = word_bbox.y + word_bbox.height

            if state.word_count >= self.config.min_words:
                should_close, reason, lookahead_count = self._check_forward_close(words, i, n, state)
                if should_close and lookahead_count > 0:
                    consumed_lookahead_count, gap_reason = self._absorb_lookahead_words(
                        words, i, lookahead_count, state
                    )
                    i += consumed_lookahead_count

                    if gap_reason is not None:
                        should_close = True
                        reason = gap_reason
                    elif reason == "sentence_boundary" and consumed_lookahead_count < lookahead_count:
                        # Sentence-boundary close is only valid if the boundary word was consumed.
                        should_close = False
                        reason = None

                if should_close and state.word_count <= 1:
                    should_close = False
                    reason = None

                if should_close and reason == "sentence_boundary":
                    chunk_index = self._emit_chunk(chunks, state, page_number, metadata, chunk_index, reason)
                    state.reset()
                elif should_close and reason == "hard_max":
                    chunk_index = self._split_or_emit_at_hard_max(chunks, state, page_number, metadata, chunk_index)
                elif should_close and reason and reason.startswith("lookahead_vertical_gap"):
                    chunk_index = self._emit_chunk(chunks, state, page_number, metadata, chunk_index, reason)
                    state.reset()

            i += 1

        if state.tokens:
            if state.word_count == 1 and chunks:
                self._append_state_to_last_chunk(chunks[-1], state)
            else:
                self._emit_chunk(chunks, state, page_number, metadata, chunk_index, "final_chunk")

        return chunks

    def _append_state_to_last_chunk(self, last_chunk: DocumentChunk, state: WordChunkState) -> None:
        """Append remaining state tokens/bboxes to an existing chunk to avoid singleton chunks."""
        if not state.tokens or not state.bboxes:
            return

        appended_text = self._normalize_chunk_text(state.tokens)
        if not appended_text:
            return

        merged_text = self._normalize_chunk_text([last_chunk.chunk_text, appended_text])
        existing_bbox = last_chunk.bounding_box.to_textractor_bbox()
        merged_bbox = combine_bounding_boxes([existing_bbox, *state.bboxes])

        last_chunk.chunk_text = merged_text
        last_chunk.bounding_box = last_chunk.bounding_box.from_textractor_bbox(merged_bbox)

    def _filter_standalone_page_footer_words(self, words: List[Word]) -> List[Word]:
        """Remove standalone footer lines matching pattern: Page X of Y."""
        filtered_words: List[Word] = []
        i = 0
        n = len(words)

        while i < n:
            footer_span = self._match_page_footer_span(words, i)
            if footer_span == 0:
                filtered_words.append(words[i])
                i += 1
                continue
            i += footer_span

        return filtered_words

    def _match_page_footer_span(self, words: List[Word], index: int) -> int:
        """Return footer token span length when words[index:] starts with standalone Page X of Y."""
        if index + 3 >= len(words):
            return 0

        tokens = [self._normalize_word_text(getattr(words[index + offset], "text", "")) for offset in range(4)]
        if not tokens[0] or not tokens[1] or not tokens[2] or not tokens[3]:
            return 0

        is_footer_pattern = (
            tokens[0].lower() == "page"
            and tokens[2].lower() == "of"
            and bool(self._PAGE_FOOTER_NUMBER_RE.fullmatch(tokens[1]))
            and bool(self._PAGE_FOOTER_NUMBER_RE.fullmatch(tokens[3]))
        )
        if not is_footer_pattern:
            return 0

        current_bbox = getattr(words[index], "bbox", None)
        next_bbox = getattr(words[index + 3], "bbox", None)
        if current_bbox is None or next_bbox is None:
            return 0

        if index > 0:
            prev_bbox = getattr(words[index - 1], "bbox", None)
            if prev_bbox is not None and abs(prev_bbox.y - current_bbox.y) < 0.001:
                return 0

        if index + 4 < len(words):
            after_bbox = getattr(words[index + 4], "bbox", None)
            if after_bbox is not None and abs(after_bbox.y - next_bbox.y) < 0.001:
                return 0

        return 4

    @staticmethod
    def _normalize_word_text(text: str) -> str:
        """Trim and collapse whitespace in individual word text."""
        return re.sub(r"\s+", " ", text).strip()

    def _normalize_chunk_text(self, tokens: List[str]) -> str:
        """Normalize chunk text and collapse whitespace."""
        text = " ".join(tokens)
        if not self.config.normalize_spacing:
            return text.strip()

        text = self._MULTI_SPACE_RE.sub(" ", text)
        return text.strip()

    def _get_gap_reason(self, prev_bottom: Optional[float], bbox: BoundingBox) -> Optional[str]:
        """Return reason text when a vertical gap break should occur."""
        if prev_bottom is None:
            return None

        vertical_gap = bbox.y - prev_bottom
        if vertical_gap > self.config.max_vertical_gap_ratio:
            return f"vertical_gap={vertical_gap:.4f} > threshold={self.config.max_vertical_gap_ratio}"
        return None

    def _check_forward_close(
        self,
        words: List[Word],
        current_index: int,
        n: int,
        state: WordChunkState,
    ) -> tuple[bool, Optional[str], int]:
        """Look ahead for a nearby sentence boundary while respecting hard max."""
        lookahead_limit = min(self.config.forward_lookahead_words, n - current_index - 1)

        for j in range(lookahead_limit + 1):
            if j == 0:
                candidate_text = state.tokens[-1] if state.tokens else ""
            else:
                next_text = self._normalize_word_text(getattr(words[current_index + j], "text", ""))
                if not next_text:
                    continue
                candidate_text = next_text

            if self.sentence_detector.ends_with_sentence_terminator(candidate_text):
                extra_words = 0
                for k in range(1, j + 1):
                    ahead_text = self._normalize_word_text(getattr(words[current_index + k], "text", ""))
                    if ahead_text:
                        extra_words += len(ahead_text.split())

                if (state.word_count + extra_words) <= self.config.max_words:
                    return True, "sentence_boundary", j
                break

        if state.word_count >= self.config.max_words:
            return True, "hard_max", 0

        return False, None, 0

    def _absorb_lookahead_words(
        self,
        words: List[Word],
        current_index: int,
        lookahead_count: int,
        state: WordChunkState,
    ) -> tuple[int, Optional[str]]:
        """Absorb lookahead words into the current chunk state.

        Returns:
            Tuple of (consumed_lookahead_count, gap_reason). consumed_lookahead_count
            represents how many lookahead positions were consumed from the input stream.
            gap_reason is set when lookahead absorption stops due to vertical gap.
        """
        consumed_lookahead_count = 0
        for k in range(1, lookahead_count + 1):
            word = words[current_index + k]
            word_text = self._normalize_word_text(getattr(word, "text", ""))
            word_bbox = getattr(word, "bbox", None)
            if not word_text or word_bbox is None:
                consumed_lookahead_count = k
                continue

            gap_reason = self._get_gap_reason(state.prev_bottom, word_bbox)
            if gap_reason is not None:
                return consumed_lookahead_count, f"lookahead_{gap_reason}"

            state.tokens.append(word_text)
            state.bboxes.append(word_bbox)
            state.word_count += len(word_text.split())
            state.prev_bottom = word_bbox.y + word_bbox.height
            consumed_lookahead_count = k

        return consumed_lookahead_count, None

    def _find_backward_split(self, tokens: List[str]) -> Optional[int]:
        """Return index after nearest backward sentence boundary token."""
        limit = min(self.config.backward_scan_words, len(tokens))
        for back in range(1, limit + 1):
            candidate_text = tokens[-back]
            if self.sentence_detector.ends_with_sentence_terminator(candidate_text):
                split_at = len(tokens) - back + 1
                if 0 < split_at < len(tokens):
                    return split_at
        return None

    def _split_or_emit_at_hard_max(
        self,
        chunks: List[DocumentChunk],
        state: WordChunkState,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> int:
        """Prefer backward sentence split at hard max, else force-close current state."""
        split_at = self._find_backward_split(state.tokens)
        if split_at is None:
            if state.word_count <= 1:
                return chunk_index

            chunk_index = self._emit_chunk(
                chunks,
                state,
                page_number,
                metadata,
                chunk_index,
                f"would_exceed_max_words current_words={state.word_count} max_words={self.config.max_words}",
            )
            state.reset()
            return chunk_index

        emit_state = WordChunkState(
            tokens=state.tokens[:split_at],
            bboxes=state.bboxes[:split_at],
            word_count=sum(len(token.split()) for token in state.tokens[:split_at]),
            prev_bottom=state.bboxes[split_at - 1].y + state.bboxes[split_at - 1].height,
        )
        chunk_index = self._emit_chunk(
            chunks,
            emit_state,
            page_number,
            metadata,
            chunk_index,
            "backward_sentence_boundary",
        )

        state.tokens = state.tokens[split_at:]
        state.bboxes = state.bboxes[split_at:]
        state.word_count = sum(len(token.split()) for token in state.tokens)
        state.prev_bottom = None
        if state.bboxes:
            last_bbox = state.bboxes[-1]
            state.prev_bottom = last_bbox.y + last_bbox.height
        return chunk_index

    def _emit_chunk(
        self,
        chunks: List[DocumentChunk],
        state: WordChunkState,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
        reason: str,
    ) -> int:
        """Create and append one chunk, returning the next chunk index."""
        chunk_text = self._normalize_chunk_text(state.tokens)
        combined_bbox = combine_bounding_boxes(state.bboxes)
        logger.debug(
            "Creating word-stream chunk page=%s index=%s words=%s reason=%s",
            page_number,
            chunk_index,
            state.word_count,
            reason,
        )

        chunk = DocumentChunk.create_chunk(
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
            layout_type="TEXTRACT_WORD_STREAM_CHUNK",
            confidence=None,
        )
        chunks.append(chunk)
        return chunk_index + 1
