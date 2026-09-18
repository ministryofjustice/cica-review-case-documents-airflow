"""S3 URI validation utilities for the ingestion pipeline."""

import re


def validate_s3_uri(s3_uri: str, expected_bucket: str) -> bool:
    """Validates whether the given S3 URI matches the expected bucket and follows the required path pattern.

    Args:
        s3_uri (str): The S3 URI to validate (e.g., 's3://bucket/26-711111/').
        expected_bucket (str): The expected S3 bucket name.

    Returns:
        bool: True if the S3 URI matches the expected bucket and path pattern, False otherwise.
    Pattern:
        The S3 URI must start with 's3://{expected_bucket}/', followed by a directory in the format 'NN-NNNNNN/',
        where 'NN' is any two digits representing the year, and 'NNNNNN' starts with either 7 or 8.
    """
    pattern = rf"^s3://{re.escape(expected_bucket)}/\d{{2}}-[78]\d{{5}}/"
    return re.match(pattern, s3_uri) is not None
