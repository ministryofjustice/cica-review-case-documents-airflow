from dataclasses import dataclass
from typing import List, cast

import pytest
from textractor.entities.bbox import BoundingBox

from src.document_chunker.utils.bbox_utils import combine_bounding_boxes


@dataclass
class MockBoundingBox:
    width: float
    height: float
    x: float
    y: float


def test_combine_bounding_boxes_multiple_boxes():
    """Test combining multiple bounding boxes."""
    # Arrange: Create mock bounding boxes
    bbox1 = MockBoundingBox(width=10, height=20, x=100, y=50)
    bbox2 = MockBoundingBox(width=5, height=5, x=115, y=60)
    bbox3 = MockBoundingBox(width=30, height=40, x=80, y=80)
    bbox4 = MockBoundingBox(width=10, height=10, x=150, y=40)

    bboxes = [bbox1, bbox2, bbox3, bbox4]

    combined_bbox = combine_bounding_boxes(cast(List[BoundingBox], bboxes))

    # Assert: Verify the combined bounding box coordinates and dimensions
    assert combined_bbox.x == 80.0, "The minimum x should be 80."
    assert combined_bbox.y == 40.0, "The minimum y should be 40."

    # Calculate expected max right and max bottom
    max_right = max(bbox.x + bbox.width for bbox in bboxes)
    max_bottom = max(bbox.y + bbox.height for bbox in bboxes)

    assert combined_bbox.x + combined_bbox.width == max_right, "The combined right edge is incorrect."
    assert combined_bbox.y + combined_bbox.height == max_bottom, "The combined bottom edge is incorrect."

    assert combined_bbox.width == (150 + 10) - 80, "Combined width is incorrect."
    assert combined_bbox.height == (80 + 40) - 40, "Combined height is incorrect."


def test_combine_bounding_boxes_single_box():
    """Test combining a single bounding box."""

    single_bbox = MockBoundingBox(width=50, height=75, x=20, y=10)
    bboxes = [single_bbox]
    combined_bbox = combine_bounding_boxes(cast(List[BoundingBox], bboxes))
    expected_bbox = BoundingBox(width=50, height=75, x=20, y=10)

    assert expected_bbox == combined_bbox, "Single box should return the same box."


def test_combine_bounding_boxes_empty_list():
    """Test that an empty list raises a ValueError."""

    bboxes = []

    with pytest.raises(ValueError, match="Cannot combine an empty list of bounding boxes."):
        combine_bounding_boxes(bboxes)
