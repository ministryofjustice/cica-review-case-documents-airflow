import logging

import boto3

from ingestion_code.config import settings

logger = logging.getLogger(__name__)

s3 = boto3.client(
    service_name="s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    aws_session_token=settings.AWS_SESSION_TOKEN,
)


def list_object_keys_in_s3_bucket(prefix: str) -> list[str]:
    """Get S3 URIs in an S3 bucket for all objects with the given prefix."""

    response = s3.list_objects_v2(Bucket=settings.S3_BUCKET_NAME, Prefix=prefix)

    obj_uri = []

    # Download each object to the local directory
    for obj in response.get("Contents", []):
        object_key = obj.get("Key")

        # Skip directories
        if object_key.endswith("/"):
            continue

        uri = f"s3://{settings.S3_BUCKET_NAME}/{object_key}"

        obj_uri.append(uri)

    return obj_uri
