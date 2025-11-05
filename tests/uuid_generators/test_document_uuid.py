import datetime
import uuid
from unittest.mock import patch

import pytest

from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

MOCK_NAMESPACE_UUID = "1b671a64-40d5-491e-99b0-da01ff1f3341"
MOCK_NAMESPACE_OBJ = uuid.UUID(MOCK_NAMESPACE_UUID)


@pytest.fixture
def base_data():
    """Provides common data for the UUID generation tests.
    Keys MUST match the DocumentIdentifier model fields.
    """
    return {
        "source_file_name": "source_document.pdf",
        "correspondence_type": "TC19",
        "received_date": datetime.date(2025, 10, 6),
        "case_ref": "25-111111",
    }


@patch(
    "ingestion_pipeline.uuid_generators.document_uuid.NAMESPACE_DOC_INGESTION",
    MOCK_NAMESPACE_OBJ,
)
@pytest.mark.parametrize(
    "page_num, expected_page_str",
    [
        (None, None),  # Case 1: Test for document UUID
        (5, "5"),  # Case 2: Test for page UUID
    ],
)
def test_generates_correct_and_valid_uuid(base_data, page_num, expected_page_str):
    """Tests if the model generates the correct, expected UUID
    for both document-level and page-level inputs.
    """
    namespace_uuid = MOCK_NAMESPACE_OBJ

    norm_filename = str(base_data["source_file_name"] or "").strip().lower()
    norm_corr_type = str(base_data["correspondence_type"] or "").strip().lower()
    norm_case_ref = str(base_data["case_ref"] or "").strip().lower()

    data_parts = [norm_filename, norm_corr_type, norm_case_ref]
    if expected_page_str:
        data_parts.append(expected_page_str)

    data_string = "-".join(data_parts)
    expected_uuid = str(uuid.uuid5(namespace_uuid, data_string))

    # Add page_num to the data see the parameterization
    call_data = base_data.copy()
    if page_num is not None:
        call_data["page_num"] = page_num

    identifier = DocumentIdentifier(**call_data)

    actual_uuid = identifier.generate_uuid()

    assert actual_uuid == expected_uuid

    try:
        uuid.UUID(actual_uuid, version=5)
    except ValueError:
        pytest.fail(f"The generated string '{actual_uuid}' is not a valid UUID.")


@patch(
    "ingestion_pipeline.uuid_generators.document_uuid.NAMESPACE_DOC_INGESTION",
    MOCK_NAMESPACE_OBJ,
)
def test_is_deterministic(base_data):
    """Tests if the function produces the same UUID when called multiple times
    with the exact same inputs.
    """
    # Create two identical instances
    identifier1 = DocumentIdentifier(**base_data)
    identifier2 = DocumentIdentifier(**base_data)

    # Call the method on each
    uuid1 = identifier1.generate_uuid()
    uuid2 = identifier2.generate_uuid()

    assert uuid1 == uuid2


@patch(
    "ingestion_pipeline.uuid_generators.document_uuid.NAMESPACE_DOC_INGESTION",
    MOCK_NAMESPACE_OBJ,
)
def test_is_sensitive_to_input_changes(base_data):
    """Tests if changing any input parameter results in a different UUID."""
    # Create the base identifier and get its UUID
    base_identifier = DocumentIdentifier(**base_data)
    base_uuid = base_identifier.generate_uuid()

    # 1. Change source_file_name
    data_new_filename = base_data.copy()
    data_new_filename["source_file_name"] = "another_document.docx"
    identifier_new_filename = DocumentIdentifier(**data_new_filename)
    assert base_uuid != identifier_new_filename.generate_uuid()

    # 2. Change correspondence type
    data_new_corr_type = base_data.copy()
    data_new_corr_type["correspondence_type"] = "DIFFERENT"
    identifier_new_corr_type = DocumentIdentifier(**data_new_corr_type)
    assert base_uuid != identifier_new_corr_type.generate_uuid()

    # 3. Add a page number (testing document vs page)
    data_with_page = base_data.copy()
    data_with_page["page_num"] = 1
    identifier_with_page = DocumentIdentifier(**data_with_page)
    assert base_uuid != identifier_with_page.generate_uuid()
