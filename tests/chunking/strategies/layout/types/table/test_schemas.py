from textractor.entities.bbox import BoundingBox

from ingestion_pipeline.chunking.strategies.layout.types.table.schemas import TextBlock


class TestTextBlock:
    def make_bbox(self, x=1.0, y=2.0, width=3.0, height=4.0):
        return BoundingBox(x=x, y=y, width=width, height=height)

    def test_properties_basic(self):
        bbox = self.make_bbox(x=10, y=20, width=30, height=40)
        tb = TextBlock(text="foo", bbox=bbox, confidence=0.9)
        assert tb.top == 20
        assert tb.left == 10
        assert tb.width == 30
        assert tb.height == 40
        assert tb.bottom == 60  # 20 + 40
        assert tb.right == 40  # 10 + 30
        assert tb.center_y == 40  # 20 + 40/2
        assert tb.confidence == 0.9
        assert tb.text == "foo"

    def test_properties_with_negative_values(self):
        bbox = self.make_bbox(x=-5, y=-10, width=-15, height=-20)
        tb = TextBlock(text="bar", bbox=bbox)
        assert tb.top == -10
        assert tb.left == -5
        assert tb.width == -15
        assert tb.height == -20
        assert tb.bottom == -30  # -10 + -20
        assert tb.right == -20  # -5 + -15
        assert tb.center_y == -20  # -10 + (-20/2)

    def test_default_confidence(self):
        bbox = self.make_bbox()
        tb = TextBlock(text="baz", bbox=bbox)
        assert tb.confidence == 0.0
