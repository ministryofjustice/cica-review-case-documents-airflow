"""Schemas for representing text blocks with geometry information."""

from dataclasses import dataclass

from textractor.entities.bbox import BoundingBox


@dataclass
class TextBlock:
    """Represents a text block from Textract with its geometry.

    Returns:
        TextBlock: The text block with bounding box and confidence score.
    """

    text: str
    bbox: BoundingBox
    confidence: float = 0.0

    @property
    def top(self) -> float:
        """The top position of the text block.

        Returns:
            float: The top position of the bounding box.
        """
        return self.bbox.y

    @property
    def left(self) -> float:
        """The left position of the text block.

        Returns:
            float: The left position of the bounding box.
        """
        return self.bbox.x

    @property
    def width(self) -> float:
        """The width of the text block.

        Returns:
            float: The width of the bounding box.
        """
        return self.bbox.width

    @property
    def height(self) -> float:
        """The height of the text block.

        Returns:
            float: The height of the bounding box.
        """
        return self.bbox.height

    @property
    def bottom(self) -> float:
        """The bottom position of the text block.

        Returns:
            float: The bottom position of the bounding box.
        """
        return self.top + self.height

    @property
    def right(self) -> float:
        """The right position of the text block.

        Returns:
            float: The right position of the bounding box.
        """
        return self.left + self.width

    @property
    def center_y(self) -> float:
        """The vertical center position of the text block.

        Returns:
            float: The vertical center position of the bounding box.
        """
        return self.top + (self.height / 2)
