"""Factory for creating DocumentPage instances."""

from ingestion_pipeline.chunking.schemas import DocumentPage
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier


class DocumentPageFactory:
    """Factory class for creating DocumentPage instances.

    Methods:
        create(metadata, page, s3_uri, img_width, img_height):
            Constructs and returns a DocumentPage object using the provided metadata, page information,
            S3 URI for the page image, and image dimensions.

    Args:
        metadata: An object containing metadata about the source document, such as source_doc_id,
            source_file_name, correspondence_type, case_ref, received_date, and page_count.
        page: An object representing a single page of the document, expected to have at least a page_num
            attribute and optionally a text attribute.
        s3_uri (str): The S3 URI where the page image is stored.
        img_width (int): The width of the page image.
        img_height (int): The height of the page image.

    Returns:
        DocumentPage: An instance of DocumentPage populated with the provided information.
    """

    def create(self, metadata, page, s3_uri, img_width, img_height):
        """Constructs and returns a DocumentPage object using the provided metadata, page information.

        S3 URI for the page image, and image dimensions.

        Args:
            metadata: An object containing metadata about the source document, such as source_doc_id,
                source_file_name, correspondence_type, case_ref, received_date, and page_count.
            page: An object representing a single page of the document, expected to have at least a page_num
                attribute and optionally a text attribute.
            s3_uri (str): The S3 URI where the page image is stored.
            img_width (int): The width of the page image.
            img_height (int): The height of the page image.

        Returns:
            DocumentPage: An instance of DocumentPage populated with the provided information.
        """
        return DocumentPage(
            source_doc_id=metadata.source_doc_id,
            page_num=page.page_num,
            page_id=DocumentIdentifier(
                source_file_name=metadata.source_file_name,
                correspondence_type=metadata.correspondence_type,
                case_ref=metadata.case_ref,
                page_num=page.page_num,
            ).generate_uuid(),
            page_width=img_width,
            page_height=img_height,
            text=getattr(page, "text", ""),
            received_date=metadata.received_date,
            page_count=metadata.page_count,
            s3_page_image_s3_uri=s3_uri,
            correspondence_type=metadata.correspondence_type,
        )
