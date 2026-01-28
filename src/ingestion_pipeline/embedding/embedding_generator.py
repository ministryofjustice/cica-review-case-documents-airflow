"""Embedding generator using Amazon Bedrock models."""

import json
import logging

import boto3

from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)
# Set the model ID, e.g., Titan Text Embeddings V2.
model_id = settings.BEDROCK_EMBEDDING_MODEL_ID


class EmbeddingError(Exception):
    """Custom exception for embedding generation failures."""


class EmbeddingGenerator:
    """Generates embeddings using Amazon Bedrock models."""

    def __init__(self, model_id: str):
        """Initializes the EmbeddingGenerator with the specified model ID.

        Args:
            model_id (str): The ID of the Bedrock model to use for generating embeddings.
        """
        self.model_id = model_id
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
            aws_session_token=getattr(settings, "AWS_MOD_PLATFORM_SESSION_TOKEN", None),  # Optional
        )

    def generate_embedding(self, text: str) -> list[float]:
        """Generates an embedding for the given text.

        Args:
            text: The input text to generate an embedding for.

        Returns:
            A list of floats representing the embedding.
        """
        try:
            logging.debug(f"Generating embedding for text: {text}")
            native_request = {"inputText": text}
            request = json.dumps(native_request)

            response = self.client.invoke_model(modelId=self.model_id, body=request)
            model_response = json.loads(response["body"].read())

            return model_response["embedding"]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise EmbeddingError(f"Failed to generate embeddings for chunks: {str(e)}") from e
