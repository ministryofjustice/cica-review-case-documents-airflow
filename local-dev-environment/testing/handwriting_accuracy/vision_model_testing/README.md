# Vision Model Testing

Direct image-to-text handwriting extraction using AWS Bedrock vision models.

## Supported Models

| Model | Provider | Notes |
|-------|----------|-------|
| `nova-pro` | Amazon | Best quality (default) |
| `nova-lite` | Amazon | Faster |
| `claude-3-5-sonnet` | Anthropic | Requires Bedrock access |

## Ground Truth Format

JSONL file with one entry per page:
```json
{"page_id": "page1", "image_path": "data/custom/page1.png", "gt_handwriting_text": "..."}
```

## Usage

### Vision Extraction
```bash
# Basic run
python -m vision_model_testing.runners.vision \
    --ground-truth data/custom/ground_truth.jsonl \
    --model nova-pro

# Single page with custom prompt
python -m vision_model_testing.runners.vision \
    --ground-truth data/custom/ground_truth.jsonl \
    --model nova-pro \
    --prompt v1.1 \
    --page-id page1
```

### Vision + LLM Augmentation
```bash
python -m vision_model_testing.runners.vision_augment \
    --baseline-run 20260225_120000 \
    --vision-model nova-pro \
    --vision-prompt v1 \
    --llm-model nova-lite \
    --llm-prompt v2.4
```

## Output

Results saved to `data/vision_results/<timestamp>/`:
- `results.jsonl` - Per-page extraction and scores
- `summary.json` - Aggregate WER/CER metrics

## Prompts

Available prompt versions: `v1`, `v1.1`, `v1.2`, `v1.3`

View prompts:
```python
from vision_model_testing.llm.prompt import VISION_PROMPTS
print(VISION_PROMPTS.keys())
```
