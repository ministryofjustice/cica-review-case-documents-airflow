"""Utility functions for bounding box operations."""

from typing import Sequence

from textractor.entities.bbox import BoundingBox


def combine_bounding_boxes(bboxes: Sequence[BoundingBox]) -> BoundingBox:
    """Combines a list of BoundingBox objects into a single encompassing BoundingBox.

    Args:
        bboxes (Sequence[BoundingBox]): A sequence of BoundingBox objects to combine.

    Raises:
        ValueError: If the input list is empty.

    Returns:
        BoundingBox: The combined BoundingBox.
    """
    if not bboxes:
        raise ValueError("Cannot combine an empty list of bounding boxes.")

    min_left = min(bbox.x for bbox in bboxes)
    min_top = min(bbox.y for bbox in bboxes)
    max_right = max(bbox.x + bbox.width for bbox in bboxes)
    max_bottom = max(bbox.y + bbox.height for bbox in bboxes)

    new_width = max_right - min_left
    new_height = max_bottom - min_top

    return BoundingBox(
        width=new_width,
        height=new_height,
        x=min_left,
        y=min_top,
    )
