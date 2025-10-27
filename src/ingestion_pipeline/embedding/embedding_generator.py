import json
import logging

import boto3

from ingestion_pipeline.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Set the model ID, e.g., Titan Text Embeddings V2.
model_id = settings.BEDROCK_EMBEDDING_MODEL_ID


class EmbeddingGenerator:
    """Generates embeddings using Amazon Bedrock models."""

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)

    def generate_embedding(self, text: str) -> list[float]:
        """Generates an embedding for the given text.

        Args:
            text: The input text to generate an embedding for.

        Returns:
            A list of floats representing the embedding.
        """
        logging.info(f"Generating embedding for text: {text}")
        native_request = {"inputText": text}
        request = json.dumps(native_request)

        response = self.client.invoke_model(modelId=self.model_id, body=request)
        model_response = json.loads(response["body"].read())

        return model_response["embedding"]
