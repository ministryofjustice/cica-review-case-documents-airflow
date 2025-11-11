"""Package initialization for ingestion_pipeline."""
# TODO move to main once we have an orchestrator

from pathlib import Path

from dotenv import load_dotenv

# Load .env at package initialization
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

if ENV_FILE_PATH.exists():
    # Don't override existing env vars; this ensures that any environment variables already set in the system
    # (e.g., by the OS or deployment platform) are preserved and not overwritten by values from the .env file.
    # which should not exist in production environments.
    load_dotenv(ENV_FILE_PATH, override=False)
