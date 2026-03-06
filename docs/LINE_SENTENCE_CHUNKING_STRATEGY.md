# Line-by-Line Sentence-Aware Chunker

## Overview

The `LineSentenceChunker` is a new deterministic chunking algorithm that operates directly on Textract LINE blocks (not LAYOUT blocks). It prioritizes sentence integrity and vertical proximity, addressing issues with the layout-based chunking approach.

## Key Features

1. **Direct LINE Block Processing**: Works with LINE blocks directly, bypassing layout detection
2. **Word-Based Counting**: Uses word count (not character count) for more natural chunking
3. **Sentence Boundary Awareness**: Closes chunks at sentence terminators (. ? !) after minimum word count
4. **Vertical Gap Detection**: Automatically breaks chunks when vertical spacing exceeds threshold
5. **Tight Bounding Boxes**: Generates accurate bounding boxes encompassing only the included lines
6. **Configurable**: All key parameters are configurable via environment variables or .env file

## References

- **Textract LINE Blocks**: [AWS Textract Documentation](https://docs.aws.amazon.com/textract/latest/dg/how-it-works-lines-words.html)
- **Textractor Library**: [Textractor GitHub](https://github.com/aws-samples/amazon-textract-textractor)
- **Current Implementation**: See `src/ingestion_pipeline/chunking/strategies/layout_text.py` for comparison


