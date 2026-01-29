import pytest

from ingestion_pipeline.page_processor.image_converter import ImageConverter


def test_pdf_to_images_valid(monkeypatch):
    # Arrange
    converter = ImageConverter()
    dummy_pdf_bytes = b"%PDF-1.4..."  # Minimal valid PDF header (for real test, use a real PDF or mock)
    dummy_image = object()

    # Patch convert_from_bytes to return a dummy list
    monkeypatch.setattr(
        "ingestion_pipeline.page_processor.image_converter.convert_from_bytes",
        lambda pdf_bytes: [dummy_image, dummy_image],
    )

    # Act
    images = converter.pdf_to_images(dummy_pdf_bytes)

    # Assert
    assert isinstance(images, list)
    assert len(images) == 2
    assert all(img is dummy_image for img in images)


def test_pdf_to_images_invalid(monkeypatch):
    # Arrange
    converter = ImageConverter()
    invalid_pdf_bytes = b"not a pdf"

    # Patch convert_from_bytes to raise an exception
    def raise_pdf_error(pdf_bytes):
        raise Exception("PDFPageCountError")

    monkeypatch.setattr("ingestion_pipeline.page_processor.image_converter.convert_from_bytes", raise_pdf_error)

    # Act & Assert
    with pytest.raises(Exception) as excinfo:
        converter.pdf_to_images(invalid_pdf_bytes)
    assert "PDFPageCountError" in str(excinfo.value)
