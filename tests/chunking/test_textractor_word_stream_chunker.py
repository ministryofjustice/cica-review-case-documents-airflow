"""Tests for Textractor word-stream chunking strategy."""

from datetime import datetime
from typing import cast
from unittest.mock import MagicMock

import pytest
from textractor.entities.bbox import BoundingBox
from textractor.entities.word import Word

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.strategies.word_stream.chunker import TextractorWordStreamChunker
from ingestion_pipeline.chunking.strategies.word_stream.config import WordStreamChunkingConfig
from ingestion_pipeline.chunking.strategies.word_stream.handler import TextractorWordStreamDocumentChunker


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        source_doc_id="test_doc_1",
        source_file_name="test.pdf",
        source_file_s3_uri="s3://test-bucket/test.pdf",
        page_count=1,
        case_ref="TEST123",
        received_date=datetime(2024, 1, 1),
        correspondence_type="letter",
    )


def create_mock_word(text: str, top: float, left: float = 0.1, width: float = 0.05, height: float = 0.02) -> Word:
    word = cast(Word, MagicMock())
    word.text = text
    word.bbox = BoundingBox(x=left, y=top, width=width, height=height)
    return word


def test_sentence_boundary_split(sample_metadata):
    config = WordStreamChunkingConfig(min_words=2, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("This", 0.1),
        create_mock_word("works.", 0.1),
        create_mock_word("Next", 0.11),
        create_mock_word("one.", 0.11),
    ]

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata)

    assert len(chunks) == 2
    assert chunks[0].chunk_text == "This works."
    assert chunks[1].chunk_text == "Next one."


def test_combines_word_bounding_boxes(sample_metadata):
    config = WordStreamChunkingConfig(min_words=50, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("alpha", top=0.10, left=0.10, width=0.20, height=0.03),
        create_mock_word("beta", top=0.14, left=0.35, width=0.10, height=0.02),
    ]

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata)

    assert len(chunks) == 1
    bbox = chunks[0].bounding_box
    assert bbox.left == pytest.approx(0.10)
    assert bbox.top == pytest.approx(0.10)
    assert bbox.right == pytest.approx(0.45)
    assert bbox.bottom == pytest.approx(0.16)


def test_handler_uses_page_get_text_and_words(sample_metadata):
    config = WordStreamChunkingConfig(min_words=1, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    handler = TextractorWordStreamDocumentChunker(config=config)

    page = MagicMock()
    page.page_num = 1
    page.get_text_and_words.return_value = (
        "Hello world.",
        [create_mock_word("Hello", 0.1), create_mock_word("world.", 0.1)],
    )

    doc = MagicMock()
    doc.pages = [page]
    doc.response = {"Blocks": [{"BlockType": "WORD"}]}

    processed = handler.chunk(doc, sample_metadata)

    assert len(processed.chunks) == 1
    assert processed.chunks[0].chunk_text == "Hello world."
    assert processed.chunks[0].chunk_type == "TEXTRACT_WORD_STREAM_CHUNK"


def test_forward_lookahead_preserves_sentence_within_hard_max(sample_metadata):
    config = WordStreamChunkingConfig(
        min_words=3,
        max_words=6,
        max_vertical_gap_ratio=0.05,
        forward_lookahead_words=3,
        backward_scan_words=6,
        normalize_spacing=True,
    )
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("Alpha", 0.10),
        create_mock_word("beta", 0.10),
        create_mock_word("gamma", 0.10),
        create_mock_word("delta", 0.10),
        create_mock_word("end.", 0.10),
        create_mock_word("Next", 0.12),
        create_mock_word("chunk.", 0.12),
    ]

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata)

    assert len(chunks) == 2
    assert chunks[0].chunk_text == "Alpha beta gamma delta end."
    assert chunks[1].chunk_text == "Next chunk."


def test_hard_max_prefers_backward_sentence_split(sample_metadata):
    config = WordStreamChunkingConfig(
        min_words=2,
        max_words=4,
        max_vertical_gap_ratio=0.05,
        forward_lookahead_words=1,
        backward_scan_words=6,
        normalize_spacing=True,
    )
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("Intro", 0.10),
        create_mock_word("done.", 0.10),
        create_mock_word("Next", 0.10),
        create_mock_word("part", 0.10),
        create_mock_word("goes", 0.12),
        create_mock_word("on.", 0.12),
    ]

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata)

    assert len(chunks) == 2
    assert chunks[0].chunk_text == "Intro done."
    assert chunks[1].chunk_text == "Next part goes on."
