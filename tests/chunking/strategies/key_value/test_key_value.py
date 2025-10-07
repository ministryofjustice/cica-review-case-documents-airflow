from unittest.mock import MagicMock, call

import pytest
from textractor.entities.bbox import BoundingBox
from textractor.entities.document_entity import DocumentEntity
from textractor.entities.key_value import KeyValue, Value
from textractor.entities.layout import Layout
from textractor.entities.line import Line
from textractor.entities.word import Word

from src.chunking.chunking_config import ChunkingConfig
from src.chunking.schemas import DocumentChunk, DocumentMetadata
from src.chunking.strategies.key_value.layout_key_value import KeyValueChunker


@pytest.fixture
def mock_kv_pair_factory():
    """
    Factory fixture to create mock KeyValue objects.
    This has been corrected to reflect that '.key' is a list of Words.
    """

    def _create_mock_kv(key_text: str, value_text: str, kv_id: str) -> MagicMock:
        mock_key_words = [MagicMock(spec=Word, text=word) for word in key_text.split()]

        mock_value = MagicMock(spec=Value)
        mock_value.text = value_text

        mock_kv = MagicMock(spec=KeyValue)
        mock_kv.key = mock_key_words
        mock_kv.value = mock_value
        mock_kv.id = kv_id
        mock_kv.bbox = MagicMock(spec=BoundingBox)

        return mock_kv

    return _create_mock_kv


@pytest.fixture
def mock_line_factory():
    """Factory fixture to create mock Line objects."""

    def _create_mock_line(text: str, line_id: str) -> MagicMock:
        mock_line = MagicMock(spec=Line)
        mock_line.text = text
        mock_line.id = line_id
        mock_line.bbox = MagicMock(spec=BoundingBox)
        return mock_line

    return _create_mock_line


@pytest.fixture
def default_config():
    """Provides a default chunking configuration."""
    return ChunkingConfig(maximum_chunk_size=500)


@pytest.fixture
def chunk_args():
    """Provides default arguments for the chunk method."""
    return {
        "page_number": 1,
        "metadata": MagicMock(spec=DocumentMetadata),
        "chunk_index_start": 0,
        "raw_response": None,
    }


def test_chunks_mixed_key_value_and_line_children(
    mocker, default_config, chunk_args, mock_kv_pair_factory, mock_line_factory
):
    """
    Verifies that the chunker correctly processes a layout block
    containing both KeyValue pairs and standalone Line objects.
    """

    mock_os_doc_from_layout = mocker.patch.object(DocumentChunk, "from_textractor_layout")

    kv_child = mock_kv_pair_factory("Name:", "John Doe", "kv-1")
    line_child = mock_line_factory("This is a standalone line.", "line-1")

    layout_block = MagicMock(spec=Layout, id="layout-1", layout_type="LAYOUT_KEY_VALUE")
    layout_block.children = [kv_child, line_child]

    strategy = KeyValueChunker(config=default_config)

    strategy.chunk(layout_block=layout_block, **chunk_args)

    assert mock_os_doc_from_layout.call_count == 2

    expected_kv_call = call(
        block=layout_block,
        page_number=1,
        metadata=chunk_args["metadata"],
        chunk_index=0,
        chunk_text="Name: John Doe",
        combined_bbox=kv_child.bbox,
    )

    expected_line_call = call(
        block=layout_block,
        page_number=1,
        metadata=chunk_args["metadata"],
        chunk_index=1,
        chunk_text="This is a standalone line.",
        combined_bbox=line_child.bbox,
    )

    mock_os_doc_from_layout.assert_has_calls([expected_kv_call, expected_line_call], any_order=False)


def test_returns_empty_list_for_empty_layout_block(default_config, chunk_args):
    """
    Verifies that an empty list is returned when the layout block has no children.
    """

    layout_block = MagicMock(spec=Layout, children=[], id="empty-block")
    strategy = KeyValueChunker(config=default_config)

    result = strategy.chunk(layout_block=layout_block, **chunk_args)

    assert result == []


def test_skips_key_value_pair_if_missing_key_or_value(mocker, default_config, chunk_args, mock_kv_pair_factory):
    """
    Verifies that KeyValue pairs with a missing key or value are skipped.
    """

    mock_os_doc_from_layout = mocker.patch.object(DocumentChunk, "from_textractor_layout")

    kv_missing_value = mock_kv_pair_factory("Address:", "123 Main St", "kv-1")
    kv_missing_value.value = None

    kv_missing_key = mock_kv_pair_factory("City:", "Anytown", "kv-2")
    kv_missing_key.key = None

    layout_block = MagicMock(spec=Layout, id="layout-2")
    layout_block.children = [kv_missing_value, kv_missing_key]

    strategy = KeyValueChunker(config=default_config)

    strategy.chunk(layout_block=layout_block, **chunk_args)

    mock_os_doc_from_layout.assert_not_called()


def test_skips_empty_or_whitespace_only_lines(mocker, default_config, chunk_args, mock_line_factory):
    """
    Verifies that lines containing no text or only whitespace are skipped.
    """

    mock_os_doc_from_layout = mocker.patch.object(DocumentChunk, "from_textractor_layout")

    empty_line = mock_line_factory("", "line-empty")
    whitespace_line = mock_line_factory("   \t\n ", "line-whitespace")
    valid_line = mock_line_factory("Valid text", "line-valid")

    layout_block = MagicMock(spec=Layout, id="layout-3")
    layout_block.children = [empty_line, whitespace_line, valid_line]
    layout_block.layout_type = "LAYOUT_KEY_VALUE"

    strategy = KeyValueChunker(config=default_config)

    strategy.chunk(layout_block=layout_block, **chunk_args)

    mock_os_doc_from_layout.assert_called_once()

    mock_os_doc_from_layout.assert_called_with(
        block=layout_block,
        page_number=1,
        metadata=chunk_args["metadata"],
        chunk_index=0,
        chunk_text="Valid text",
        combined_bbox=valid_line.bbox,
    )


def test_skips_unsupported_child_types_and_logs_warning(mocker, default_config, chunk_args, mock_line_factory):
    """
    Verifies that unexpected child types within a LAYOUT_KEY_VALUE block
    are skipped and a warning is logged.
    """

    mock_logger_warning = mocker.patch("src.chunking.strategies.key_value.layout_key_value.logger.warning")
    mock_os_doc_from_layout = mocker.patch.object(DocumentChunk, "from_textractor_layout")

    unsupported_child = MagicMock(spec=DocumentEntity)
    unsupported_child.__class__.__name__ = "UnsupportedType"
    valid_line = mock_line_factory("This should be processed", "line-1")

    layout_block = MagicMock(spec=Layout, id="layout-mixed-support")
    layout_block.children = [unsupported_child, valid_line]
    layout_block.layout_type = "LAYOUT_KEY_VALUE"

    strategy = KeyValueChunker(config=default_config)

    strategy.chunk(layout_block=layout_block, **chunk_args)

    mock_logger_warning.assert_called_once()
    log_message = mock_logger_warning.call_args[0][0]
    assert "Skipping unexpected child block of type " in log_message
    assert layout_block.id in log_message

    mock_os_doc_from_layout.assert_called_once()
    mock_os_doc_from_layout.assert_called_with(
        block=layout_block,
        page_number=1,
        metadata=chunk_args["metadata"],
        chunk_index=0,
        chunk_text="This should be processed",
        combined_bbox=valid_line.bbox,
    )
