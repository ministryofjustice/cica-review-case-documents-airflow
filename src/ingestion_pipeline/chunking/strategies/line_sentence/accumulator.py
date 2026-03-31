"""Chunk accumulation state for line-sentence chunking."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from textractor.entities.bbox import BoundingBox

LineEntry = Tuple[str, BoundingBox]


@dataclass
class ChunkAccumulator:
    """Mutable state used while building a chunk across lines."""

    lines: List[LineEntry] = field(default_factory=list)
    word_count: int = 0
    prev_line_bottom: Optional[float] = None

    def add_line(self, text: str, bbox: BoundingBox, word_count: int) -> None:
        """Append a line and update counters."""
        self.lines.append((text, bbox))
        self.word_count += word_count
        self.prev_line_bottom = bbox.y + bbox.height

    def start_with_line(self, text: str, bbox: BoundingBox, word_count: int) -> None:
        """Reset and start a new chunk with the provided line."""
        self.lines = [(text, bbox)]
        self.word_count = word_count
        self.prev_line_bottom = bbox.y + bbox.height

    def reset(self) -> None:
        """Clear all accumulated state."""
        self.lines = []
        self.word_count = 0
        self.prev_line_bottom = None

    def split_at(self, index: int) -> Tuple[List[LineEntry], List[LineEntry]]:
        """Split current lines at index and return (emit_lines, remaining_lines)."""
        return self.lines[:index], self.lines[index:]

    def replace_lines(self, lines: List[LineEntry]) -> None:
        """Replace current lines and recompute word count.

        Intentionally leaves prev_line_bottom unchanged to preserve existing behavior
        in edge cases where a backward split emits all lines.
        """
        self.lines = lines
        self.word_count = sum(len(text.split()) for text, _ in lines)
