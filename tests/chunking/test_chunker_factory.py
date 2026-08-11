import pytest

from ingestion_pipeline.chunking.chunk_strategy_factory import get_chunk_strategy
from ingestion_pipeline.chunking.strategies.layout.layout_chunk_handler import TextractLayoutDocumentChunker
from ingestion_pipeline.chunking.strategies.line_sentence.line_sentence_handler import LineBasedDocumentChunker
from ingestion_pipeline.chunking.strategies.word_stream.handler import TextractorWordStreamDocumentChunker


def test_factory_returns_line_chunker():
    chunker = get_chunk_strategy("linear-sentence-splitter")
    assert isinstance(chunker, LineBasedDocumentChunker)


def test_factory_returns_layout_chunker():
    chunker = get_chunk_strategy("layout")
    assert isinstance(chunker, TextractLayoutDocumentChunker)


def test_factory_returns_textractor_word_stream_chunker():
    chunker = get_chunk_strategy("textractor-word-stream")
    assert isinstance(chunker, TextractorWordStreamDocumentChunker)


def test_factory_logs_textractor_word_stream_chunker_config(caplog):
    with caplog.at_level("INFO"):
        get_chunk_strategy("textractor-word-stream")

    assert "ChunkStrategy settings for textractor-word-stream" in caplog.text
    assert "\nWORDSTREAM_CHUNKER_MIN_WORDS=80" not in caplog.text
    assert "WORDSTREAM_CHUNKER_MIN_WORDS=" in caplog.text
    assert "WORDSTREAM_CHUNKER_MAX_WORDS=" in caplog.text
    assert "WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO=" in caplog.text
    assert "WORDSTREAM_CHUNKER_FORWARD_LOOKAHEAD_WORDS=" in caplog.text
    assert "WORDSTREAM_CHUNKER_BACKWARD_SCAN_WORDS=" in caplog.text


def test_factory_logs_layout_chunker_config(caplog):
    with caplog.at_level("INFO"):
        get_chunk_strategy("layout")

    assert "ChunkStrategy settings for layout" in caplog.text
    assert "\nLAYOUT_CHUNKER_MIN_WORDS=80" not in caplog.text
    assert "LAYOUT_CHUNKING_MAXIMUM_CHUNK_SIZE=" in caplog.text
    assert "LAYOUT_CHUNKING_Y_TOLERANCE_RATIO=" in caplog.text
    assert "LAYOUT_CHUNKING_MAX_VERTICAL_GAP=" in caplog.text
    assert "LAYOUT_CHUNKING_LINE_CHUNK_CHAR_LIMIT=" in caplog.text


def test_factory_logs_linear_sentence_splitter_chunker_config(caplog):
    with caplog.at_level("INFO"):
        get_chunk_strategy("linear-sentence-splitter")

    assert "ChunkStrategy settings for linear-sentence-splitter" in caplog.text
    assert "SENTENCE_CHUNKER_MIN_WORDS=80" in caplog.text
    assert "SENTENCE_CHUNKER_MAX_WORDS=120" in caplog.text
    assert "SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO=0.05" in caplog.text


def test_factory_explicit_type_line_normalization():
    chunker = get_chunk_strategy("linear-sentence-splitter")
    assert isinstance(chunker, LineBasedDocumentChunker)
    # Test normalization
    chunker2 = get_chunk_strategy("  LINEAR-sentence-splitter  ")
    assert isinstance(chunker2, LineBasedDocumentChunker)


def test_factory_explicit_type_layout_normalization():
    chunker = get_chunk_strategy("layout")
    assert isinstance(chunker, TextractLayoutDocumentChunker)
    # Test normalization
    chunker2 = get_chunk_strategy("  LaYoUt  ")
    assert isinstance(chunker2, TextractLayoutDocumentChunker)


def test_factory_invalid_type():
    with pytest.raises(ValueError) as excinfo:
        get_chunk_strategy("invalid_type")
    assert "Unknown chunker_type" in str(excinfo.value)
    assert "layout" in str(excinfo.value) and "linear-sentence-splitter" in str(excinfo.value)
