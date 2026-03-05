# Switching Between Chunkers in Pipeline

## Quick Switch Guide

### Current Setup: Layout-Based Chunker (Default)

The pipeline currently uses the **Layout-Based DocumentChunker** which processes LAYOUT blocks.

### How to Switch to Line-Based Chunker

**Option 1: Simple Switch (Uses Settings from .env)**

In [pipeline_builder.py](src/ingestion_pipeline/pipeline_builder.py), replace:

```python
# OLD: Layout-based
chunker = DocumentChunker(
    strategy_handlers=strategy_handlers,
    config=chunking_config,
)
```

With:

```python
# NEW: Line-based (uses settings automatically)
chunker = LineBasedDocumentChunker()
```

**Option 2: Custom Configuration**

```python
# NEW: Line-based with custom config
line_chunking_config = LineSentenceChunkingConfig(
    min_words=80,
    max_words=100,
    max_vertical_gap_ratio=0.05,
    debug=True,  # Enable detailed logging
)
chunker = LineBasedDocumentChunker(config=line_chunking_config)
```

## Step-by-Step Instructions

### 1. Open pipeline_builder.py

```bash
code src/ingestion_pipeline/pipeline_builder.py
```

### 2. Find the Chunker Section

Look for the section marked:

```python
# ========================================
# OPTION 1: Layout-Based Chunking (CURRENT)
# ========================================
```

### 3. Comment Out Layout-Based Chunker

```python
# ========================================
# OPTION 1: Layout-Based Chunking (CURRENT)
# ========================================
# layout_text_strategy = LayoutTextChunkingStrategy(chunking_config)
# ... (comment out all strategy setup)
# chunker = DocumentChunker(
#     strategy_handlers=strategy_handlers,
#     config=chunking_config,
# )
```

### 4. Uncomment Line-Based Chunker

```python
# ========================================
# OPTION 2: Line-Based Sentence Chunking (NEW)
# ========================================
chunker = LineBasedDocumentChunker()  # Uses settings automatically
```

### 5. Save and Test

```bash
# Verify imports work
PYTHONPATH=src python3 -c "from ingestion_pipeline.pipeline_builder import build_pipeline; print('✓ OK')"

# Run your pipeline
python src/ingestion_pipeline/runner.py
```

## Configuration via .env

Both chunkers respect `.env` settings:

### Layout-Based Chunker Settings
```bash
MAXIMUM_CHUNK_SIZE=80
Y_TOLERANCE_RATIO=0.5
MAX_VERTICAL_GAP=0.5
LINE_CHUNK_CHAR_LIMIT=300
```

### Line-Based Chunker Settings
```bash
SENTENCE_CHUNKER_MIN_WORDS=80
SENTENCE_CHUNKER_MAX_WORDS=100
SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO=0.05
```

## Comparison

| Aspect | Layout-Based (Old) | Line-Based (New) |
|--------|-------------------|------------------|
| **Input** | LAYOUT blocks | LINE blocks |
| **Strategies** | Multiple (text, table, list, key-value) | Single (sentence-aware) |
| **Size Metric** | Character count | **Word count** |
| **Sentence Aware** | No | **Yes (. ? !)** |
| **Merging** | ChunkMerger applies | **No merging** |
| **Bounding Boxes** | Can span layouts | **Tight line boxes** |
| **Vertical Gaps** | Not detected | **Auto-detected** |

## A/B Testing Both Chunkers

To compare results, you can run both:

```python
def compare_chunkers(doc, metadata):
    """Compare both chunking approaches."""
    # Layout-based
    layout_chunker = DocumentChunker(strategy_handlers, chunking_config)
    layout_result = layout_chunker.chunk(doc, metadata)
    
    # Line-based
    line_chunker = LineBasedDocumentChunker()
    line_result = line_chunker.chunk(doc, metadata)
    
    print(f"Layout-based: {len(layout_result.chunks)} chunks")
    print(f"Line-based: {len(line_result.chunks)} chunks")
    
    return {
        "layout": layout_result,
        "line": line_result,
    }
```

## Troubleshooting

### Issue: Import Error

```python
# Make sure imports are added:
from ingestion_pipeline.chunking.line_based_document_chunker import LineBasedDocumentChunker
from ingestion_pipeline.chunking.layout.strategies.line_sentence_chunker import LineSentenceChunkingConfig
```

### Issue: page.lines is None

The line-based chunker requires `page.lines` to be populated. If you see warnings about missing lines:

1. Check that Textractor properly populates page.lines
2. Verify your Textract response includes LINE blocks
3. Consider extracting lines from raw response (see examples)

### Issue: Want More Debug Info

```python
# Enable debug logging
config = LineSentenceChunkingConfig(
    min_words=80,
    max_words=100,
    max_vertical_gap_ratio=0.05,
    debug=True,  # <-- Enable this
)
chunker = LineBasedDocumentChunker(config=config)
```

## Rollback

To switch back to layout-based chunking:

1. Uncomment the layout-based section
2. Comment out the line-based section
3. Restart your pipeline

## Next Steps

1. **Test**: Run on sample documents
2. **Compare**: Check chunk quality vs layout-based
3. **Tune**: Adjust min/max words if needed
4. **Monitor**: Watch for any edge cases
5. **Commit**: Once satisfied, make it permanent

---

**Ready to switch!** Just uncomment the line-based chunker in `pipeline_builder.py`.
