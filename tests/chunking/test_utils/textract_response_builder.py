import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

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


class RawObjectBuilder:
    """Creates mock raw Textract JSON blocks for entities."""

    def _build_geometry(self, bbox: BoundingBox) -> Dict:
        """Builds the 'Geometry' part of a Textract block."""
        return {
            "BoundingBox": {
                "Width": bbox.width,
                "Height": bbox.height,
                "Left": bbox.x,
                "Top": bbox.y,
            },
            "Polygon": [
                {"X": bbox.x, "Y": bbox.y},
                {"X": bbox.x + bbox.width, "Y": bbox.y},
                {"X": bbox.x + bbox.width, "Y": bbox.y + bbox.height},
                {"X": bbox.x, "Y": bbox.y + bbox.height},
            ],
        }

    def build_word_block(self, word: Word) -> Dict:
        """Builds a raw 'WORD' block."""
        return {
            "BlockType": "WORD",
            "Confidence": word.confidence,
            "Text": word.text,
            "TextType": "PRINTED",
            "Id": word.id,
            "Geometry": self._build_geometry(word.bbox),
        }

    def build_line_block(self, line: Line) -> Dict:
        """Builds a raw 'LINE' block with relationships."""
        word_ids = [word.id for word in line.words]
        return {
            "BlockType": "LINE",
            "Confidence": 99.0,  # Line confidence is often high
            "Text": line.text,
            "Id": line.id,
            "Geometry": self._build_geometry(line.bbox),
            "Relationships": [{"Type": "CHILD", "Ids": word_ids}],
        }

    def build_layout_block(self, layout: Layout) -> Dict:
        """Builds a raw 'LAYOUT' block with relationships."""
        line_ids = [line.id for line in layout.children]
        return {
            "BlockType": layout.layout_type,
            "Confidence": layout.confidence,
            "Id": layout.id,
            "Geometry": self._build_geometry(layout.bbox),
            "Relationships": [{"Type": "CHILD", "Ids": line_ids}],
        }

    def build_page_block(self, page: Page, child_ids: List[str]) -> Dict:
        """Builds a raw 'PAGE' block with relationships."""
        return {
            "BlockType": "PAGE",
            "Id": page.id,
            "Geometry": self._build_geometry(BoundingBox(0, 0, 1, 1)),
            "Relationships": [{"Type": "CHILD", "Ids": child_ids}],
        }


class WordBuilder:
    """Builds Word entities with proper positioning."""

    def __init__(
        self, bbox_calculator: BoundingBoxCalculator, config: LayoutConfig, raw_object_builder: RawObjectBuilder
    ):
        self.bbox_calc = bbox_calculator
        self.config = config
        self.raw_builder = raw_object_builder

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
            word.raw_object = self.raw_builder.build_word_block(word)
            words.append(word)

            # Move x-position for next word
            current_x += word_bbox.width + self.config.word_spacing

        return words


class LineBuilder:
    """Builds Line entities with proper word positioning."""

    def __init__(
        self, word_builder: WordBuilder, bbox_calculator: BoundingBoxCalculator, raw_object_builder: RawObjectBuilder
    ):
        self.word_builder = word_builder
        self.bbox_calc = bbox_calculator
        self.raw_builder = raw_object_builder

    def build_line(self, line_def: Union[str, dict], y: float) -> Optional[Line]:
        """Build a Line object from a string or dictionary definition."""
        if isinstance(line_def, str):
            line_text = line_def
            line_bbox = None
        elif isinstance(line_def, dict):
            line_text = line_def.get("text", "").strip()
            line_bbox = line_def.get("bbox")
        else:
            return None

        if not line_text:
            return None

        if not line_bbox:
            words = self.word_builder.build_words_for_line(line_text, y)
            if not words:
                return None
            line_bbox = self.bbox_calc.calculate_line_bbox(words)
        else:
            word = Word(
                entity_id=f"word-{uuid.uuid4()}",
                bbox=line_bbox,
                text=line_text,
                confidence=self.word_builder.config.default_confidence,
            )
            word.raw_object = self.raw_builder.build_word_block(word)
            words = [word]

        line = Line(entity_id=f"line-{uuid.uuid4()}", bbox=line_bbox, words=words)
        line.raw_object = self.raw_builder.build_line_block(line)

        for word in words:
            setattr(word, "line_id", line.id)
            setattr(word, "line_bbox", line.bbox)

        return line


