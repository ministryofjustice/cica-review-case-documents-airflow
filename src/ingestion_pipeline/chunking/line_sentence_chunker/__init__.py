"""Line-by-line sentence-aware chunking package."""

from ingestion_pipeline.chunking.strategies.line_sentence_chunker.chunker import LineSentenceChunker
from ingestion_pipeline.chunking.strategies.line_sentence_chunker.config import LineSentenceChunkingConfig

__all__ = ["LineSentenceChunker", "LineSentenceChunkingConfig"]
