"""Tests for Textractor word-stream chunking strategy."""

from datetime import datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from textractor.entities.bbox import BoundingBox
from textractor.entities.word import Word

from ingestion_pipeline.chunking.chunk_strategy import ChunkError
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


def test_handler_raises_on_page_and_chunk_text_mismatch(sample_metadata):
    config = WordStreamChunkingConfig(min_words=1, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    handler = TextractorWordStreamDocumentChunker(config=config)

    page = MagicMock()
    page.page_num = 1
    page.get_text_and_words.return_value = (
        "Different text from get_text_and_words",
        [create_mock_word("Hello", 0.1), create_mock_word("world.", 0.1)],
    )

    doc = MagicMock()
    doc.pages = [page]
    doc.response = {"Blocks": [{"BlockType": "WORD"}]}

    with pytest.raises(ChunkError) as exc_info:
        handler.chunk(doc, sample_metadata)

    assert "Word-stream text mismatch on page=1" in str(exc_info.value.__cause__)


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


def test_lookahead_does_not_cross_vertical_gap(sample_metadata):
    config = WordStreamChunkingConfig(
        min_words=3,
        max_words=10,
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
        create_mock_word("end.", 0.30),
        create_mock_word("Next", 0.30),
        create_mock_word("chunk.", 0.30),
    ]

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata)

    assert len(chunks) == 2
    assert chunks[0].chunk_text == "Alpha beta gamma"
    assert chunks[1].chunk_text == "end. Next chunk."


def test_lookahead_gap_break_does_not_skip_or_duplicate_words(sample_metadata):
    config = WordStreamChunkingConfig(
        min_words=3,
        max_words=10,
        max_vertical_gap_ratio=0.05,
        forward_lookahead_words=3,
        backward_scan_words=6,
        normalize_spacing=True,
    )
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("w1", 0.10),
        create_mock_word("w2", 0.10),
        create_mock_word("w3", 0.10),
        create_mock_word("w4.", 0.30),
        create_mock_word("w5", 0.30),
        create_mock_word("w6.", 0.30),
    ]

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata)
    chunk_tokens = [token for chunk in chunks for token in chunk.chunk_text.split()]

    assert chunk_tokens == ["w1", "w2", "w3", "w4.", "w5", "w6."]


def test_wordstream_config_from_settings_uses_wordstream_prefixed_fields():
    settings_obj = SimpleNamespace(
        SENTENCE_CHUNKER_MIN_WORDS=1,
        SENTENCE_CHUNKER_MAX_WORDS=2,
        SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO=0.99,
        WORDSTREAM_CHUNKER_MIN_WORDS=80,
        WORDSTREAM_CHUNKER_MAX_WORDS=120,
        WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO=0.05,
        WORDSTREAM_CHUNKER_FORWARD_LOOKAHEAD_WORDS=8,
        WORDSTREAM_CHUNKER_BACKWARD_SCAN_WORDS=20,
    )

    config = WordStreamChunkingConfig.from_settings(settings_obj)

    assert config.min_words == 80
    assert config.max_words == 120
    assert config.max_vertical_gap_ratio == 0.05
    assert config.forward_lookahead_words == 8
    assert config.backward_scan_words == 20


def test_all_printed_words_page_contains_handwriting_false(sample_metadata):
    """When all words are PRINTED, page_contains_handwriting should be False."""
    from textractor.data.constants import TextTypes

    config = WordStreamChunkingConfig(min_words=2, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("Hello", 0.1),
        create_mock_word("world.", 0.1),
    ]
    for w in words:
        w.text_type = TextTypes.PRINTED

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata, page_contains_handwriting=False)

    assert len(chunks) == 1
    assert chunks[0].page_contains_handwriting is False


def test_handwriting_word_page_contains_handwriting_true(sample_metadata):
    """When at least one word is HANDWRITING, page_contains_handwriting should be True."""
    from textractor.data.constants import TextTypes

    config = WordStreamChunkingConfig(min_words=2, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("Hello", 0.1),
        create_mock_word("world.", 0.1),
    ]
    words[0].text_type = TextTypes.PRINTED
    words[1].text_type = TextTypes.HANDWRITING

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata, page_contains_handwriting=True)

    assert len(chunks) == 1
    assert chunks[0].page_contains_handwriting is True


def test_mixed_words_all_chunks_flagged(sample_metadata):
    """When a page has mixed text types, all chunks from that page should be flagged."""
    from textractor.data.constants import TextTypes

    config = WordStreamChunkingConfig(min_words=2, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    chunker = TextractorWordStreamChunker(config=config)

    words = [
        create_mock_word("First", 0.1),
        create_mock_word("sentence.", 0.1),
        create_mock_word("Second", 0.12),
        create_mock_word("sentence.", 0.12),
    ]
    # Only one word is handwritten
    words[0].text_type = TextTypes.PRINTED
    words[1].text_type = TextTypes.PRINTED
    words[2].text_type = TextTypes.HANDWRITING
    words[3].text_type = TextTypes.PRINTED

    chunks = chunker.chunk_page(words=words, page_number=1, metadata=sample_metadata, page_contains_handwriting=True)

    assert len(chunks) == 2
    assert all(chunk.page_contains_handwriting is True for chunk in chunks)


def test_handler_detects_handwriting_from_words(sample_metadata):
    """Handler should detect handwriting at page level and propagate to chunks."""
    from textractor.data.constants import TextTypes

    config = WordStreamChunkingConfig(min_words=1, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    handler = TextractorWordStreamDocumentChunker(config=config)

    word1 = create_mock_word("Hello", 0.1)
    word1.text_type = TextTypes.PRINTED
    word2 = create_mock_word("world.", 0.1)
    word2.text_type = TextTypes.HANDWRITING

    page = MagicMock()
    page.page_num = 1
    page.get_text_and_words.return_value = ("Hello world.", [word1, word2])

    doc = MagicMock()
    doc.pages = [page]
    doc.response = {"Blocks": [{"BlockType": "WORD"}]}

    processed = handler.chunk(doc, sample_metadata)

    assert len(processed.chunks) == 1
    assert processed.chunks[0].page_contains_handwriting is True


def test_handler_no_handwriting_words(sample_metadata):
    """Handler should set page_contains_handwriting=False when all words are printed."""
    from textractor.data.constants import TextTypes

    config = WordStreamChunkingConfig(min_words=1, max_words=100, max_vertical_gap_ratio=0.05, normalize_spacing=True)
    handler = TextractorWordStreamDocumentChunker(config=config)

    word1 = create_mock_word("Hello", 0.1)
    word1.text_type = TextTypes.PRINTED
    word2 = create_mock_word("world.", 0.1)
    word2.text_type = TextTypes.PRINTED

    page = MagicMock()
    page.page_num = 1
    page.get_text_and_words.return_value = ("Hello world.", [word1, word2])

    doc = MagicMock()
    doc.pages = [page]
    doc.response = {"Blocks": [{"BlockType": "WORD"}]}

    processed = handler.chunk(doc, sample_metadata)

    assert len(processed.chunks) == 1
    assert processed.chunks[0].page_contains_handwriting is False
