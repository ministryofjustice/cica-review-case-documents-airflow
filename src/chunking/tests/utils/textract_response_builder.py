import uuid

from textractor.entities.bbox import BoundingBox
from textractor.entities.document import Document
from textractor.entities.layout import Layout
from textractor.entities.line import Line
from textractor.entities.page import Page
from textractor.entities.word import Word


def _create_dummy_bbox() -> BoundingBox:
    """Creates a placeholder BoundingBox."""
    return BoundingBox(x=0.1, y=0.1, width=0.1, height=0.1)


def _build_layout_block(layout_def: dict, reading_order: int) -> Layout:
    """Builds a single Layout object from a simplified definition."""
    lines = []
    for line_text in layout_def.get("lines", []):
        words = [
            Word(
                entity_id=f"word-{uuid.uuid4()}",
                bbox=_create_dummy_bbox(),
                text=word_text,
                confidence=99,
            )
            for word_text in line_text.split()
        ]
        line = Line(entity_id=f"line-{uuid.uuid4()}", bbox=_create_dummy_bbox(), words=words)
        lines.append(line)

    layout_type = layout_def.get("type", "LAYOUT_TEXT")
    layout_confidence = layout_def.get("confidence", 60.0)

    # The constructor correctly handles the confidence value.
    # It takes a value like 60.0 and stores it as 0.60 in `_confidence`.
    layout_block = Layout(
        entity_id=f"layout-{uuid.uuid4()}",
        bbox=_create_dummy_bbox(),
        confidence=layout_confidence,
        reading_order=reading_order,
        label=layout_type,
    )

    # Assign to the private _children attribute because .children is read-only.
    layout_block._children = lines

    # Establish the parent-child links for full realism.
    for line in layout_block._children:
        line.parent = layout_block
        for word in line.children:
            word.parent = line

    return layout_block


def textractor_document_factory(page_definitions: list[list[dict]]) -> Document:
    """
    Builds a valid in-memory textractor.Document object from a simplified definition.
    """
    pages = []
    layout_reading_order_counter = 0
    for i, page_def in enumerate(page_definitions, 1):
        page_id = f"page-{i}-{uuid.uuid4()}"

        layout_blocks = []
        for layout_def in page_def:
            layout_blocks.append(_build_layout_block(layout_def, layout_reading_order_counter))
            layout_reading_order_counter += 1

        page = Page(
            id=page_id,
            page_num=i,
            width=1000,
            height=1200,
        )

        page.layouts = layout_blocks

        all_lines = []
        for layout in layout_blocks:
            all_lines.extend(layout.children)
        page.lines = all_lines

        all_words = []
        for line in all_lines:
            all_words.extend(line.children)
        page.words = all_words

        pages.append(page)

    doc = Document()
    doc.pages = pages

    return doc
