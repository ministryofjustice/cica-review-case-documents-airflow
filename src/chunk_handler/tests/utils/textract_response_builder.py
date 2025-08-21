import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.document import Document
from textractor.entities.layout import Layout
from textractor.entities.line import Line
from textractor.entities.page import Page
from textractor.entities.word import Word


@dataclass
class LayoutConfig:
    """Configuration for layout positioning and sizing."""

    page_margin: float = 0.05
    line_height: float = 0.04
    word_spacing: float = 0.008
    char_width: float = 0.008
    default_confidence: float = 95.0
    page_width: int = 1000
    page_height: int = 1200


class BoundingBoxCalculator:
    """Handles bounding box calculations for document elements."""

    def __init__(self, config: LayoutConfig):
        self.config = config

    def create_dummy_bbox(self) -> BoundingBox:
        """Creates a placeholder BoundingBox for empty elements."""
        margin = self.config.page_margin
        return BoundingBox(x=margin, y=margin, width=0.01, height=0.01)

    def calculate_word_bbox(self, text: str, x: float, y: float) -> BoundingBox:
        """Calculate bounding box for a word based on its text length."""
        width = len(text) * self.config.char_width
        height = self.config.line_height * 0.8
        return BoundingBox(x=x, y=y, width=width, height=height)

    def calculate_line_bbox(self, words: List[Word]) -> BoundingBox:
        """Calculate enclosing bounding box for a line's words."""
        if not words:
            return self.create_dummy_bbox()
        return BoundingBox.enclosing_bbox([word.bbox for word in words])

    def calculate_layout_bbox(self, lines: List[Line]) -> BoundingBox:
        """Calculate enclosing bounding box for a layout's lines."""
        if not lines:
            return self.create_dummy_bbox()
        return BoundingBox.enclosing_bbox([line.bbox for line in lines])


class WordBuilder:
    """Builds Word entities with proper positioning."""

    def __init__(self, bbox_calculator: BoundingBoxCalculator, config: LayoutConfig):
        self.bbox_calc = bbox_calculator
        self.config = config

    def build_words_for_line(self, line_text: str, y: float) -> List[Word]:
        """Build a list of Word objects for a line of text."""
        if not line_text.strip():
            return []

        words = []
        current_x = self.config.page_margin
        word_texts = line_text.split()

        for word_text in word_texts:
            word_bbox = self.bbox_calc.calculate_word_bbox(word_text, current_x, y)

            word = Word(
                entity_id=f"word-{uuid.uuid4()}",
                bbox=word_bbox,
                text=word_text,
                confidence=self.config.default_confidence,
            )
            words.append(word)

            # Move x-position for next word
            current_x += word_bbox.width + self.config.word_spacing

        return words


class LineBuilder:
    """Builds Line entities with proper word positioning."""

    def __init__(self, word_builder: WordBuilder, bbox_calculator: BoundingBoxCalculator):
        self.word_builder = word_builder
        self.bbox_calc = bbox_calculator

    def build_line(self, line_text: str, y: float) -> Optional[Line]:
        """Build a Line object from text, returning None for empty lines."""
        if not line_text.strip():
            return None

        words = self.word_builder.build_words_for_line(line_text, y)
        if not words:
            return None

        line_bbox = self.bbox_calc.calculate_line_bbox(words)
        line = Line(entity_id=f"line-{uuid.uuid4()}", bbox=line_bbox, words=words)

        # Set line reference on words (Word class uses line_id and line_bbox attributes)
        # This follows the same pattern used in Line.get_text_and_words()
        for word in words:
            # Use setattr to avoid type checker issues with potentially restrictive type hints
            setattr(word, "line_id", line.id)
            setattr(word, "line_bbox", line.bbox)

        return line


