import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import List

from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout
from textractor.entities.line import Line
from textractor.entities.table import Table
from textractor.entities.table_cell import TableCell

from src.chunking.schemas import DocumentMetadata, OpenSearchDocument
from src.chunking.strategies.base import ChunkingStrategyHandler

logger = logging.getLogger(__name__)


@dataclass
class TextBlock:
    """Represents a text block from Textract with its geometry"""

    text: str
    top: float
    left: float
    width: float
    height: float
    bbox: BoundingBox
    confidence: float = 0.0

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def center_y(self) -> float:
        return self.top + (self.height / 2)


class LayoutTableChunkingStrategy(ChunkingStrategyHandler):
    """
    Implements a chunking strategy for LAYOUT_TABLE blocks.
    It detects if the table is structured by Cells or Lines and chunks accordingly.
    - For Cell structures, it creates one chunk per table row.
    - For Line structures, it groups lines into visually aligned rows.
    """

    def chunk(
        self, layout_block: Layout, page_number: int, metadata: DocumentMetadata, chunk_index_start: int
    ) -> List[OpenSearchDocument]:
        """
        Detects the table structure and dispatches to the appropriate chunking method.
        """
        if not layout_block.children:
            logger.warning(f"Layout table block {layout_block.id} has no children to process.")
            return []

        # Correctly check for the Table object within the Layout block
        first_child = layout_block.children[0]
        if isinstance(first_child, Table):
            logger.debug(f"Detected LAYOUT_TABLE with Table/Cell structure for block {layout_block.id}.")
            return self._chunk_by_cells(layout_block, page_number, metadata, chunk_index_start)
        elif isinstance(first_child, Line):
            logger.debug(f"Detected LAYOUT_TABLE with Line structure for block {layout_block.id}.")
            return self._chunk_by_lines(layout_block, page_number, metadata, chunk_index_start)
        else:
            logger.warning(
                f"Unsupported child type in LAYOUT_TABLE: {type(first_child)}. Skipping block {layout_block.id}."
            )
            return []

    def _chunk_by_cells(
        self, layout_block: Layout, page_number: int, metadata: DocumentMetadata, chunk_index_start: int
    ) -> List[OpenSearchDocument]:
        """
        Chunks a LAYOUT_TABLE where children are Cell objects. One chunk is created per row.
        """
        chunks = []
        current_chunk_index = chunk_index_start

        rows = defaultdict(list)

        for table in layout_block.children:
            for cell in table.table_cells:
                if isinstance(cell, TableCell):
                    rows[cell.row_index].append(cell)

        for row_index in sorted(rows.keys()):
            sorted_cells = sorted(rows[row_index], key=lambda c: (c.col_index, c.id))

            row_text_parts = []
            row_bboxes = []
            seen_texts = set()

            for cell in sorted_cells:
                row_bboxes.append(cell.bbox)

                cell_text = cell.text.strip()
                if cell_text and cell.text not in seen_texts:
                    row_text_parts.append(cell_text)
                    seen_texts.add(cell.text)

            if not row_text_parts:
                continue

            current_chunk_text = " ".join(row_text_parts)

            chunk = self._create_chunk(
                chunk_text=current_chunk_text,
                bboxes=row_bboxes,
                layout_block=layout_block,
                page_number=page_number,
                metadata=metadata,
                chunk_index=current_chunk_index,
            )
            chunks.append(chunk)
            current_chunk_index += 1

        return chunks

    def _chunk_by_lines(
        self, layout_block: Layout, page_number: int, metadata: DocumentMetadata, chunk_index_start: int
    ) -> List[OpenSearchDocument]:
        """
        Extract chunks by grouping Line objects into visually aligned rows.
        """
        chunks = []
        current_chunk_index = chunk_index_start

        text_blocks = self._convert_lines_to_textblocks(layout_block.children)
        visual_lines = self._group_blocks_into_visual_lines(text_blocks)

        for line_of_blocks in visual_lines:
            if not line_of_blocks:
                continue

            sorted_line_of_blocks = sorted(line_of_blocks, key=lambda b: b.left)
            current_chunk_text = " ".join([block.text for block in sorted_line_of_blocks])
            current_chunk_bboxes = [block.bbox for block in sorted_line_of_blocks]

            chunk = self._create_chunk(
                chunk_text=current_chunk_text,
                bboxes=current_chunk_bboxes,
                layout_block=layout_block,
                page_number=page_number,
                metadata=metadata,
                chunk_index=current_chunk_index,
            )
            chunks.append(chunk)
            current_chunk_index += 1

        return chunks

    def _convert_lines_to_textblocks(self, children: List) -> List[TextBlock]:
        """Converts Textractor Line objects to our internal TextBlock dataclass."""
        blocks = []

        for i, line in enumerate(children):
            if isinstance(line, Line) and hasattr(line, "bbox") and line.bbox is not None:
                geometry = line.bbox
                if line.text and line.text.strip():
                    try:
                        blocks.append(
                            TextBlock(
                                text=line.text.strip(),
                                top=geometry.y,
                                left=geometry.x,
                                width=geometry.width,
                                height=geometry.height,
                                confidence=line.confidence,
                                bbox=geometry,
                            )
                        )
                    except AttributeError as e:
                        logger.warning(f"  > FAILED to create TextBlock from Line. Error: {e}")
        return sorted(blocks, key=lambda x: (x.top, x.left))

    def _create_chunk(
        self,
        chunk_text: str,
        bboxes: List[BoundingBox],
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> OpenSearchDocument:
        """Create a chunk from accumulated lines and bounding boxes."""

        if not bboxes:
            combined_bbox = layout_block.bbox
        else:
            combined_bbox = BoundingBox.enclosing_bbox(bboxes)

        return OpenSearchDocument.from_textractor_layout(
            block=layout_block,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )

    def _group_blocks_into_visual_lines(
        self, blocks: List[TextBlock], y_tolerance_ratio: float = 0.5
    ) -> List[List[TextBlock]]:
        """
        Groups TextBlock objects into visual lines based on vertical proximity.
        """
        if not blocks:
            return []

        heights = [block.height for block in blocks if block.height > 0]
        if not heights:
            return [[b] for b in blocks]

        avg_height = statistics.mean(heights)
        y_tolerance = avg_height * y_tolerance_ratio

        visual_lines = []
        current_line = []

        for block in blocks:
            if not current_line:
                current_line.append(block)
            else:
                first_block_in_line = current_line[0]
                if abs(block.center_y - first_block_in_line.center_y) < y_tolerance:
                    current_line.append(block)
                else:
                    visual_lines.append(current_line)
                    current_line = [block]

        if current_line:
            visual_lines.append(current_line)

        return visual_lines
