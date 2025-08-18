import json
import logging
import os
import tempfile
import time
from enum import Enum
from typing import Any

import fitz
from botocore.exceptions import ClientError
from config import settings
from ingestion_code.aws_clients import s3, textract
from ingestion_code.utils import get_s3_keys

logger = logging.getLogger(__name__)


class TextractMode(Enum):
    TEXT_DETECTION = "text-detection"
    DOCUMENT_ANALYSIS = "document-analysis"


def run_textract_on_pdf(bucket: str, key: str, mode: TextractMode, features: str | None = None) -> list[dict[str, Any]]:
    """
    Run Textract on a PDF, wait for completion, and return the response as a dictionary.
    """

    document_location = {"S3Object": {"Bucket": bucket, "Name": key}}

    # 1) start the async job
    if mode == TextractMode.TEXT_DETECTION:
        resp = textract.start_document_text_detection(DocumentLocation=document_location)
    elif mode == TextractMode.DOCUMENT_ANALYSIS:
        if not features:
            raise ValueError("Feature types are required for document_analysis.")
        resp = textract.start_document_analysis(DocumentLocation=document_location, FeatureTypes=features)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    job_id = resp["JobId"]
    logger.info("Started Textract %s job %s for %r", mode, job_id, key)

    # 2) poll until done
    # TO DO: Get the completion status from the Amazon SNS topic, using an Amazon SQS
    # queue, or an AWS Lambda function.
    responses = []
    while True:
        if mode == TextractMode.TEXT_DETECTION:
            response = textract.get_document_text_detection(JobId=job_id)
        elif mode == TextractMode.DOCUMENT_ANALYSIS:
            response = textract.get_document_analysis(JobId=job_id)
        else:
            raise ValueError("Invalid mode for result retrieval.")
        status = response["JobStatus"]
        if status == "SUCCEEDED":
            responses.append(response)
            while "NextToken" in response:
                next_token = response["NextToken"]
                if mode == TextractMode.TEXT_DETECTION:
                    response = textract.get_document_text_detection(JobId=job_id, NextToken=next_token)
                else:
                    response = textract.get_document_analysis(JobId=job_id, NextToken=next_token)
                responses.append(response)
            logger.info("Finished Textract %s job %s for %r", mode, job_id, key)
            break
        elif status == "FAILED":
            raise RuntimeError("Textract job failed.")
        else:
            logger.debug("Waiting for Textract job %s… status=%s", job_id, status)
            time.sleep(settings.POLL_INTERVAL_SECONDS)

    return responses


def _upload_json(
    bucket: str,
    prefix: str,
    doc_key: str,
    mode: TextractMode,
    responses: list[dict[str, Any]],
) -> None:
    """
    Upload the Textract responses in a single JSON file for a single document.
    """
    total_pages = responses[0]["DocumentMetadata"]["Pages"]
    # Combine all response blocks into a single list of blocks
    all_blocks = []
    for resp in responses:
        all_blocks.extend(resp["Blocks"])

    # Store in a unified dictionary
    full_document = {
        "document_key": doc_key,
        "DocumentMetadata": {"Pages": total_pages},
        "Blocks": all_blocks,
    }

    body = json.dumps(full_document)
    base = doc_key.replace(prefix, f"{prefix}/{mode.value}")
    out_key = f"{base.rstrip('.pdf')}.json"

    # Upload object to S3
    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        "Saved complete Textract response as a JSON file of %r to s3://%s/%s",
        doc_key,
        bucket,
        out_key,
    )


def run_textract_and_upload_responses(
    bucket: str, prefix: str, mode: TextractMode, features: str | None = None
) -> None:
    """Use Textract to extract text from PDFs in S3 and save it to JSON files."""
    pdf_keys = get_s3_keys(bucket, prefix, ".pdf")
    if not pdf_keys:
        logger.warning("No PDF files found under %s", prefix)
        return

    for key in pdf_keys:
        try:
            responses = run_textract_on_pdf(bucket, key, mode, features)

            _upload_json(bucket, prefix, key, mode, responses)

        except ClientError as e:
            logger.error("S3 error processing %r: %s", key, e)
        except Exception:
            logger.exception("Unexpected error processing %r", key)


def save_pdf_pages_as_images(bucket: str, prefix: str) -> None:
    """
    Downloads PDFs locally from S3, renders each page to PNG, ane uploads back to S3.
    """
    for key in get_s3_keys(bucket, prefix, ".pdf"):
        try:
            # 1) Download PDF to a temp file
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                local_pdf_path = tmp.name
                s3.download_file(bucket, key, local_pdf_path)

            # 2) Open with PyMuPDF
            doc = fitz.open(local_pdf_path)
            base_name = os.path.splitext(os.path.basename(key))[0]
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")

                # 3) Upload each page
                out_key = prefix + "/images/" + f"{base_name}_page_{page_index + 1:03}.png"
                s3.put_object(Bucket=bucket, Key=out_key, Body=img_data, ContentType="image/png")
                logger.info(
                    "Uploaded image for %r page %d to s3://%s/%s",
                    key,
                    page_index + 1,
                    bucket,
                    out_key,
                )

            doc.close()
        except Exception:
            logger.exception("Failed to process %r", key)
        finally:
            # clean up
            try:
                os.remove(local_pdf_path)
            except Exception:
                pass
