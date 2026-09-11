from unittest import mock

from ingestion_pipeline.orchestration.document_source import DocumentJob, SqsDocumentSource


def test_document_job_source_file_name_derived_from_uri():
    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/some_file.pdf",
        correspondence_type="TC19",
        case_ref="26-711111",
    )
    assert job.source_file_name == "some_file.pdf"


def test_document_job_source_file_name_ignores_trailing_slash():
    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/some_file.pdf/",
        correspondence_type="TC19",
        case_ref="26-711111",
    )
    assert job.source_file_name == "some_file.pdf"


def test_sqs_source_fetch_batch_builds_job_from_settings():
    with mock.patch("ingestion_pipeline.orchestration.document_source.settings") as mock_settings:
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "bucket"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX = "26-711111"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME = "file.pdf"

        source = SqsDocumentSource()
        batch = source.fetch_batch()

    assert len(batch) == 1
    job = batch[0]
    assert job.source_file_s3_uri == "s3://bucket/26-711111/file.pdf"
    assert job.case_ref == "26-711111"
    assert job.source_file_name == "file.pdf"


def test_sqs_source_acknowledge_is_noop():
    source = SqsDocumentSource(queue_url="http://queue", max_messages=5)
    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/file.pdf",
        correspondence_type="TC19",
        case_ref="26-711111",
    )
    # Stub acknowledge should not raise.
    assert source.acknowledge(job) is None