class LayoutBuilder:
    """Builds Layout entities with proper line positioning."""

    def __init__(self, line_builder: LineBuilder, bbox_calculator: BoundingBoxCalculator, config: LayoutConfig):
        self.line_builder = line_builder
        self.bbox_calc = bbox_calculator
        self.config = config

    def build_layout_block(self, layout_def: Dict, reading_order: int) -> Optional[Layout]:
        """Build a Layout object from a simplified definition."""
        lines = []
        current_y = self.config.page_margin

        line_texts = layout_def.get("lines", [])
        if not line_texts:
            return None

        # Build lines with proper positioning
        for line_text in line_texts:
            line = self.line_builder.build_line(line_text, current_y)
            if line:  # Only add non-empty lines
                lines.append(line)
            current_y += self.config.line_height

        if not lines:
            return None

        # Create layout block
        layout_type = layout_def.get("type", "LAYOUT_TEXT")
        layout_confidence = layout_def.get("confidence", self.config.default_confidence)
        layout_bbox = self.bbox_calc.calculate_layout_bbox(lines)

        layout_block = Layout(
            entity_id=f"layout-{uuid.uuid4()}",
            bbox=layout_bbox,
            confidence=layout_confidence,
            reading_order=reading_order,
            label=layout_type,
        )

        # Set up parent-child relationships
        layout_block._children = lines
        # Set layout references on words (using setattr to avoid type checker issues)
        for line in lines:
            for word in line.words:
                setattr(word, "layout_id", layout_block.id)
                setattr(word, "layout_type", layout_type)
                setattr(word, "layout_bbox", layout_bbox)

        return layout_block


class PageBuilder:
    """Builds Page entities with proper layout positioning."""

    def __init__(self, layout_builder: LayoutBuilder, config: LayoutConfig):
        self.layout_builder = layout_builder
        self.config = config

    def build_page(self, page_def: List[Dict], page_number: int, reading_order_counter: int) -> tuple[Page, int]:
        """
        Build a Page object from layout definitions.

        Returns:
            tuple: (Page object, updated reading_order_counter)
        """
        page_id = f"page-{page_number}-{uuid.uuid4()}"
        layout_blocks = []

        for layout_def in page_def:
            layout_block = self.layout_builder.build_layout_block(layout_def, reading_order_counter)
            if layout_block:  # Only add non-empty layouts
                layout_blocks.append(layout_block)
                reading_order_counter += 1

        page = Page(
            id=page_id,
            page_num=page_number,
            width=self.config.page_width,
            height=self.config.page_height,
        )

        # Set page relationships using the Page class setters
        page.layouts = layout_blocks

        # Collect all lines and words for page-level access
        all_lines = []
        all_words = []
        for layout in layout_blocks:
            all_lines.extend(layout.children)
            for line in layout.children:
                all_words.extend(line.children)

        page.lines = all_lines
        page.words = all_words

        # Set page number on all entities (Page class expects this)
        for word in all_words:
            word.page = page_number
        for line in all_lines:
            line.page = page_number

        return page, reading_order_counter


class TextractorDocumentFactory:
    """
    Factory class for creating mock Textractor Document objects.

    This class provides a clean interface for building complex document structures
    from simplified definitions while maintaining proper entity relationships.
    """

    def __init__(self, config: Optional[LayoutConfig] = None):
        self.config = config or LayoutConfig()

        # Initialize builders in dependency order
        self.bbox_calc = BoundingBoxCalculator(self.config)
        self.word_builder = WordBuilder(self.bbox_calc, self.config)
        self.line_builder = LineBuilder(self.word_builder, self.bbox_calc)
        self.layout_builder = LayoutBuilder(self.line_builder, self.bbox_calc, self.config)
        self.page_builder = PageBuilder(self.layout_builder, self.config)

    def create_document(self, page_definitions: List[List[Dict]]) -> Document:
        """
        Create a Document from simplified page definitions.

        Args:
            page_definitions: List of pages, where each page is a list of layout definitions.
                             Each layout definition should have:
                             - type: Layout type (e.g., "LAYOUT_TEXT", "LAYOUT_TITLE")
                             - lines: List of text strings
                             - confidence: Optional confidence score

        Returns:
            Document: A fully constructed Textractor Document object

        Example:
            >>> factory = TextractorDocumentFactory()
            >>> doc = factory.create_document(
            ...     [
            ...         [  # Page 1
            ...             {"type": "LAYOUT_TEXT", "lines": ["Hello world"]},
            ...             {"type": "LAYOUT_TITLE", "lines": ["My Title"]},
            ...         ]
            ...     ]
            ... )
        """
        if not page_definitions:
            return Document()

        pages = []
        reading_order_counter = 0

        for page_number, page_def in enumerate(page_definitions, 1):
            page, reading_order_counter = self.page_builder.build_page(page_def, page_number, reading_order_counter)
            pages.append(page)

        document = Document(num_pages=len(pages))
        document.pages = pages

        return document


# Convenience function to maintain backward compatibility
def textractor_document_factory(page_definitions: List[List[Dict]]) -> Document:
    """
    Legacy function for backward compatibility.

    For new code, prefer using TextractorDocumentFactory directly for better
    configuration control and testing flexibility.
    """
    factory = TextractorDocumentFactory()
    return factory.create_document(page_definitions)
