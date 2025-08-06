from pathlib import Path
from unittest.mock import patch

import pytest
from ingestion_code.utils import get_pdf_path, get_repo_root

# --- Test get_repo_root ---


def test_get_repo_root_finds_git(monkeypatch):
    """Test finding the repo root with .git directory."""

    fake_file = Path("/home/user/project/module/my_module.py")

    # Make Path.resolve() always return our fake path
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: fake_file)
    # Patch __file__ to fake path
    monkeypatch.setattr("ingestion_code.paths.__file__", str(fake_file))

    # Patch Path.exists to simulate .git folder
    def fake_exists(self):
        # If checking for .git in /home/user/project
        return str(self) == "/home/user/project/.git"

    monkeypatch.setattr(Path, "exists", fake_exists)

    root = get_repo_root()
    assert root == Path("/home/user/project")


def test_get_repo_root_raises(monkeypatch):
    """Test raises RuntimeError if no .git found."""

    fake_file = Path("/fake/path/to/file.py")
    monkeypatch.setattr("ingestion_code.paths.__file__", str(fake_file))

    # .git never exists
    monkeypatch.setattr(Path, "exists", lambda self: False)
    with pytest.raises(RuntimeError):
        get_repo_root()


# --- Test get_pdf_path ---


@patch("ingestion_code.paths.get_repo_root")
@patch("ingestion_code.config.settings")
def test_get_pdf_path_valid(mock_settings, mock_get_repo_root, tmp_path):
    """Test get_pdf_path returns valid path."""

    # Simulate repo root and settings
    mock_get_repo_root.return_value = tmp_path
    mock_settings.DATA_DIR = "data"

    # Create test pdf file
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pdf_file = data_dir / "test.pdf"
    pdf_file.write_bytes(b"dummy")

    result = get_pdf_path("test.pdf")
    assert result == pdf_file


@patch("ingestion_code.paths.get_repo_root")
@patch("ingestion_code.config.settings")
def test_get_pdf_path_not_pdf(mock_settings, mock_get_repo_root, tmp_path):
    """Test get_pdf_path raises FileNotFoundError for non-pdf extension."""

    mock_get_repo_root.return_value = tmp_path
    mock_settings.DATA_DIR = "data"

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    fake_file = data_dir / "not_a_pdf.txt"
    fake_file.write_text("dummy")

    with pytest.raises(FileNotFoundError):
        get_pdf_path("not_a_pdf.txt")


@patch("ingestion_code.paths.get_repo_root")
@patch("ingestion_code.config.settings")
def test_get_pdf_path_file_not_exist(mock_settings, mock_get_repo_root, tmp_path):
    """Test get_pdf_path raises FileNotFoundError if file doesn't exist."""

    mock_get_repo_root.return_value = tmp_path
    mock_settings.DATA_DIR = "data"

    with pytest.raises(FileNotFoundError):
        get_pdf_path("missing.pdf")
