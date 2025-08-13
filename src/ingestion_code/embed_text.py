import json
import logging
from typing import Any

from botocore.exceptions import ClientError

from ingestion_code.aws_clients import bedrock
from ingestion_code.config import settings
from ingestion_code.model import get_sentence_transformers_model

logger = logging.getLogger(__name__)


def embed_text_with_local_model(
    page_chunks: list[tuple[int, str, list[str]]],
) -> list[tuple[int, str, list[str], list[list[float]]]]:
    """
    Chunk extracted text for local embedding models.

    Args:
        pages (list[tuple[int, str]]): Page numbers and page text from a pdf.

    Returns:
        list[tuple[int, str, list[str]]]: A list of (page_number, page_text, chunks).
    """
    model = get_sentence_transformers_model()
    logger.info("Embedding text chunks.")
    extracted_data = []
    for page_number, page_text, chunks in page_chunks:
        try:
            embeddings = model.encode(
                chunks, batch_size=32, show_progress_bar=True
            ).tolist()
            extracted_data.append((page_number, page_text, chunks, embeddings))
        except Exception as e:
            logger.exception("Failed to embed chunks on page: %s", page_number)
            raise RuntimeError("Error with embedding page chunks") from e

    logger.info("Chunks embedded successfully.")
    return extracted_data


def embed_text_with_titan_model(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Embed a list of text chunks using the Amazon Titan model on Bedrock.

    Args:
        chunks: List of dicts, each with 'text' and 'metadata' fields.
        model_id: Bedrock model ID (default is Titan embedding model).

    Returns:
        List of dicts with 'text', 'embedding', and 'metadata' for each chunk.
    """
    logger.info("Starting embedding of text chunks with the Titan Bedrock model.")
    results = []

    for chunk in chunks:
        text = chunk["text"]

        # Prepare the payload
        payload = {"inputText": text}

        try:
            response = bedrock.invoke_model(
                modelId=settings.BEDROCK_EMBEDDING_MODEL_ID,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json",
            )
            # Parse the Titan V2 response
            body = json.loads(response["body"].read())
            embedding = body["embeddingsByType"]["float"]

            results.append(
                {"embedding": embedding, "text": text, "metadata": chunk["metadata"]}
            )

        except ClientError as e:
            page = chunk["metadata"]["page"]
            msg = "Bedrock InvokeModel failed for Titan embed on page %s: %r" % (
                page,
                e,
            )
            logger.exception(msg)
            raise

    logger.info("Chunks embedded successfully.")

    return results


def embed_query_with_titan_model(query: str):
    payload = {"inputText": query, "normalize": False}
    resp = bedrock.invoke_model(
        modelId=settings.BEDROCK_EMBEDDING_MODEL_ID,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json",
    )
    data = json.loads(resp["body"].read())
    return data["embeddingsByType"]["float"]


def embed_text_with_cohere_model(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Embed a list of text chunks using the Cohere Embed English v3 model on Bedrock.

    Args:
        chunks: List of dicts, each with 'text' and 'metadata'.

    Returns:
        List of dicts with keys:
          - 'embedding': List[float] (1024-dim vector)
          - 'text' : the chunk text
          - 'metadata': original metadata dict
    """
    results = []

    # Process in batches of up to _MAX_BATCH_SIZE texts
    _MAX_BATCH_SIZE = 96
    for i in range(0, len(chunks), 96):
        batch = chunks[i : i + _MAX_BATCH_SIZE]
        texts = [c["text"] for c in batch]

        payload = {
            "texts": texts,
            "input_type": "search_document",
            "truncate": "NONE",
        }

        try:
            response = bedrock.invoke_model(
                modelId=settings.BEDROCK_EMBEDDING_MODEL_ID,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json",
            )
            # Parse the response
            body = json.loads(response["body"].read())
            embeddings = body.get("embeddings")
            if not embeddings or not isinstance(embeddings, list):
                raise KeyError("No 'embeddings' key in response body: %r" % body)

            # Match each embedding to its chunk
            for chunk_dict, vector in zip(batch, embeddings):
                results.append(
                    {
                        "embedding": vector,
                        "text": chunk_dict["text"],
                        "metadata": chunk_dict["metadata"],
                    }
                )

        except ClientError as e:
            msg = "Bedrock InvokeModel failed for Cohere embed: %r" % e
            logger.exception(msg)
            raise

    logger.info("Chunks embedded successfully.")

    return results
