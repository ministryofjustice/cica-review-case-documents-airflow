from unittest.mock import Mock

import pytest

from ingestion_pipeline.page_processor import s3_utils


def test_download_file_from_s3_success():
    s3_client = Mock()
    s3_client.get_object.return_value = {"Body": Mock(read=Mock(return_value=b"data"))}
    result = s3_utils.download_file_from_s3(s3_client, "bucket", "key")
    assert result == b"data"
    s3_client.get_object.assert_called_once_with(Bucket="bucket", Key="key")


def test_download_file_from_s3_client_error():
    s3_client = Mock()
    s3_client.get_object.side_effect = s3_utils.ClientError({}, "GetObject")
    with pytest.raises(s3_utils.ClientError):
        s3_utils.download_file_from_s3(s3_client, "bucket", "key")


def test_upload_file_to_s3_with_retry_success():
    s3_client = Mock()
    buf = Mock()
    s3_utils.upload_file_to_s3_with_retry(s3_client, buf, "bucket", "key", retries=2, delay=0)
    s3_client.upload_fileobj.assert_called_once_with(buf, "bucket", "key", ExtraArgs={"ContentType": "image/png"})


def test_upload_file_to_s3_with_retry_retries_and_fails(monkeypatch):
    s3_client = Mock()
    buf = Mock()
    s3_client.upload_fileobj.side_effect = Exception("fail")
    with pytest.raises(Exception, match="fail"):
        s3_utils.upload_file_to_s3_with_retry(s3_client, buf, "bucket", "key", retries=2, delay=0)
    assert s3_client.upload_fileobj.call_count == 2


def test_delete_files_from_s3_success():
    s3_client = Mock()
    keys = ["a", "b"]
    s3_utils.delete_files_from_s3(s3_client, "bucket", keys)
    assert s3_client.delete_object.call_count == 2
    s3_client.delete_object.assert_any_call(Bucket="bucket", Key="a")
    s3_client.delete_object.assert_any_call(Bucket="bucket", Key="b")


def test_delete_files_from_s3_with_error(caplog):
    s3_client = Mock()
    s3_client.delete_object.side_effect = [None, Exception("fail")]
    keys = ["a", "b"]
    s3_utils.delete_files_from_s3(s3_client, "bucket", keys)
    assert "Failed to delete b from bucket bucket" in caplog.text
