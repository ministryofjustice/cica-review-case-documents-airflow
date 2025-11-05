"""Package initialization for ingestion_pipeline."""

from pathlib import Path

from dotenv import load_dotenv

# Load .env at package initialization
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

if ENV_FILE_PATH.exists():
    load_dotenv(ENV_FILE_PATH, override=False)  # Don't override existing env vars
