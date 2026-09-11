from ingestion_pipeline.errors import (
    DlqCategory,
    EmptyTextractResponseError,
    PipelineError,
    ZeroChunksError,
)

"""Tests for the central pipeline error hierarchy."""


def test_pipeline_error_defaults():
    err = PipelineError("something went wrong")
    assert err.category is DlqCategory.UNEXPECTED
    assert err.retryable is True
    assert err.source_doc_id is None
    assert err.case_ref is None
    assert err.s3_uri is None


def test_terminal_subclasses_are_not_retryable():
    assert EmptyTextractResponseError("x").retryable is False
    assert EmptyTextractResponseError("x").category is DlqCategory.EMPTY_TEXTRACT_RESPONSE
    assert ZeroChunksError("x").retryable is False
    assert ZeroChunksError("x").category is DlqCategory.ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT


def test_failure_context_has_stable_shape_and_values():
    err = ZeroChunksError(
        "no chunks extracted",
        source_doc_id="doc-1",
        case_ref="26-711111",
        s3_uri="s3://bucket/26-711111/file.pdf",
    )

    context = err.failure_context()

    assert context == {
        "category": "zero_chunks_extracted_from_document",
        "retryable": False,
        "error_type": "ZeroChunksError",
        "message": "no chunks extracted",
        "source_doc_id": "doc-1",
        "case_ref": "26-711111",
        "s3_uri": "s3://bucket/26-711111/file.pdf",
    }


def test_failure_context_keys_present_when_context_missing():
    """Keys are always present (None) so downstream records have a stable shape."""
    context = PipelineError("bare").failure_context()

    assert context["source_doc_id"] is None
    assert context["case_ref"] is None
    assert context["s3_uri"] is None
    assert set(context) == {
        "category",
        "retryable",
        "error_type",
        "message",
        "source_doc_id",
        "case_ref",
        "s3_uri",
    }
