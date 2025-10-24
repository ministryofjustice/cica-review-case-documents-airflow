import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from ingestion_pipeline.config import settings

NAMESPACE_DOC_INGESTION = uuid.UUID(settings.SYSTEM_UUID_NAMESPACE)


class DocumentIdentifier(BaseModel):
    """
    Immutable input data used for generating deterministic UUIDs.
    Contains the "natural key" components of a document or page.
    """

    model_config = ConfigDict(frozen=True)

    source_file_name: str
    correspondence_type: str
    case_ref: str
    page_num: Optional[int] = None

    @field_validator("source_file_name", "correspondence_type", "case_ref")
    @classmethod
    def normalize_strings(cls, v: str) -> str:
        """
        Ensures all key strings are non-null, stripped,
        and lowercased for deterministic hashing.
        """
        return (v or "").strip().lower()

    def generate_uuid(self) -> str:
        """
        Creates a deterministic Version 5 UUID from this object's data.

        - If self.page_num is None, generates a DOCUMENT-level UUID.
        - If self.page_num is provided, generates a PAGE-level UUID.
        """

        data_parts = [self.source_file_name, self.correspondence_type, self.case_ref]

        # Conditionally add the page number
        if self.page_num is not None:
            data_parts.append(str(self.page_num))

        data_string = "-".join(data_parts)

        return str(uuid.uuid5(NAMESPACE_DOC_INGESTION, data_string))
