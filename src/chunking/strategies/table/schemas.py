# src/chunking/strategies/table/types.py (REVISED)

from dataclasses import dataclass

from textractor.entities.bbox import BoundingBox


@dataclass
class TextBlock:
    """Represents a text block from Textract with its geometry"""

    text: str
    bbox: BoundingBox  # <-- The single source of truth for geometry
    confidence: float = 0.0

    @property
    def top(self) -> float:
        return self.bbox.y

    @property
    def left(self) -> float:
        return self.bbox.x

    @property
    def width(self) -> float:
        return self.bbox.width

    @property
    def height(self) -> float:
        return self.bbox.height

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def center_y(self) -> float:
        return self.top + (self.height / 2)
