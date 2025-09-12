import logging
from collections import defaultdict
from typing import Dict, List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout
from textractor.entities.table import Table
from textractor.entities.table_cell import TableCell

from src.chunking.exceptions import ChunkException
from src.chunking.schemas import DocumentMetadata, OpenSearchDocument
from src.chunking.strategies.table.base import BaseTableChunker

logger = logging.getLogger(__name__)


class CellTableChunker(BaseTableChunker):
    """Handles tables with Cell/Table structure - one chunk per row"""

    def can_handle(self, layout_block: Layout) -> bool:
        """Check if layout contains Table objects"""
        return any(isinstance(child, Table) for child in layout_block.children)

    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[OpenSearchDocument]:
        """Process cell-based table into row chunks"""
        logger.debug(f"++++++++++++++++++++ Processing cell-based table: {layout_block.id} ++++++++++++++")

        rows = self._group_cells_by_row(layout_block)

        chunks = []
        for row_index in sorted(rows.keys()):
            chunk_text, bboxes = self._process_table_row(rows[row_index])
            if chunk_text:  # Only create chunk if we have content
                chunk = self._create_chunk(
                    chunk_text=chunk_text,
                    bboxes=bboxes,
                    layout_block=layout_block,
                    page_number=page_number,
                    metadata=metadata,
                    chunk_index=chunk_index_start + len(chunks),
                )
                chunks.append(chunk)

        logger.debug(f"Created {len(chunks)} chunks from cell-based table")
        return chunks

    def _group_cells_by_row(self, layout_block: Layout) -> Dict[int, List[TableCell]]:
        """Extract and group table cells by row index."""
        rows = defaultdict(list)

        for table in layout_block.children:
            if isinstance(table, Table):
                for cell in table.table_cells:
                    if isinstance(cell, TableCell):
                        rows[cell.row_index].append(cell)
                    else:
                        # This is a data integrity error. The Table object is corrupt.
                        cell_type = type(cell).__name__
                        raise ChunkException(
                            f"Fatal error in table {table.id}: "
                            f"Expected only TableCell objects in table.table_cells, but found '{cell_type}'."
                        )
            else:
                # This is a data integrity error. The Table object is corrupt.
                block_type = type(table).__name__
                raise ChunkException(
                    f"Fatal error in table {table.id}: "
                    f"Expected instance of Table objects in layout_block.children, but found '{block_type}'."
                )

        return rows

    def _process_table_row(self, cells: List[TableCell]) -> tuple[str, List[BoundingBox]]:
        """Process a row of cells, handling merged cells and duplicates."""
        sorted_cells = sorted(cells, key=lambda c: (c.col_index, c.id))

        text_parts = []
        bboxes = []
        seen_texts = set()

        for cell in sorted_cells:
            bboxes.append(cell.bbox)
            cell_text = cell.text.strip()

            # Skip empty cells and duplicates (handles merged cells)
            if cell_text and cell_text not in seen_texts:
                text_parts.append(cell_text)
                seen_texts.add(cell_text)

        return " ".join(text_parts), bboxes
