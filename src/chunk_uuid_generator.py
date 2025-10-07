import uuid

from src.config import settings

CHUNK_INDEX_UUID_NAMESPACE = settings.CHUNK_INDEX_UUID_NAMESPACE


def create_guid_hash(filename, correspondence_type, received_date, case_ref):
    """
    Creates a Version 5 UUID from the given parameters.

    Args:
        filename (str): The name of the source file.
        correspondence_type (str): The correspondence type code.
        received_date (datetime.date): The date the document was received.
        case_ref (str): The case reference number.

    Returns:
        str: A standard UUID string in the format "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx".
    """
    # Create a unique namespace for your application
    # This is a fixed UUID that you define once for your system.
    # TODO This should be a UUID that is generated, is stored as a secret and is kept constant
    NAMESPACE_DOC_INGESTION = uuid.UUID(CHUNK_INDEX_UUID_NAMESPACE)

    data_string = f"{filename}-{correspondence_type}-{received_date.isoformat()}-{case_ref}"

    # Generate a UUID based on the namespace and the data string
    # uuid.uuid5() uses a SHA-1 hash internally.
    return str(uuid.uuid5(NAMESPACE_DOC_INGESTION, data_string))
