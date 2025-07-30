import logging
from pathlib import Path

from ingestion_code.config import settings

logger = logging.getLogger(__name__)


def get_repo_root() -> Path:
    """Get the path of the root of the repository."""
    # 1. Walk up from this module’s file
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists():
            logger.debug("Found repo root at %s", parent)
            return parent

    # 2. If we get here, no .git folder was found
    message = f"Could not find .git in {current} or any of its parents."
    logger.error(message)
    raise RuntimeError(message)


def get_pdf_path(pdf_filename: str) -> Path:
    """Get the path of the pdf stored in the data directory given it's filename.

    Args:
        pdf_filename (str): pdf filename.

    Returns:
        Path: The path to the pdf file.
    """

    repo_root = get_repo_root()
    pdf_path = repo_root / settings.DATA_DIR / pdf_filename

    if not pdf_path.is_file() or not pdf_path.suffix.lower() == ".pdf":
        raise FileNotFoundError(f"Invalid PDF path: {pdf_path}")

    return pdf_path


def get_json_paths(folder_name: str) -> list[str]:
    """
    Return a list of all .json file paths in data/{folder_name}/extracted/
    """
    repo_root = get_repo_root()
    base_dir = repo_root / settings.DATA_DIR / folder_name / "extracted"
    # If you only want the top‐level files, otherwise use rglob
    return [str(p) for p in base_dir.glob("*.json") if p.is_file()]
