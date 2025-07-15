import logging

from sentence_transformers import SentenceTransformer

from ingestion_code.config import settings

logger = logging.getLogger(__name__)

# --- Initialize Embedding Model ---
try:
    # print(f"Loading SentenceTransformer model: {MODEL_NAME}...")
    logger.info(f"Loading SentenceTransformer model: {settings.MODEL_NAME}...")
    model = SentenceTransformer(settings.MODEL_NAME)
    logger.info("Model loaded successfully.")
except Exception as e:
    logger.info(f"Error loading model: {e}")
    exit(1)
