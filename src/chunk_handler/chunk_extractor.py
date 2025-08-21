from typing import Optional, Set

from textractor.entities.document import Document

from data_models.chunk_models import DocumentMetadata, OpenSearchChunk


def metadata_validator(metadata: DocumentMetadata):
    """_summary_

    Args:
        metadata (DocumentMetadata): DocumentMetadata validator

    Raises:
        ValueError: DocumentMetadata cannot be None and its string fields cannot be empty
        ValueError: DocumentMetadata.page_count must be a positive integer.
    """
    if not metadata or not all(
        [
            metadata.ingested_doc_id,
            metadata.s3_page_image_uri,
            metadata.source_file_name,
        ]
    ):
        raise ValueError("DocumentMetadata cannot be None and its string fields cannot be empty.")

    if metadata.page_count <= 0:
        raise ValueError("DocumentMetadata.page_count must be a positive integer.")


def extract_layout_chunks(
    doc: Document, metadata: DocumentMetadata, desired_layout_types: Optional[Set[str]] = None
) -> list[OpenSearchChunk]:
    """
    Parses a Textractor Document and extracts specified layout blocks as structured chunks.

    :param doc: The Textractor Document object.
    :param metadata: An object containing document-level metadata.
    :param desired_layout_types: A set of layout type strings to extract (e.g., {"LAYOUT_TEXT", "LAYOUT_TITLE"}).
    :raises ValueError: If the metadata object is None or contains empty/invalid values.
    """

    metadata_validator(metadata)

    if desired_layout_types is None:
        desired_layout_types = {"LAYOUT_TEXT"}

    chunks: list[OpenSearchChunk] = []
    chunk_index_counter = 0

    for page in doc.pages:
        # TODO consider moving this out of here, this should be created and added to a page index
        s3_page_image_uri = f"{metadata.s3_page_image_uri}/page_{page.page_num}.png"

        chunk_metadata = DocumentMetadata(
            ingested_doc_id=metadata.ingested_doc_id,
            s3_page_image_uri=s3_page_image_uri,
            source_file_name=metadata.source_file_name,
            page_count=metadata.page_count,
            case_ref=metadata.case_ref,
            received_date=metadata.received_date,
            correspondence_type=metadata.correspondence_type,
        )

        for layout_block in page.layouts:
            if layout_block.layout_type in desired_layout_types and layout_block.text.strip():
                chunk = OpenSearchChunk.from_textractor_layout(
                    block=layout_block, page=page, metadata=chunk_metadata, chunk_index=chunk_index_counter
                )
                chunks.append(chunk)
                chunk_index_counter += 1

    return chunks
