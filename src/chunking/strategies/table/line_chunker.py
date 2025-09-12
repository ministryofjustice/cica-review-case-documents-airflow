import logging
import statistics
from typing import List, Optional

from textractor.data.constants import LINE
from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout, Line

from src.chunking.schemas import DocumentMetadata, OpenSearchDocument
from src.chunking.strategies.table.base import BaseTableChunker
from src.chunking.strategies.table.schemas import TextBlock

logger = logging.getLogger(__name__)


class LineTableChunker(BaseTableChunker):
    """Handles tables with Line structure - groups lines into visual rows"""

    def can_handle(self, layout_block: Layout) -> bool:
        """Check if layout contains Line objects"""
        return bool(layout_block.children) and isinstance(layout_block.children[0], Line)

    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[OpenSearchDocument]:
        """Process line-based table into visual row chunks"""
        logger.debug(f"Processing line-based table: {layout_block.id}")

        text_blocks = self._extract_text_blocks(layout_block, raw_response)
        visual_rows = self._group_into_visual_rows(text_blocks)

        chunks = []
        for row_blocks in visual_rows:
            if not row_blocks:
                continue

            chunk_text, bboxes = self._process_text_block_row(row_blocks)
            chunk = self._create_chunk(
                chunk_text=chunk_text,
                bboxes=bboxes,
                layout_block=layout_block,
                page_number=page_number,
                metadata=metadata,
                chunk_index=chunk_index_start + len(chunks),
            )
            chunks.append(chunk)

        logger.debug(f"Created {len(chunks)} chunks from line-based table")
        return chunks

    def _extract_text_blocks(self, layout_block: Layout, raw_response: Optional[dict]) -> List[TextBlock]:
        """Extract text blocks from lines, including missed ones from raw response."""
        text_blocks = self._convert_lines_to_text_blocks(layout_block.children)

        # Apply Textractor bug workaround if raw response available
        if raw_response:
            missed_blocks = self._recover_missed_lines(layout_block, raw_response)
            text_blocks.extend(missed_blocks)
            text_blocks.sort(key=lambda x: (x.top, x.left))

        return text_blocks

    def _convert_lines_to_text_blocks(self, children: List) -> List[TextBlock]:
        """Convert Textractor Line objects to TextBlock objects."""
        blocks = []

        for line in children:
            if not isinstance(line, Line) or not line.bbox or not line.text or not line.text.strip():
                continue

            try:
                text = line.raw_object.get("Text", line.text).strip()
                blocks.append(
                    TextBlock(
                        text=text,
                        bbox=line.bbox,
                        confidence=line.confidence,
                    )
                )
            except (AttributeError, KeyError) as e:
                logger.warning(f"Failed to convert line to TextBlock: {e}")

        return sorted(blocks, key=lambda x: (x.top, x.left))

    def _recover_missed_lines(self, layout_block: Layout, raw_response: dict) -> List[TextBlock]:
        """Workaround for Textractor bug: recover lines that should be children but are missed."""
        try:
            missed_ids = self._find_missed_line_ids(layout_block, raw_response)
            if not missed_ids:
                return []

            return self._create_text_blocks_from_missed_ids(missed_ids, raw_response, layout_block)

        except Exception as e:
            logger.error(f"Error recovering missed lines for block {layout_block.id}: {e}")
            return []

    def _find_missed_line_ids(self, layout_block: Layout, raw_response: dict) -> set:
        """Find line IDs that should be children but are missing."""
        id_map = {block["Id"]: block for block in raw_response.get("Blocks", [])}
        layout_json = id_map.get(layout_block.id)

        if not layout_json:
            return set()

        # Find expected vs actual child IDs
        expected_ids = set()
        for relationship in layout_json.get("Relationships", []):
            if relationship.get("Type") == "CHILD":
                expected_ids.update(relationship.get("Ids", []))

        actual_ids = {child.id for child in layout_block.children}
        return expected_ids - actual_ids

    def _create_text_blocks_from_missed_ids(
        self, missed_ids: set, raw_response: dict, layout_block: Layout
    ) -> List[TextBlock]:
        """Create TextBlock objects from missed line IDs."""
        id_map = {block["Id"]: block for block in raw_response.get("Blocks", [])}
        spatial_object = layout_block.bbox.spatial_object

        if not spatial_object:
            logger.warning(f"No spatial context for layout {layout_block.id}, skipping missed lines")
            return []

        text_blocks = []
        for child_id in missed_ids:
            block_json = id_map.get(child_id)
            if not block_json or block_json.get("BlockType") != LINE:
                continue

            text = block_json.get("Text", "").strip()
            if not text:
                continue

            try:
                bbox = BoundingBox.from_normalized_dict(
                    block_json["Geometry"]["BoundingBox"],
                    spatial_object=spatial_object,
                )
                text_blocks.append(
                    TextBlock(
                        text=text,
                        bbox=bbox,
                        confidence=block_json.get("Confidence", 0.0),
                    )
                )
            except Exception as e:
                logger.error(f"Failed to create TextBlock from missed line {child_id}: {e}")

        return text_blocks

    def _group_into_visual_rows(self, blocks: List[TextBlock]) -> List[List[TextBlock]]:
        """Group text blocks into visual rows based on vertical alignment."""
        y_tolerance_ratio = self.config.y_tolerance_ratio

        if not blocks:
            return []

        heights = [b.height for b in blocks if b.height > 0]
        if not heights:
            return [[b] for b in blocks]

        y_tolerance = statistics.mean(heights) * y_tolerance_ratio

        rows = []
        current_row = []

        for block in blocks:
            if not current_row:
                current_row = [block]
            elif abs(block.center_y - current_row[0].center_y) < y_tolerance:
                current_row.append(block)
            else:
                rows.append(current_row)
                current_row = [block]

        if current_row:
            rows.append(current_row)

        return rows

    def _process_text_block_row(self, blocks: List[TextBlock]) -> tuple[str, List[BoundingBox]]:
        """Process a row of text blocks, sorting by horizontal position."""
        sorted_blocks = sorted(blocks, key=lambda b: b.left)
        texts = [block.text for block in sorted_blocks]
        bboxes = [block.bbox for block in sorted_blocks]
        return " ".join(texts), bboxes
