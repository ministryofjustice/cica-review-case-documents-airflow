import pytest

from ingestion_pipeline.chunking.chunker_factory import get_document_chunker
from ingestion_pipeline.chunking.line_based_document_chunker import LineBasedDocumentChunker
from ingestion_pipeline.chunking.textract_document_chunker import TextractLayoutDocumentChunker


def test_factory_returns_line_chunker():
    chunker = get_document_chunker("line")
    assert isinstance(chunker, LineBasedDocumentChunker)

def test_factory_returns_layout_chunker():
    chunker = get_document_chunker("layout")
    assert isinstance(chunker, TextractLayoutDocumentChunker)

def test_factory_explicit_type_line_normalization():
    chunker = get_document_chunker("line")
    assert isinstance(chunker, LineBasedDocumentChunker)
    # Test normalization
    chunker2 = get_document_chunker("  LINE  ")
    assert isinstance(chunker2, LineBasedDocumentChunker)

def test_factory_explicit_type_layout_normalization():
    chunker = get_document_chunker("layout")
    assert isinstance(chunker, TextractLayoutDocumentChunker)
    # Test normalization
    chunker2 = get_document_chunker("  LaYoUt  ")
    assert isinstance(chunker2, TextractLayoutDocumentChunker)

def test_factory_invalid_type():
    with pytest.raises(ValueError) as excinfo:
        get_document_chunker("invalid_type")
    assert "Unknown chunker_type" in str(excinfo.value)
    assert "layout" in str(excinfo.value) and "line" in str(excinfo.value)
