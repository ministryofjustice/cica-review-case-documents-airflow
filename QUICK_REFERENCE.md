# Quick Reference: Line-by-Line Sentence Chunker

## 🚀 Quick Start

```python
from ingestion_pipeline.chunking.strategies.line_sentence_chunker import LineSentenceChunker

# 1. Create chunker
chunker = LineSentenceChunker()

# 2. Chunk a page
chunks = chunker.chunk_page(
    lines=page.lines,              # List of LINE blocks
    page_number=page.page_num,     # Page number (1-indexed)
    metadata=metadata,             # DocumentMetadata object
    chunk_index_start=0,           # Starting chunk index
)

# 3. Use chunks
for chunk in chunks:
    print(f"Chunk {chunk.chunk_index}: {chunk.word_count} words")
    print(f"Text: {chunk.chunk_text[:50]}...")
    print(f"BBox: ({chunk.bounding_box.left}, {chunk.bounding_box.top})")
```

## 📝 Configuration

### Via .env file (Recommended)
```bash
SENTENCE_CHUNKER_MIN_WORDS=80
SENTENCE_CHUNKER_MAX_WORDS=100
SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO=0.05
```

### Programmatic
```python
from ingestion_pipeline.chunking.strategies.line_sentence_chunker import (
    LineSentenceChunkingConfig
)

config = LineSentenceChunkingConfig(
    min_words=80,                    # Min words before sentence break
    max_words=100,                   # Force break at this limit
    max_vertical_gap_ratio=0.05,    # Gap threshold (% of page height)
    debug=False,                     # Enable debug logging
)
chunker = LineSentenceChunker(config=config)
```

## 🎯 Algorithm in 4 Rules

1. **Accumulate** lines sequentially (sorted by vertical position)
2. **Check gap**: If vertical_gap > threshold → **force break**
3. **Check max**: If words + new_line > max_words → **force break**
4. **Check sentence**: If words ≥ min_words AND line ends with [.?!] → **close chunk**

## 🔧 Common Adjustments

### Chunks too large?
```python
config = LineSentenceChunkingConfig(max_words=75)  # Reduce from 100
```

### Chunks breaking mid-paragraph?
```python
config = LineSentenceChunkingConfig(max_vertical_gap_ratio=0.08)  # More tolerant
```

### Too many small chunks?
```python
config = LineSentenceChunkingConfig(min_words=100)  # Increase from 80
```

### Enable debug logging
```python
config = LineSentenceChunkingConfig(debug=True)
```

## 📦 Output Structure

Each chunk is a `DocumentChunk` with:

```python
chunk.chunk_id                # Unique UUID
chunk.chunk_text              # Combined text with spaces
chunk.chunk_index             # Sequential index
chunk.page_number             # Page number
chunk.word_count              # Computed word count
chunk.character_count         # Computed character count
chunk.bounding_box            # DocumentBoundingBox
  .left                       # X coordinate (0-1)
  .top                        # Y coordinate (0-1)
  .width                      # Width (0-1)
  .height                     # Height (0-1)
  .right                      # Computed: left + width
  .bottom                     # Computed: top + height
chunk.chunk_type              # "LINE_SENTENCE_CHUNK"
chunk.confidence              # Average confidence (default: 95.0)
```

## 🧪 Testing

```bash
# Verify installation
PYTHONPATH=src python3 -c "from ingestion_pipeline.chunking.strategies.line_sentence_chunker import LineSentenceChunker; print('OK')"

# Run tests
pytest tests/chunking/test_line_sentence_chunker.py -v
```

## 📚 Full Documentation

- **Complete Guide**: `docs/LINE_SENTENCE_CHUNKER.md`
- **Examples**: `examples/line_sentence_chunker_example.py`
- **Implementation Summary**: `IMPLEMENTATION_SUMMARY.md`

## 💡 Key Differences from Layout-Based Chunking

| Feature | Layout-Based (Old) | Line-Based (New) |
|---------|-------------------|------------------|
| Input | LAYOUT blocks | LINE blocks |
| Sizing | Character-based | **Word-based** |
| Sentence Awareness | No | **Yes (. ? !)** |
| Bounding Box | Combined layouts | **Tight line boxes** |
| Vertical Gaps | No detection | **Automatic detection** |

## ⚠️ Important Notes

1. **Requires `page.lines`**: Ensure your Textractor Document has `page.lines` populated
   - If not available, see `example_extracting_lines_from_raw_response()` in examples

2. **LINE blocks sorted**: Algorithm sorts by `bbox.y` automatically

3. **Word count**: Uses `.split()` (whitespace-based counting)

4. **Sentence detection**: Simple check for [.?!] at end of line
   - Doesn't handle abbreviations like "Dr." yet
   - Enhancement opportunity for future

5. **Bounding boxes**: Minimal enclosing rectangle using `combine_bounding_boxes()`

## 🆘 Troubleshooting

```python
# Problem: page.lines is None or empty
# Solution: Extract from raw_response
from examples.line_sentence_chunker_example import example_extracting_lines_from_raw_response
lines = example_extracting_lines_from_raw_response(doc.response, page.page_num)

# Problem: Chunks too inconsistent
# Solution: Enable debug logging
config = LineSentenceChunkingConfig(debug=True)

# Problem: Import errors
# Solution: Set PYTHONPATH
export PYTHONPATH=src
```

## 🎓 Example: Process Full Document

```python
def process_document(doc, metadata):
    """Process entire document with line-based chunking."""
    from ingestion_pipeline.chunking.strategies.line_sentence_chunker import LineSentenceChunker
    
    chunker = LineSentenceChunker()
    all_chunks = []
    chunk_index = 0
    
    for page in doc.pages:
        page_chunks = chunker.chunk_page(
            lines=page.lines,
            page_number=page.page_num,
            metadata=metadata,
            chunk_index_start=chunk_index,
        )
        all_chunks.extend(page_chunks)
        chunk_index += len(page_chunks)
    
    return all_chunks  # Returns List[DocumentChunk]
```

---

**That's it!** You now have a working line-by-line sentence-aware chunker ready to use.
