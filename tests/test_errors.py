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


def _document_metadata():
    """A minimal, valid DocumentMetadata for context-mapping tests."""
    import datetime

    from ingestion_pipeline.chunking.schemas import DocumentMetadata

    return DocumentMetadata(
        source_doc_id="doc-123",
        source_file_name="file.pdf",
        source_file_s3_uri="s3://bucket/26-711111/file.pdf",
        page_count=1,
        case_ref="26-711111",
        received_date=datetime.datetime(2024, 1, 1),
        correspondence_type="Email",
    )


def test_from_metadata_maps_document_context():
    """from_metadata copies context from the metadata onto the concrete subclass."""
    err = ZeroChunksError.from_metadata("no chunks", _document_metadata())

    assert isinstance(err, ZeroChunksError)
    assert err.source_doc_id == "doc-123"
    assert err.case_ref == "26-711111"
    assert err.s3_uri == "s3://bucket/26-711111/file.pdf"
    assert str(err) == "no chunks"


def test_enrich_from_metadata_backfills_only_missing_fields():
    """A bare error gets all three context fields filled from metadata."""
    err = PipelineError("bare")

    err.enrich_from_metadata(_document_metadata())

    assert err.source_doc_id == "doc-123"
    assert err.case_ref == "26-711111"
    assert err.s3_uri == "s3://bucket/26-711111/file.pdf"


def test_enrich_from_metadata_preserves_existing_context():
    """Context already set on the error is not overwritten by metadata."""
    err = PipelineError(
        "preset",
        source_doc_id="other-doc",
        case_ref="99-999999",
        s3_uri="s3://other/file.pdf",
    )

    err.enrich_from_metadata(_document_metadata())

    assert err.source_doc_id == "other-doc"
    assert err.case_ref == "99-999999"
    assert err.s3_uri == "s3://other/file.pdf"


def test_enrich_from_metadata_fills_partial_context():
    """Only the None fields are backfilled; already-set fields are left alone."""
    err = PipelineError("partial", source_doc_id="kept-doc")

    err.enrich_from_metadata(_document_metadata())

    assert err.source_doc_id == "kept-doc"
    assert err.case_ref == "26-711111"
    assert err.s3_uri == "s3://bucket/26-711111/file.pdf"
