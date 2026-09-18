from ingestion_pipeline.errors import DlqCategory
from ingestion_pipeline.orchestration.batch_processing.document_result import DocumentResult
from ingestion_pipeline.orchestration.document_source import DocumentJob


def _make_job(
    source_file_s3_uri="s3://bucket/26-711111/file.pdf",
    correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
    case_ref="26-711111",
):
    return DocumentJob(
        source_file_s3_uri=source_file_s3_uri,
        correspondence_type=correspondence_type,
        case_ref=case_ref,
    )


def test_success_result_defaults_error_category_retryable_to_none():
    job = _make_job()

    result = DocumentResult(job=job, source_doc_id="some-id", success=True)

    assert result.job is job
    assert result.source_doc_id == "some-id"
    assert result.success is True
    assert result.error is None
    assert result.category is None
    assert result.retryable is None


def test_failure_result_carries_error_category_and_retryable():
    job = _make_job()
    error = ValueError("boom")

    result = DocumentResult(
        job=job,
        source_doc_id="some-id",
        success=False,
        error=error,
        category=DlqCategory.UNEXPECTED,
        retryable=False,
    )

    assert result.success is False
    assert result.error is error
    assert result.category is DlqCategory.UNEXPECTED
    assert result.retryable is False
