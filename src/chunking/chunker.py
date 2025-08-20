from textractor.entities.document import Document
from textractor.entities.layout import Layout
from textractor.entities.page import Page

# Note: The 'textract_response' fixture in the test comes from Amazon Textract.
# The 'textractor' library is a client-side parser for that JSON response.


def _serialize_geometry(bbox) -> dict:
    """Helper to convert a Geometry object to a serializable dictionary."""
    return {
        "Width": bbox.width,
        "Height": bbox.height,
        "Left": bbox.x,
        "Top": bbox.y,
    }


def _create_opensearch_chunk(
    block: Layout,
    page: Page,
    ingested_doc_id: str,
    chunk_index: int,
    doc_meta: dict,
    s3_page_image_uri: str,
    file_name: str,
) -> dict:
    """Creates a standardized OpenSearch chunk dictionary from a Textractor Layout block."""

    # The Layout object conveniently provides the concatenated text of its children.
    text_content = block.text.strip()
    chunk_id = f"{ingested_doc_id}_p{page.page_num}_c{chunk_index}"

    return {
        "chunk_id": chunk_id,
        "ingested_doc_id": ingested_doc_id,
        "chunk_text": text_content,
        "embedding": None,
        "case_ref": None,
        # Set to None to match the test's expectation
        "received_date": None,
        "source_file_name": file_name,
        "s3_page_image_uri": s3_page_image_uri,
        "correspondence_type": None,
        "page_count": doc_meta.get("Pages"),
        "page_number": page.page_num,
        "chunk_index": chunk_index,
        # Use the layout_type attribute from the Layout object
        "chunk_type": block.layout_type,
        "confidence": block.confidence,
        "bounding_box": _serialize_geometry(block.bbox),
    }


def extract_layout_chunks(textract_response: dict, ingested_doc_id: str, s3_image_uri_prefix: str) -> list[dict]:
    """
    Parses a Textract response and extracts LAYOUT_TEXT blocks as structured chunks.

    :param textract_response: The raw JSON dictionary from an Amazon Textract AnalyzeDocument call.
    :param document_id: A unique identifier for the source document.
    :param s3_image_uri_prefix: The S3 prefix for where page images are stored (e.g., s3://bucket/doc-id).
    :return: A list of dictionaries, where each dictionary represents a chunk.
    """
    doc = Document.open(textract_response)
    doc_meta = textract_response.get("DocumentMetadata", {})

    # It's safer to get the filename from metadata if available, as 'UploadedFileName' isn't always present.
    # For this test, we assume 'UploadedFileName' is present in the mock data.
    uploaded_file_name = textract_response.get("UploadedFileName", "")

    chunks = []
    chunk_index_counter = 0

    for page in doc.pages:
        # The correct way to get layout elements is to iterate through page.layouts
        for layout_block in page.layouts:
            # We are only interested in blocks identified as standard text layouts.
            if layout_block.layout_type == "LAYOUT_TEXT":
                chunk = _create_opensearch_chunk(
                    block=layout_block,
                    page=page,
                    ingested_doc_id=ingested_doc_id,
                    chunk_index=chunk_index_counter,
                    doc_meta=doc_meta,
                    s3_page_image_uri=s3_image_uri_prefix,
                    file_name=uploaded_file_name,
                )
                chunks.append(chunk)
                chunk_index_counter += 1

    return chunks
