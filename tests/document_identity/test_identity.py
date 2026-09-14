import datetime
from unittest import mock

from ingestion_pipeline.document_identity.identity import build_document_metadata, compute_source_doc_id
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


def test_compute_source_doc_id_is_deterministic_for_equal_natural_keys():
    job_a = _make_job()
    job_b = _make_job()

    assert compute_source_doc_id(job_a) == compute_source_doc_id(job_b)


def test_compute_source_doc_id_stable_across_repeated_calls():
    job = _make_job()

    assert compute_source_doc_id(job) == compute_source_doc_id(job)


def test_compute_source_doc_id_differs_when_source_file_name_differs():
    job_a = _make_job(source_file_s3_uri="s3://bucket/26-711111/file_a.pdf")
    job_b = _make_job(source_file_s3_uri="s3://bucket/26-711111/file_b.pdf")

    assert compute_source_doc_id(job_a) != compute_source_doc_id(job_b)


def test_compute_source_doc_id_differs_when_correspondence_type_differs():
    job_a = _make_job(correspondence_type="TC19 - ADDITIONAL INFO REQUEST")
    job_b = _make_job(correspondence_type="TC20 - SOMETHING ELSE")

    assert compute_source_doc_id(job_a) != compute_source_doc_id(job_b)


def test_compute_source_doc_id_differs_when_case_ref_differs():
    job_a = _make_job(source_file_s3_uri="s3://bucket/26-711111/file.pdf", case_ref="26-711111")
    job_b = _make_job(source_file_s3_uri="s3://bucket/26-811111/file.pdf", case_ref="26-811111")

    assert compute_source_doc_id(job_a) != compute_source_doc_id(job_b)


def test_build_document_metadata_maps_fields_from_job():
    job = _make_job()
    source_doc_id = "some-source-doc-id"

    metadata = build_document_metadata(job, source_doc_id)

    assert metadata.source_doc_id == source_doc_id
    assert metadata.source_file_name == job.source_file_name
    assert metadata.source_file_s3_uri == job.source_file_s3_uri
    assert metadata.case_ref == job.case_ref
    assert metadata.correspondence_type == job.correspondence_type


def test_build_document_metadata_sets_page_count_none():
    metadata = build_document_metadata(_make_job(), "id")

    assert metadata.page_count is None


def test_build_document_metadata_received_date_is_naive_utc():
    frozen = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    with mock.patch("ingestion_pipeline.document_identity.identity.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = frozen
        mock_datetime.timezone.utc = datetime.timezone.utc

        metadata = build_document_metadata(_make_job(), "id")

    assert metadata.received_date.tzinfo is None
    assert metadata.received_date == frozen.replace(tzinfo=None)
