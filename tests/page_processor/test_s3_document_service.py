from unittest.mock import Mock, patch

import pytest

from ingestion_pipeline.page_processor.s3_document_service import S3DocumentService


@pytest.fixture
def s3_client():
    return Mock()


@pytest.fixture
def service(s3_client):
    return S3DocumentService(s3_client, "source-bucket", "page-bucket")


def test_download_pdf_success(service):
    with patch("ingestion_pipeline.page_processor.s3_document_service.download_file_from_s3") as mock_download:
        mock_download.return_value = b"pdf-bytes"
        result = service.download_pdf("s3://source-bucket/path/to/file.pdf")
        assert result == b"pdf-bytes"
        mock_download.assert_called_once_with(service.s3_client, "source-bucket", "path/to/file.pdf")


def test_download_pdf_invalid_uri(service):
    with pytest.raises(ValueError):
        service.download_pdf("not-an-s3-uri")


def test_download_pdf_failure(service):
    with patch(
        "ingestion_pipeline.page_processor.s3_document_service.download_file_from_s3", side_effect=Exception("fail")
    ):
        with pytest.raises(RuntimeError) as excinfo:
            service.download_pdf("s3://source-bucket/path/to/file.pdf")
        assert "Failed to download PDF from S3" in str(excinfo.value)


def test_upload_image_success(service):
    with patch("ingestion_pipeline.page_processor.s3_document_service.upload_file_to_s3_with_retry") as mock_upload:
        buf = Mock()
        service._upload_image(buf, "some/key.png")
        mock_upload.assert_called_once_with(service.s3_client, buf, "page-bucket", "some/key.png")


def test_upload_image_failure(service):
    with patch(
        "ingestion_pipeline.page_processor.s3_document_service.upload_file_to_s3_with_retry",
        side_effect=Exception("fail"),
    ):
        with pytest.raises(RuntimeError) as excinfo:
            service._upload_image(Mock(), "some/key.png")
        assert "Failed to upload image to S3" in str(excinfo.value)


def test__upload_image_raises_runtime_error(service):
    with patch(
        "ingestion_pipeline.page_processor.s3_document_service.upload_file_to_s3_with_retry",
        side_effect=Exception("fail"),
    ):
        with pytest.raises(RuntimeError):
            service._upload_image(Mock(), "key")


def test_delete_images_success(service):
    with patch("ingestion_pipeline.page_processor.s3_document_service.delete_files_from_s3") as mock_delete:
        service.delete_images(["key1", "key2"])
        mock_delete.assert_called_once_with(service.s3_client, "page-bucket", ["key1", "key2"])


def test_delete_images_failure(service):
    with patch(
        "ingestion_pipeline.page_processor.s3_document_service.delete_files_from_s3", side_effect=Exception("fail")
    ):
        with pytest.raises(RuntimeError) as excinfo:
            service.delete_images(["key1", "key2"])
        assert "Failed to delete images from S3" in str(excinfo.value)


def test_delete_images_raises_runtime_error(service):
    with patch(
        "ingestion_pipeline.page_processor.s3_document_service.delete_files_from_s3",
        side_effect=Exception("fail"),
    ):
        with pytest.raises(RuntimeError):
            service.delete_images(["key"])


def test_upload_page_images_success(service):
    # Arrange
    mock_image = Mock()
    mock_image.size = (100, 200)
    images = [mock_image, mock_image]
    case_ref = "case123"
    source_doc_id = "doc456"

    # Act
    with patch.object(service, "_upload_image") as mock_upload:
        results = service.upload_page_images(images, case_ref, source_doc_id)

    # Assert
    assert mock_upload.call_count == 2
    assert len(results) == 2
    assert results[0].s3_uri == "s3://page-bucket/case123/doc456/pages/1.png"
    assert results[1].width == 100


def test_upload_page_images_handles_upload_failure(service):
    # Arrange
    mock_image = Mock()
    mock_image.size = (100, 200)
    images = [mock_image]

    # Act & Assert
    with patch.object(service, "_upload_image", side_effect=RuntimeError("Upload failed")):
        with pytest.raises(RuntimeError, match="Upload failed"):
            service.upload_page_images(images, "case123", "doc456")
