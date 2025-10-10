import datetime
import uuid
from unittest.mock import patch

import pytest

from ingestion_pipeline.uuid_generators.document_uuid import generate_uuid


@pytest.fixture
def test_data():
    """Provides common data for the UUID generation tests."""
    return {
        "filename": "source_document.pdf",
        "correspondence_type": "TC19",
        "received_date": datetime.date(2025, 10, 6),
        "case_ref": "25-111111",
        "mock_namespace": "1b671a64-40d5-491e-99b0-da01ff1f3341",
    }


@patch(
    "ingestion_pipeline.uuid_generators.document_uuid.CHUNK_INDEX_UUID_NAMESPACE",
    "1b671a64-40d5-491e-99b0-da01ff1f3341",
)
def test_generates_correct_and_valid_uuid(test_data):
    """
    Tests if the function generates the correct, expected UUID for a given set of inputs.
    """
    namespace_uuid = uuid.UUID(test_data["mock_namespace"])
    data_string = (
        f"{test_data['filename']}-{test_data['correspondence_type']}-"
        f"{test_data['received_date'].isoformat()}-{test_data['case_ref']}"
    )
    expected_uuid = str(uuid.uuid5(namespace_uuid, data_string))

    actual_uuid = generate_uuid(
        test_data["filename"],
        test_data["correspondence_type"],
        test_data["received_date"],
        test_data["case_ref"],
    )

    assert actual_uuid == expected_uuid

    try:
        uuid.UUID(actual_uuid, version=5)
    except ValueError:
        pytest.fail(f"The generated string '{actual_uuid}' is not a valid UUID.")


@patch(
    "ingestion_pipeline.uuid_generators.document_uuid.CHUNK_INDEX_UUID_NAMESPACE",
    "1b671a64-40d5-491e-99b0-da01ff1f3341",
)
def test_is_deterministic(test_data):
    """
    Tests if the function produces the same UUID when called multiple times
    with the exact same inputs.
    """
    uuid1 = generate_uuid(
        test_data["filename"],
        test_data["correspondence_type"],
        test_data["received_date"],
        test_data["case_ref"],
    )
    uuid2 = generate_uuid(
        test_data["filename"],
        test_data["correspondence_type"],
        test_data["received_date"],
        test_data["case_ref"],
    )

    assert uuid1 == uuid2


@patch(
    "ingestion_pipeline.uuid_generators.document_uuid.CHUNK_INDEX_UUID_NAMESPACE",
    "1b671a64-40d5-491e-99b0-da01ff1f3341",
)
def test_is_sensitive_to_input_changes(test_data):
    """
    Tests if changing any input parameter results in a different UUID.
    """
    base_uuid = generate_uuid(
        test_data["filename"],
        test_data["correspondence_type"],
        test_data["received_date"],
        test_data["case_ref"],
    )

    # 1. Change filename
    uuid_new_filename = generate_uuid(
        "another_document.docx",
        test_data["correspondence_type"],
        test_data["received_date"],
        test_data["case_ref"],
    )
    assert base_uuid != uuid_new_filename

    # 2. Change correspondence type
    uuid_new_corr_type = generate_uuid(
        test_data["filename"], "DIFFERENT", test_data["received_date"], test_data["case_ref"]
    )
    assert base_uuid != uuid_new_corr_type

    # 3. Change received date
    uuid_new_date = generate_uuid(
        test_data["filename"],
        test_data["correspondence_type"],
        datetime.date(2025, 10, 7),
        test_data["case_ref"],
    )
    assert base_uuid != uuid_new_date

    # 4. Change case reference
    uuid_new_case_ref = generate_uuid(
        test_data["filename"],
        test_data["correspondence_type"],
        test_data["received_date"],
        "25-999999",
    )
    assert base_uuid != uuid_new_case_ref
