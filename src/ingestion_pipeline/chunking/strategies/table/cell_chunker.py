"""Chunker for tables structured with cells."""

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout
from textractor.entities.table import Table
from textractor.entities.table_cell import TableCell

from ingestion_pipeline.chunking.exceptions import ChunkException
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.table.base import BaseTableChunker

logger = logging.getLogger(__name__)


class CellTableChunker(BaseTableChunker):
    """Handles tables with Cell/Table structure - one chunk per row."""

    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[DocumentChunk]:
        """Processes a cell-based table layout block into document chunks.

        Args:
            layout_block (Layout): The layout block to process.
            page_number (int): The page number of the layout block.
            metadata (DocumentMetadata): The metadata associated with the document.
            chunk_index_start (int): The starting index for chunk numbering.
            raw_response (Optional[dict], optional): Raw response from the source. Defaults to None.

        Returns:
            List[DocumentChunk]: A list of document chunks created from the layout block.
        """
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
        """Extract and group table cells by row index.

        Args:
            layout_block (Layout): The layout block containing the table.

        Raises:
            ChunkException: The layout block is not a valid table.
            ChunkException: The table contains invalid cell objects.

        Returns:
            Dict[int, List[TableCell]]: A dictionary mapping row indices to lists of table cells.
        """
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
                    f"Text: '{table.text}'."
                )

        return rows

    def _process_table_row(self, cells: List[TableCell]) -> tuple[str, List[BoundingBox]]:
        """Process a row of cells, handling merged cells and duplicates.

        Args:
        cells (List[TableCell]): the list of table cells in the row.

        Returns:
        tuple[str, List[BoundingBox]]: the concatenated text of the row and the list of bounding boxes.
        """
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
