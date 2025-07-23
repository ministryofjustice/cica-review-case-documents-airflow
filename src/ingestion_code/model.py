import logging

from sentence_transformers import SentenceTransformer

from ingestion_code.config import settings

logger = logging.getLogger(__name__)

# --- Initialize Embedding Model ---


def get_sentence_transformers_model() -> SentenceTransformer:
    """Load a SentenceTransformer model."""
    try:
        logger.info("Loading SentenceTransformer model: %s", settings.MODEL_NAME)
        model = SentenceTransformer(settings.MODEL_NAME)
        logger.info("Model %s loaded successfully.", settings.MODEL_NAME)
        return model
    except Exception as e:
        logger.exception(
            "Failed to load SentenceTransformer model %s", settings.MODEL_NAME
        )
        raise RuntimeError(
            f"Error loading embedding model '{settings.MODEL_NAME}'"
        ) from e
