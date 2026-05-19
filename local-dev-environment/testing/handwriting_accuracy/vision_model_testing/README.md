# Vision Model Testing

Handwriting extraction from document page images using vision LLMs. Supports evaluation (WER/CER against ground truth) and exposes the `LiteLLMVisionClient` that is intended for integration into the production document processing pipeline.

---

## Package structure

```
vision_model_testing/
  llm/
    clients.py          # NovaVisionClient, ClaudeVisionClient, LiteLLMVisionClient
    base.py             # Abstract BaseVisionClient, retry logic
    prompt.py           # Evaluation prompt variants (v1.5, v1.5-mm, v1.5-mm-struct2)
    production_prompt.py  # Production prompt (v1.0-prod) — full-page transcription
    response.py         # VisionResponse dataclass
    __init__.py         # get_vision_client() factory, VISION_CLIENT_REGISTRY
  runners/
    vision.py           # Batch WER/CER evaluation runner
    vision_augment.py   # Vision + LLM augmentation runner
    vision_keyword.py   # Keyword recall runner (degraded docs)
    utils.py            # Shared runner utilities
  scoring.py            # WER/CER scoring helpers
  config.py             # Re-exports ingestion pipeline settings
```

---

## Supported models

| Model shortname | Provider | Access |
|---|---|---|
| `bedrock-claude-opus-4-6` | Anthropic via Bedrock | LiteLLM gateway (`OPENAI_KEY`) |
| `bedrock-claude-sonnet-4-6` | Anthropic via Bedrock | LiteLLM gateway (`OPENAI_KEY`) |
| `bedrock-claude-opus-4-5` | Anthropic via Bedrock | LiteLLM gateway (`OPENAI_KEY`) |
| `bedrock-claude-sonnet-4-5` | Anthropic via Bedrock | LiteLLM gateway (`OPENAI_KEY`) |
| `nova-pro` | Amazon Nova via Bedrock | Direct Bedrock (`AWS_*` env vars) |
| `nova-lite` | Amazon Nova via Bedrock | Direct Bedrock (`AWS_*` env vars) |
| `claude-3-5-sonnet` | Anthropic via Bedrock | Direct Bedrock (`AWS_*` env vars) |

**Recommended for evaluation and production:** `bedrock-claude-opus-4-6` via the LiteLLM gateway.

The `OPENAI_KEY` for the LiteLLM gateway is held by Max B and Jennifer. If it is lost, Jeremy Collins can provide a new one.

---

## Prompts

### Evaluation prompts (`llm/prompt.py`)

Used during evaluation runs to measure WER/CER against ground truth. These prompts target **handwriting-only** output — they suppress pre-printed form content.

| Version | Description | Status |
|---|---|---|
| `v1` – `v1.4` | Iterative development versions | Superseded |
| `v1.5` | Direct vision — handwriting only, form chrome suppressed | Active (Method 2) |
| `v1.5-mm`      | Multimodal flat OCR hint + crossed-out exclusion | **Best evaluated (Method 3)** |
| `v1.5-mm-struct2` | Multimodal structured OCR table, all words as context | Active (Method 4) |

### Production prompt (`llm/production_prompt.py`)

`v1.0-prod` transcribes **all** visible text on the page (printed and handwritten). This is appropriate for production where downstream chunking/indexing needs the full page content, not just the handwritten portion.

```python
from vision_model_testing.llm.production_prompt import get_production_prompt
prompt = get_production_prompt("v1.0-prod")
```

---

## Ground truth format

JSONL file with one record per page:

```json
{"page_id": "case2page3", "image_path": "images/case2/page3.png", "gt_handwriting_text": "..."}
```

---

## Running evaluations

All runners are invoked from the `local-dev-environment/` directory with the `testing/handwriting_accuracy` package on `PYTHONPATH`.

```bash
cd local-dev-environment
source .venv/bin/activate
export PYTHONPATH=testing/handwriting_accuracy
```

### Batch WER/CER evaluation

```bash
python -m vision_model_testing.runners.vision \
    --ground-truth testing/handwriting_accuracy/data/case_documents_ground_truth.jsonl \
    --model bedrock-claude-opus-4-6 \
    --prompt v1.5-mm
```

Single page:
```bash
python -m vision_model_testing.runners.vision \
    --ground-truth testing/handwriting_accuracy/data/case_documents_ground_truth.jsonl \
    --model bedrock-claude-opus-4-6 \
    --prompt v1.5-mm \
    --page-id case18page23
```

### Vision + LLM augmentation

```bash
python -m vision_model_testing.runners.vision_augment \
    --baseline-run 20260225_120000 \
    --vision-model bedrock-claude-opus-4-6 \
    --vision-prompt v1.5-mm \
    --llm-model bedrock-claude-sonnet-4-6 \
    --llm-prompt v2.6
```

### Keyword recall (degraded documents)

```bash
python -m vision_model_testing.runners.vision_keyword \
    --ground-truth testing/handwriting_accuracy/data/case_documents_keywords.jsonl \
    --model bedrock-claude-opus-4-6
```

---

## Production pipeline integration

For the document processing pipeline, the important boundary is where the multimodal output would be stored.

- The multimodal response should be written into the chunk text that is ultimately indexed in OpenSearch.
- In the current ingestion pipeline this corresponds to the `chunk_text` field on `DocumentChunk`.
- The chunk geometry and positional metadata should still come from the existing Textract-based chunking pipeline; the vision model output replaces or augments only the text content.

In other words: multimodal extraction would not introduce a new storage object in the pipeline. Its output would land in the same place the pipeline already stores extracted chunk text before indexing.
