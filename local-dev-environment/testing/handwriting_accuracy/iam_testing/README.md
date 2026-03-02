# IAM Handwriting OCR Accuracy Testing

> **Status: In Development** — This testing module is under active development.

Evaluates AWS Textract OCR accuracy on handwritten text using the [IAM Handwriting Database](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database), with optional LLM augmentation via AWS Bedrock.

**Current Performance (1539 forms):**
| Metric | Baseline | Augmented (nova-pro + v2) | Improvement |
|--------|----------|---------------------------|-------------|
| WER | 13.26% | 4.41% | 67% reduction |
| Forms | — | 1352 improved, 77 worse, 110 unchanged | — |

## Quick Start

### Prerequisites

1. **AWS Credentials** with Textract and Bedrock access:
   ```bash
   export AWS_ACCESS_KEY_ID="..."
   export AWS_SECRET_ACCESS_KEY="..."
   export AWS_REGION="us-east-1"
   ```

2. **IAM Database**: Download from [IAM Database](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database) and extract to:
   ```
   data/
   ├── page_images/    # PNG images (e.g., a01-000u.png)
   └── xml/            # Ground truth XML files
   ```

3. **Dependencies**:
   ```bash
   cd local-dev-environment
   source .venv/bin/activate
   uv pip install jiwer
   ```

### Running Tests

```bash
# 1. Parse ground truth (one-time)
python -m iam_testing.ground_truth_parser

# 2. Test single form
python -m iam_testing.runners.single --form-id r06-121

# 3. Run baseline batch
python -m iam_testing.runners.batch --limit 10    # Test subset
python -m iam_testing.runners.batch               # All forms
python -m iam_testing.runners.batch --resume      # Resume interrupted

# 4. Apply LLM augmentation
python -m iam_testing.runners.augment --baseline-run 20260126_140000
python -m iam_testing.runners.augment --baseline-run 20260126_140000 --model nova-pro
```

## Custom Documents

For non-IAM documents:

1. Create `data/custom_ground_truth.jsonl`:
   ```json
   {"page_id": "page1", "image_path": "data/custom/page1.png", "gt_handwriting_text": "your ground truth"}
   ```

2. Run tests:
   ```bash
   python -m iam_testing.runners.custom --mode single --page-id page1
   python -m iam_testing.runners.custom --mode batch
   python -m iam_testing.runners.augment --baseline-run <RUN_ID> --dataset custom
   ```

## LLM Models & Prompts

### Models

| Model | Provider | Notes |
|-------|----------|-------|
| `nova-pro` | Amazon | Best quality, recommended |
| `nova-lite` | Amazon | Good balance, default |
| `nova-micro` | Amazon | Fastest, cheapest |
| `mistral-7b`, `mixtral-8x7b`, `mistral-large` | Mistral AI | Auto-enabled |
| `llama-3-8b`, `llama-3-70b`, `llama-3-1-8b`, `llama-3-1-70b` | Meta | Auto-enabled |
| `claude-3-haiku`, `claude-3-5-haiku`, `claude-3-sonnet`, `claude-3-5-sonnet` | Anthropic | Requires subscription |

### Prompts

| Version | WER (100-sample) | Notes |
|---------|------------------|-------|
| **v2** | **8.04%** | ⭐ Recommended, concise |
| v1 | 9.09% | Detailed guidelines |
| v4 | 9.26% | Few-shot, over-corrects |

All prompts include British English spelling, proper noun preservation, and short word handling.

## Text Normalization

Ensures fair comparison by removing differences OpenSearch ignores:

```python
def normalize_text(text: str) -> str:
    text = html.unescape(text)                        # &quot; → "
    text = text.replace("—", "-").replace("–", "-")   # Normalize dashes
    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)   # govern- ment → government
    text = re.sub(r'[^\w\s]', '', text)               # Remove punctuation
    return " ".join(text.lower().split())             # Lowercase + collapse whitespace
```

| Issue | Example | Result |
|-------|---------|--------|
| Line-break hyphens | `govern- ment` | `government` |
| HTML entities | `&quot;hello&quot;` | `hello` |
| Compound hyphens | `self-determination` | `selfdetermination` |

## Metrics

| Metric | Description |
|--------|-------------|
| **WER** | Word Error Rate (0.0 = perfect, 1.0 = all wrong) |
| **CER** | Character Error Rate |

## Package Structure

```
iam_testing/
├── runners/               # CLI entry points
│   ├── single.py          # Single-form test
│   ├── batch.py           # Batch baseline runner
│   ├── augment.py         # LLM augmentation
│   └── custom.py          # Custom document runner
├── llm/                   # LLM integration
│   ├── clients.py         # Bedrock model clients
│   └── prompt.py          # Versioned prompts
├── scoring.py             # WER/CER calculation
├── textract_ocr.py        # OCR processing
├── iam_filters.py         # Text normalization
└── ground_truth_parser.py # IAM XML parser
```

## Output Formats

**Baseline** (`data/batch_runs/{run_id}/score_results.jsonl`):
```json
{"form_id": "r06-121", "wer_handwriting": 0.0789, "cer_handwriting": 0.0236}
```

**Augmented** (`data/batch_runs/{run_id}/augmented/{model}_{prompt}_{mode}.jsonl`):
```json
{"form_id": "r06-121", "baseline_wer": 0.0789, "augmented_wer": 0.0395, "wer_improvement": 0.0394}
```

## Cost Estimates

| Operation | Per page | 1000 pages |
|-----------|----------|------------|
| Textract | ~$0.0015 | ~$1.50 |
| Nova Pro | ~$0.001 | ~$1.00 |
| Claude Sonnet | ~$0.005 | ~$5.00 |
