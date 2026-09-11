"""Utility functions for interacting with AWS S3, including downloading, uploading with retry logic, and deleting files.

Functions:
    download_file_from_s3(s3_client, bucket, key):
        Downloads a file from the specified S3 bucket and key.

Args:
            s3_client: Boto3 S3 client instance.
            bucket (str): Name of the S3 bucket.
            key (str): Key of the file to download.

Returns:
            bytes: The content of the downloaded file.

Raises:
            ClientError: If the download fails.

    upload_file_to_s3_with_retry(s3_client, buf, bucket, key, retries=3, delay=2):
        Uploads a file-like object to S3 with retry logic.

Args:
            s3_client: Boto3 S3 client instance.
            buf: File-like object to upload.
            bucket (str): Name of the S3 bucket.
            key (str): Key under which to store the file.
            retries (int, optional): Number of retry attempts. Defaults to 3.
            delay (int, optional): Delay in seconds between retries. Defaults to 2.

Raises:
            Exception: If all retry attempts fail.

    delete_files_from_s3(s3_client, bucket, keys):
        Deletes multiple files from the specified S3 bucket.

Args:
            s3_client: Boto3 S3 client instance.
            bucket (str): Name of the S3 bucket.
            keys (list): List of keys to delete.
"""

import logging
import time

import boto3

ClientError = boto3.client("s3").exceptions.ClientError

logger = logging.getLogger(__name__)

MAX_UPLOAD_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def download_file_from_s3(s3_client, bucket, key):
    """Download a file from an S3 bucket using the provided S3 client.

    Args:
        s3_client (boto3.client): The boto3 S3 client to use for downloading the file.
        bucket (str): The name of the S3 bucket.
        key (str): The key (path) of the file in the S3 bucket.

    Returns:
        bytes: The contents of the downloaded file.

    Raises:
        ClientError: If there is an error downloading the file from S3.
    """
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except ClientError as e:
        logger.error(f"Error downloading {key} from bucket {bucket}: {e}")
        raise


def upload_file_to_s3_with_retry(s3_client, buf, bucket, key, retries=MAX_UPLOAD_RETRIES, delay=RETRY_DELAY_SECONDS):
    """Uploads a file-like object to an S3 bucket with retry logic.

    Attempts to upload the provided buffer to the specified S3 bucket and key using the given S3 client.
    If the upload fails, it will retry up to `retries` times, waiting `delay` seconds between attempts.
    Raises the last encountered exception if all retries fail.

    Args:
        s3_client (boto3.client): The S3 client to use for uploading.
        buf (file-like object): The file-like object to upload.
        bucket (str): The name of the S3 bucket.
        key (str): The S3 object key (path in the bucket).
        retries (int, optional): Number of times to retry on failure. Defaults to 3.
        delay (int or float, optional): Delay in seconds between retries. Defaults to 2.

    Raises:
        Exception: The last exception encountered if all retries fail.
    """
    attempt = 0
    while attempt < retries:
        try:
            s3_client.upload_fileobj(buf, bucket, key, ExtraArgs={"ContentType": "image/png"})
            return
        except Exception as e:
            attempt += 1
            logger.error(f"Upload failed for {key} (attempt {attempt}): {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                raise


def delete_files_from_s3(s3_client, bucket, keys):
    """Delete multiple files from an S3 bucket.

    Args:
        s3_client (boto3.client): The boto3 S3 client used to interact with S3.
        bucket (str): The name of the S3 bucket.
        keys (list of str): A list of object keys to delete from the bucket.

    Logs:
        Info message for each successfully deleted file.
        Error message if deletion of a file fails.
    """
    for key in keys:
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"Deleted {key} from bucket {bucket}")
        except Exception as e:
            logger.error(f"Failed to delete {key} from bucket {bucket}: {e}")


def delete_prefix_from_s3(s3_client, bucket, prefix):
    """Delete every object under a key prefix in an S3 bucket.

    Lists all objects sharing the given prefix (handling pagination) and deletes
    them. This is used to clean up all page images for a document regardless of
    how many were uploaded, so a partial or concurrent upload leaves nothing behind.

    Args:
        s3_client (boto3.client): The boto3 S3 client used to interact with S3.
        bucket (str): The name of the S3 bucket.
        prefix (str): The key prefix whose objects should be deleted.

    Returns:
        int: The number of objects successfully deleted.

    Raises:
        ClientError: If listing or deleting objects fails.
        RuntimeError: If S3 reports per-key errors in the DeleteObjects response,
            meaning some objects could not be deleted and orphaned images remain.
    """
    deleted = 0
    errors = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if not objects:
            continue
        # delete_objects accepts up to 1000 keys per call; a single list page never
        # exceeds that, so one call per page is safe.
        response = s3_client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        # DeleteObjects can return HTTP 200 while reporting per-key failures in
        # "Errors". Only count keys S3 confirms in "Deleted"; surface the rest so a
        # partial cleanup is not reported as success (which would leave orphaned
        # page images without triggering the pipeline's cleanup warning).
        deleted += len(response.get("Deleted", []))
        for error in response.get("Errors", []):
            logger.error(
                f"Failed to delete '{error.get('Key')}' from bucket {bucket}: "
                f"{error.get('Code')} - {error.get('Message')}"
            )
            errors.append(error)
    if errors:
        failed_keys = [error.get("Key") for error in errors]
        raise RuntimeError(
            f"Deleted {deleted} object(s) under prefix '{prefix}' from bucket {bucket}, "
            f"but {len(errors)} object(s) could not be deleted: {failed_keys}."
        )
    logger.info(f"Deleted {deleted} object(s) under prefix '{prefix}' from bucket {bucket}.")
    return deleted
