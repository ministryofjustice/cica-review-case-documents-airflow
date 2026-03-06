import pytest

from ingestion_pipeline.chunking.chunk_strategy_factory import get_chunk_strategy
from ingestion_pipeline.chunking.strategies.layout.layout_chunk_handler import TextractLayoutDocumentChunker
from ingestion_pipeline.chunking.strategies.line_sentence.line_sentence_handler import LineBasedDocumentChunker


def test_factory_returns_line_chunker():
    chunker = get_chunk_strategy("linear-sentence-splitter")
    assert isinstance(chunker, LineBasedDocumentChunker)


def test_factory_returns_layout_chunker():
    chunker = get_chunk_strategy("layout")
    assert isinstance(chunker, TextractLayoutDocumentChunker)


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
