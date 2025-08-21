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

    # --- CHANGE: Define a starting y-position and line height for layout ---
    current_y = 0.1
    line_height = 0.05
    word_spacing = 0.01

    for line_text in layout_def.get("lines", []):
        words = []

        # --- CHANGE: Define a starting x-position for words in this line ---
        current_x = 0.1

        word_texts = line_text.split()
        for i, word_text in enumerate(word_texts):
            # Create a bbox for the word with an incrementing x-position
            word_width = len(word_text) * 0.01  # Approximate width
            word_bbox = BoundingBox(x=current_x, y=current_y, width=word_width, height=line_height * 0.8)
            words.append(
                Word(
                    entity_id=f"word-{uuid.uuid4()}",
                    bbox=word_bbox,
                    text=word_text,
                    confidence=99,
                )
            )
            # Move x-position for the next word
            current_x += word_width + word_spacing

        # --- CHANGE: Create the Line's bounding box with the current_y position ---
        # The line's Bbox should encompass all its words
        line_bbox = BoundingBox.enclosing_bbox([w.bbox for w in words]) if words else _create_dummy_bbox()
        line = Line(entity_id=f"line-{uuid.uuid4()}", bbox=line_bbox, words=words)
        lines.append(line)

        # --- CHANGE: Increment the y-position for the next line ---
        current_y += line_height

    layout_type = layout_def.get("type", "LAYOUT_TEXT")
    layout_confidence = layout_def.get("confidence", 60.0)

    # The overall layout block should encompass all its lines
    layout_bbox = BoundingBox.enclosing_bbox([line.bbox for line in lines]) if lines else _create_dummy_bbox()

    layout_block = Layout(
        entity_id=f"layout-{uuid.uuid4()}",
        bbox=layout_bbox,
        confidence=layout_confidence,
        reading_order=reading_order,
        label=layout_type,
    )

    layout_block._children = lines

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
