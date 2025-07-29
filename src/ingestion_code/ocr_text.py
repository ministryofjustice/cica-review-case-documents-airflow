import json
import logging
import os
import tempfile
import time
from typing import Any, Iterator

import boto3
import fitz
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
textract = boto3.client("textract")
POLL_INTERVAL_SECONDS = 5
S3_BUCKET = "alpha-a2j-projects"
S3_PREFIX = "textract-test"


def list_pdfs(bucket: str, prefix: str) -> Iterator[str]:
    """Yield all .pdf keys under the given bucket/prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".pdf"):
                yield key


def extract_text_from_pdf(bucket: str, key: str) -> list[dict[str, Any]]:
    """
    Submit the PDF to Textract, wait for completion, and return a list of detected text.
    """
    # 1) start the async job
    resp = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )
    job_id = resp["JobId"]
    logger.info("Started Textract text extraction job %s for %r", job_id, key)

    # 2) poll until done
    while True:
        status = textract.get_document_text_detection(JobId=job_id)["JobStatus"]
        if status in ("SUCCEEDED", "FAILED"):
            break
        logger.debug("Waiting for Textract job %s… status=%s", job_id, status)
        time.sleep(POLL_INTERVAL_SECONDS)

    if status != "SUCCEEDED":
        msg = f"Textract job {job_id} failed for {key!r}"
        logger.error(msg)
        raise RuntimeError(msg)

    # 3) # collect blocks, grouping by page
    pages: dict[int, dict[str, Any]] = {}
    next_token = None
    while True:
        kwargs = {"JobId": job_id}
        if next_token:
            kwargs["NextToken"] = next_token
        page = textract.get_document_text_detection(**kwargs)

        # Loop over response blocks to store required info
        for block in page["Blocks"]:
            pg = block["Page"]  # page number
            slot = pages.setdefault(pg, {"lines": [], "words": []})
            if block["BlockType"] == "LINE":
                slot["lines"].append(block["Text"])
            elif block["BlockType"] == "WORD":
                slot["words"].append(
                    {
                        "text": block["Text"],
                        "bounding_box": block["Geometry"]["BoundingBox"],
                        "confidence": block["Confidence"],
                    }
                )

        next_token = page.get("NextToken")
        if not next_token:
            break

    # 4) build ordered list of page dicts
    result: list[dict[str, Any]] = []
    for pg, data in sorted(pages.items()):
        result.append(
            {
                "page_number": pg,
                "text": "\n".join(data["lines"]),
                "words": data["words"],
            }
        )
    return result


def _upload_page_json(
    bucket: str, prefix: str, doc_key: str, page: dict[str, Any]
) -> None:
    """
    Upload a single-page JSON blob (with words+boxes+confidence).
    """
    payload = {"document_key": doc_key, **page}
    body = json.dumps(payload)

    base = doc_key.replace(prefix, f"{prefix}/extracted")
    out_key = f"{base.rstrip('.pdf')}_page_{page['page_number']:03}.json"

    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )
    logger.info(
        "Saved page %d JSON of %r to s3://%s/%s",
        page["page_number"],
        doc_key,
        bucket,
        out_key,
    )


def call_textract(bucket: str, prefix: str) -> None:
    """Use Textract to extract text from PDFs in S3 and save it to JSON files."""
    pdf_keys = list(list_pdfs(bucket, prefix))
    if not pdf_keys:
        logger.warning("No PDF files found under %s", prefix)
        return

    for key in pdf_keys:
        try:
            pages = extract_text_from_pdf(bucket, key)

            for page in pages:
                _upload_page_json(bucket, prefix, key, page)

        except ClientError as e:
            logger.error("S3 error processing %r: %s", key, e)
        except Exception:
            logger.exception("Unexpected error processing %r", key)


def save_pdf_pages_as_images(
    bucket: str = S3_BUCKET,
    prefix: str = S3_PREFIX,
) -> None:
    """
    Downloads PDFs locally from S3, renders each page to PNG, ane uploads back to S3.
    """
    for key in list_pdfs(bucket, prefix):
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
                out_key = (
                    prefix
                    + "/extracted/images/"
                    + f"{base_name}_page_{page_index + 1:03}.png"
                )
                s3.put_object(
                    Bucket=bucket, Key=out_key, Body=img_data, ContentType="image/png"
                )
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
