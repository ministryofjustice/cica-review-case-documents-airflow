"""Line preprocessing helpers for sentence-aware chunking."""

import re
from typing import List

from textractor.entities.line import Line

FOOTER_THRESHOLD = 0.95
PAGE_NUMBER_PATTERN = re.compile(r"^Page\s*\d+", re.IGNORECASE)


def filter_and_sort_lines(lines: List[Line]) -> List[Line]:
    """Filter footer-like lines and sort by vertical position."""
    filtered = [
        line
        for line in lines
        if line.bbox
        and line.bbox.y < FOOTER_THRESHOLD
        and not (line.text and PAGE_NUMBER_PATTERN.match(line.text.strip()))
    ]
    return sorted(filtered, key=lambda line: line.bbox.y if line.bbox else 0)
