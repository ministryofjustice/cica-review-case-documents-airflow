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
        mock_settings.SRC_S3_KEY = ""
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


def test_sqs_source_fetch_batch_builds_jobs_from_multiple_src_s3_keys():
    with mock.patch("ingestion_pipeline.orchestration.document_source.settings") as mock_settings:
        # Comma-separated keys (with surrounding whitespace / a trailing empty entry)
        # should each produce a job derived from that key.
        mock_settings.SRC_S3_KEY = "26-700030/case30.pdf, 26-800040/case40.pdf,"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "bucket"
        # Fallback settings must be ignored when SRC_S3_KEY is populated.
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX = "26-711111"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME = "file.pdf"

        source = SqsDocumentSource()
        batch = source.fetch_batch()

    assert len(batch) == 2

    first, second = batch
    assert first.source_file_s3_uri == "s3://bucket/26-700030/case30.pdf"
    assert first.case_ref == "26-700030"
    assert first.source_file_name == "case30.pdf"

    assert second.source_file_s3_uri == "s3://bucket/26-800040/case40.pdf"
    assert second.case_ref == "26-800040"
    assert second.source_file_name == "case40.pdf"


def test_sqs_source_acknowledge_is_noop():
    source = SqsDocumentSource(queue_url="http://queue", max_messages=5)
    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/file.pdf",
        correspondence_type="TC19",
        case_ref="26-711111",
    )
    # Stub acknowledge should not raise.
    assert source.acknowledge(job) is None
