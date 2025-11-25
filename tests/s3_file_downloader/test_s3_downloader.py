import os
import unittest

import boto3
from botocore.exceptions import ClientError
from moto import mock_aws

# Import the function to be tested
from ingestion_pipeline.s3_file_downloader.s3_downloader import download_pdf_from_s3


@mock_aws
class TestS3Downloader(unittest.TestCase):
    def setUp(self):
        """Set up the mock S3 environment before each test.
        This method runs before each test function.
        """
        self.bucket_name = "my-test-bucket"
        self.s3_client = boto3.client("s3", region_name="us-east-1")
        self.s3_client.create_bucket(Bucket=self.bucket_name)
        self.download_dir = "test_downloads"
        os.makedirs(self.download_dir, exist_ok=True)

    def tearDown(self):
        """Clean up the mock S3 environment and local files after each test.
        This method runs after each test function.
        """
        # Clean up downloaded files
        for item in os.listdir(self.download_dir):
            os.remove(os.path.join(self.download_dir, item))
        os.rmdir(self.download_dir)

    def test_download_pdf_successfully(self):
        """Test case for successfully downloading a PDF from S3.
        This test now also implicitly checks that no exception is raised.
        """
        file_key = "test.pdf"
        local_file_path = os.path.join(self.download_dir, file_key)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n..."

        self.s3_client.put_object(Bucket=self.bucket_name, Key=file_key, Body=pdf_content)

        # Call the function to be tested
        download_pdf_from_s3(self.bucket_name, file_key, local_file_path)

        # Assertions
        self.assertTrue(os.path.exists(local_file_path))
        with open(local_file_path, "rb") as f:
            self.assertEqual(f.read(), pdf_content)

    def test_download_pdf_raises_error_if_not_found(self):
        """Test that a ClientError is raised if the file does not exist."""
        non_existent_file_key = "non_existent.pdf"
        local_file_path = os.path.join(self.download_dir, non_existent_file_key)

        # Use assertRaises as a context manager to check for the exception
        with self.assertRaises(ClientError) as cm:
            download_pdf_from_s3(self.bucket_name, non_existent_file_key, local_file_path)

        # Optionally, assert details about the exception
        self.assertEqual(cm.exception.response["Error"]["Code"], "404")
        self.assertFalse(os.path.exists(local_file_path))
