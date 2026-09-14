import pytest

from ingestion_pipeline.s3_utils.s3_uri import validate_s3_uri

BUCKET = "my-bucket"


@pytest.mark.parametrize(
    "s3_uri",
    [
        "s3://my-bucket/26-711111/file.pdf",
        "s3://my-bucket/26-811111/file.pdf",
        "s3://my-bucket/00-700000/document.pdf",
        "s3://my-bucket/99-899999/nested/path/file.pdf",
        "s3://my-bucket/26-711111/",
    ],
)
def test_valid_uris_return_true(s3_uri):
    assert validate_s3_uri(s3_uri, BUCKET) is True


def test_wrong_bucket_returns_false():
    assert validate_s3_uri("s3://other-bucket/26-711111/file.pdf", BUCKET) is False


@pytest.mark.parametrize(
    "s3_uri",
    [
        # leading digit of the six-digit part is not 7 or 8
        "s3://my-bucket/26-611111/file.pdf",
        "s3://my-bucket/26-911111/file.pdf",
        # wrong count of leading (year) digits
        "s3://my-bucket/2-711111/file.pdf",
        "s3://my-bucket/263-711111/file.pdf",
        # wrong count of trailing digits (needs 7 or 8 then five more)
        "s3://my-bucket/26-71111/file.pdf",
        "s3://my-bucket/26-7111111/file.pdf",
        # missing hyphen
        "s3://my-bucket/26711111/file.pdf",
        # missing trailing slash after the case-ref directory
        "s3://my-bucket/26-711111",
        # non-digit characters
        "s3://my-bucket/ab-711111/file.pdf",
        # wrong scheme / prefix
        "https://my-bucket/26-711111/file.pdf",
        "",
    ],
)
def test_malformed_patterns_return_false(s3_uri):
    assert validate_s3_uri(s3_uri, BUCKET) is False
