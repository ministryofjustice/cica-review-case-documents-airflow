import logging
from pathlib import Path

from ingestion_code.config import settings

logger = logging.getLogger(__name__)


def get_repo_root() -> Path:
    try:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / ".git").exists():
                logger.info(f"The root of the repo is {parent}")
                return parent
    except NameError:
        # __file__ is not defined (e.g. in a Jupyter notebook)
        return Path.cwd()
    raise RuntimeError("Could not find the project root.")


def get_pdf_path(pdf_filename: str) -> Path:
    repo_root = get_repo_root()
    pdf_path = repo_root / settings.DATA_DIR / pdf_filename

    if not pdf_path.is_file() or not pdf_path.suffix.lower() == ".pdf":
        raise FileNotFoundError(f"Invalid PDF path: {pdf_path}")

    return pdf_path