class LayoutBuilder:
    """Builds Layout entities with proper line positioning."""

    def __init__(
        self,
        line_builder: LineBuilder,
        bbox_calculator: BoundingBoxCalculator,
        config: LayoutConfig,
        raw_object_builder: RawObjectBuilder,
    ):
        self.line_builder = line_builder
        self.bbox_calc = bbox_calculator
        self.config = config
        self.raw_builder = raw_object_builder

    def build_layout_block(self, layout_def: Dict, reading_order: int) -> Optional[Layout]:
        """Build a Layout object from a simplified definition."""
        lines = []
        current_y = self.config.page_margin

        line_definitions = layout_def.get("lines", [])
        if not line_definitions:
            return None

        for line_def in line_definitions:
            line = self.line_builder.build_line(line_def, current_y)
            if line:
                lines.append(line)
            current_y += self.config.line_height

        if not lines:
            return None

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

        layout_block._children = lines
        layout_block.raw_object = self.raw_builder.build_layout_block(layout_block)

        for line in lines:
            for word in line.words:
                setattr(word, "layout_id", layout_block.id)
                setattr(word, "layout_type", layout_type)
                setattr(word, "layout_bbox", layout_bbox)

        return layout_block


class PageBuilder:
    """Builds Page entities with proper layout positioning."""

    def __init__(self, layout_builder: LayoutBuilder, config: LayoutConfig, raw_object_builder: RawObjectBuilder):
        self.layout_builder = layout_builder
        self.config = config
        self.raw_builder = raw_object_builder

    def build_page(
        self, page_def: List[Dict], page_number: int, reading_order_counter: int
    ) -> tuple[Page, int, List[Dict]]:
        """
        Build a Page object and a list of its raw JSON blocks.

        Returns:
            tuple: (Page object, updated reading_order_counter, list of all raw blocks)
        """
        page_id = f"page-{page_number}-{uuid.uuid4()}"
        layout_blocks = []
        page_raw_blocks = []

        for layout_def in page_def:
            layout_block = self.layout_builder.build_layout_block(layout_def, reading_order_counter)
            if layout_block:
                layout_blocks.append(layout_block)
                reading_order_counter += 1

                # Collect all raw blocks from the layout and its children
                page_raw_blocks.append(layout_block.raw_object)
                for line in layout_block.children:
                    page_raw_blocks.append(line.raw_object)
                    for word in line.children:
                        page_raw_blocks.append(word.raw_object)

        page = Page(
            id=page_id,
            page_num=page_number,
            width=self.config.page_width,
            height=self.config.page_height,
        )

        # Create the PAGE block itself and add it to the list, prepending it
        all_child_ids_on_page = [block["Id"] for block in page_raw_blocks]
        page_block = self.raw_builder.build_page_block(page, all_child_ids_on_page)
        setattr(page, "raw_object", page_block)
        page_raw_blocks.insert(0, page_block)

        page.layouts = layout_blocks

        all_lines = [line for layout in layout_blocks for line in layout.children]
        all_words = [word for line in all_lines for word in line.children]
        page.lines = all_lines
        page.words = all_words

        for word in all_words:
            word.page = page_number
        for line in all_lines:
            line.page = page_number

        return page, reading_order_counter, page_raw_blocks


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
        self.raw_builder = RawObjectBuilder()
        self.word_builder = WordBuilder(self.bbox_calc, self.config, self.raw_builder)
        self.line_builder = LineBuilder(self.word_builder, self.bbox_calc, self.raw_builder)
        self.layout_builder = LayoutBuilder(self.line_builder, self.bbox_calc, self.config, self.raw_builder)
        self.page_builder = PageBuilder(self.layout_builder, self.config, self.raw_builder)

    def create_document(self, page_definitions: List[List[Dict]]) -> Document:
        """
        Create a Document from simplified page definitions.
        ...
        """
        if not page_definitions:
            document = Document()
            # Use setattr to dynamically add the attribute for the type checker
            setattr(document, "raw_response", {"Blocks": [], "DocumentMetadata": {"Pages": 0}})
            return document

        pages = []
        all_raw_blocks = []
        reading_order_counter = 0

        for page_number, page_def in enumerate(page_definitions, 1):
            page, reading_order_counter, page_blocks = self.page_builder.build_page(
                page_def, page_number, reading_order_counter
            )
            pages.append(page)
            all_raw_blocks.extend(page_blocks)

        document = Document(num_pages=len(pages))
        document.pages = pages

        # Construct the final raw_response dictionary
        raw_response = {
            "DocumentMetadata": {"Pages": len(pages)},
            "Blocks": all_raw_blocks,
            "AnalyzeDocumentModelVersion": "1.0",
        }

        # Use setattr to dynamically add the attribute for the type checker
        setattr(document, "response", raw_response)

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
