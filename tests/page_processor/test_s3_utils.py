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


def test_delete_prefix_from_s3_deletes_all_matching_objects():
    s3_client = Mock()
    paginator = Mock()
    s3_client.get_paginator.return_value = paginator
    # Two pages of results to exercise pagination handling.
    paginator.paginate.return_value = [
        {"Contents": [{"Key": "case/doc/pages/1.png"}, {"Key": "case/doc/pages/2.png"}]},
        {"Contents": [{"Key": "case/doc/pages/3.png"}]},
    ]
    # DeleteObjects confirms deletions in the "Deleted" list.
    s3_client.delete_objects.side_effect = [
        {"Deleted": [{"Key": "case/doc/pages/1.png"}, {"Key": "case/doc/pages/2.png"}]},
        {"Deleted": [{"Key": "case/doc/pages/3.png"}]},
    ]

    deleted = s3_utils.delete_prefix_from_s3(s3_client, "bucket", "case/doc/pages/")

    assert deleted == 3
    s3_client.get_paginator.assert_called_once_with("list_objects_v2")
    paginator.paginate.assert_called_once_with(Bucket="bucket", Prefix="case/doc/pages/")
    assert s3_client.delete_objects.call_count == 2
    s3_client.delete_objects.assert_any_call(
        Bucket="bucket",
        Delete={"Objects": [{"Key": "case/doc/pages/1.png"}, {"Key": "case/doc/pages/2.png"}]},
    )


def test_delete_prefix_from_s3_handles_empty_prefix():
    s3_client = Mock()
    paginator = Mock()
    s3_client.get_paginator.return_value = paginator
    # No Contents key when the prefix matches nothing.
    paginator.paginate.return_value = [{}]

    deleted = s3_utils.delete_prefix_from_s3(s3_client, "bucket", "case/doc/pages/")

    assert deleted == 0
    s3_client.delete_objects.assert_not_called()


def test_delete_prefix_from_s3_raises_on_partial_failure(caplog):
    s3_client = Mock()
    paginator = Mock()
    s3_client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"Contents": [{"Key": "case/doc/pages/1.png"}, {"Key": "case/doc/pages/2.png"}]},
    ]
    # DeleteObjects returns HTTP 200 but reports a per-key failure in "Errors".
    s3_client.delete_objects.return_value = {
        "Deleted": [{"Key": "case/doc/pages/1.png"}],
        "Errors": [
            {
                "Key": "case/doc/pages/2.png",
                "Code": "AccessDenied",
                "Message": "Access Denied",
            }
        ],
    }

    with pytest.raises(RuntimeError) as excinfo:
        s3_utils.delete_prefix_from_s3(s3_client, "bucket", "case/doc/pages/")

    assert "case/doc/pages/2.png" in str(excinfo.value)
    assert "1 object(s) could not be deleted" in str(excinfo.value)
    assert "Failed to delete 'case/doc/pages/2.png'" in caplog.text


def test_delete_prefix_from_s3_counts_only_confirmed_deletions():
    s3_client = Mock()
    paginator = Mock()
    s3_client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"Contents": [{"Key": "case/doc/pages/1.png"}, {"Key": "case/doc/pages/2.png"}]},
    ]
    # Only one key is confirmed deleted; no errors reported.
    s3_client.delete_objects.return_value = {"Deleted": [{"Key": "case/doc/pages/1.png"}]}

    deleted = s3_utils.delete_prefix_from_s3(s3_client, "bucket", "case/doc/pages/")

    assert deleted == 1
