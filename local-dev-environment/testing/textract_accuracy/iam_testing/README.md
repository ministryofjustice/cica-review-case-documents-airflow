# IAM Handwriting OCR Accuracy Testing

<<<<<<< HEAD
<<<<<<< HEAD
Evaluates AWS Textract OCR accuracy on handwritten text using the [IAM Handwriting Database](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database), with LLM augmentation to improve results. Further spot testing to be done on speicifc

**Current Performance (1539 forms):**
- Baseline WER: 13.26% | Augmented WER: 4.41% (with nova-pro + v2 prompt)
- Improvement: 8.85 percentage points (67% relative reduction)
- Forms improved: 1352 | Worse: 77 | Unchanged: 110

## Overview

This pipeline processes handwritten documents through:
1. AWS Textract OCR with printed/handwriting text separation
2. Dataset-specific filtering (headers, footers, signatures)
3. Text normalization for fair comparison
4. WER/CER calculation against ground truth
5. Optional LLM correction via AWS Bedrock

### Metrics
=======
> **Status: In Development** — This testing module is under active development and not yet production-ready.
=======
Evaluates AWS Textract OCR accuracy on handwritten text using the [IAM Handwriting Database](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database), with LLM augmentation to improve results. Further spot testing to be done on speicifc
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

**Current Performance (1539 forms):**
- Baseline WER: 13.26% | Augmented WER: 4.41% (with nova-pro + v2 prompt)
- Improvement: 8.85 percentage points (67% relative reduction)
- Forms improved: 1352 | Worse: 77 | Unchanged: 110

## Overview

This pipeline processes handwritten documents through:
1. AWS Textract OCR with printed/handwriting text separation
2. Dataset-specific filtering (headers, footers, signatures)
3. Text normalization for fair comparison
4. WER/CER calculation against ground truth
5. Optional LLM correction via AWS Bedrock

<<<<<<< HEAD
## Metrics
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
### Metrics
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

| Metric | Description |
|--------|-------------|
| **WER** (Word Error Rate) | Fraction of words incorrect (0.0 = perfect, 1.0 = all wrong) |
| **CER** (Character Error Rate) | Fraction of characters incorrect |

<<<<<<< HEAD
<<<<<<< HEAD
### Text Normalization

All text undergoes identical normalization before scoring to ensure WER improvements translate to real search quality. The pipeline removes differences that OpenSearch's standard analyzer would ignore:

```python
def normalize_text(text: str) -> str:
    text = html.unescape(text)              # &quot; → "
    text = text.replace("—", "-").replace("–", "-")  # Normalize dash variants
    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)  # govern- ment → government
    text = re.sub(r'[^\w\s]', '', text)     # Remove all punctuation (including hyphens)
    return " ".join(text.lower().split())   # Lowercase + collapse whitespace
```

**Why these normalizations?** They ensure fair comparison by removing differences that don't affect search quality:
- **Line-break hyphens**: "govern- ment" → "government" (247 forms had these artifacts)
- **All hyphens removed**: After punctuation stripping, both "self-determination" and "selfdetermination" become "selfdetermination" (ensures consistent matching regardless of whether OCR preserves hyphens)
- **Case/whitespace**: Lowercase and collapse whitespace for consistent comparison

## Prerequisites

1. **Navigate to local dev environment**:
   ```bash
   cd local-dev-environment/testing/textract_accuracy
   source ../../.venv/bin/activate  # Activate virtual environment
   ```

2. **AWS Credentials** with Textract and Bedrock access:
   ```bash
   export AWS_MOD_PLATFORM_ACCESS_KEY_ID="..."
   export AWS_MOD_PLATFORM_SECRET_ACCESS_KEY="..."
<<<<<<< HEAD
   export AWS_REGION="us-east-1"
   ```
   Or add to `.env` file in project root.

3. **IAM Handwriting Database**: Download from [IAM Database](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database) and extract to:
   ```
   data/
   ├── page_images/    # PNG images (e.g., a01-000u.png)
   └── xml/            # Ground truth XML files
   ```

4. **Python dependencies**:
=======
## Quick Start
=======
### Text Normalization
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

All text undergoes identical normalization before scoring to ensure WER improvements translate to real search quality. The pipeline removes differences that OpenSearch's standard analyzer would ignore:

```python
def normalize_text(text: str) -> str:
    text = html.unescape(text)              # &quot; → "
    text = text.replace("—", "-").replace("–", "-")  # Normalize dash variants
    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)  # govern- ment → government
    text = re.sub(r'[^\w\s]', '', text)     # Remove all punctuation (including hyphens)
    return " ".join(text.lower().split())   # Lowercase + collapse whitespace
```

**Why these normalizations?** They ensure fair comparison by removing differences that don't affect search quality:
- **Line-break hyphens**: "govern- ment" → "government" (247 forms had these artifacts)
- **All hyphens removed**: After punctuation stripping, both "self-determination" and "selfdetermination" become "selfdetermination" (ensures consistent matching regardless of whether OCR preserves hyphens)
- **Case/whitespace**: Lowercase and collapse whitespace for consistent comparison

## Prerequisites

1. **Navigate to local dev environment**:
   ```bash
   cd local-dev-environment/testing/textract_accuracy
   source ../../.venv/bin/activate  # Activate virtual environment
   ```

2. **AWS Credentials** with Textract and Bedrock access:
   ```bash
   export AWS_ACCESS_KEY_ID="..."
   export AWS_SECRET_ACCESS_KEY="..."
=======
>>>>>>> 435e12b (add/custom_doc_ocr_and_augmentation)
   export AWS_REGION="us-east-1"
   ```
   Or add to `.env` file in project root.

3. **IAM Handwriting Database**: Download from [IAM Database](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database) and extract to:
   ```
   data/
   ├── page_images/    # PNG images (e.g., a01-000u.png)
   └── xml/            # Ground truth XML files
   ```

<<<<<<< HEAD
3. **Dependencies**: Ensure `jiwer` is installed:
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
4. **Python dependencies**:
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
   ```bash
   uv pip install jiwer
   ```

<<<<<<< HEAD
<<<<<<< HEAD
## Quick Start

### 1. Parse Ground Truth (One-Time Setup)
=======
### Parse Ground Truth (One-Time Setup)
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
## Quick Start

### 1. Parse Ground Truth (One-Time Setup)
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

```bash
python -m iam_testing.ground_truth_parser
```
<<<<<<< HEAD
<<<<<<< HEAD
Generates `data/ground_truth.jsonl` with 1539 form records.

### 2. Test Single Form

Validate the pipeline with one form:
=======
Creates `data/ground_truth.jsonl` with 1539 form records.
=======
Generates `data/ground_truth.jsonl` with 1539 form records.
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

### 2. Test Single Form

<<<<<<< HEAD
Validate the pipeline with one form (low API cost):
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
Validate the pipeline with one form:
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

```bash
python -m iam_testing.runners.single
python -m iam_testing.runners.single --form-id r06-121
python -m iam_testing.runners.single --form-id r06-121 --show-full-text
```
<<<<<<< HEAD
<<<<<<< HEAD
Output: `data/latest_single_test.json`

### 3. Run Baseline Batch

Process all forms through Textract:

```bash
python -m iam_testing.runners.batch --limit 10    # Test with 10 forms
python -m iam_testing.runners.batch               # All 1539 forms
python -m iam_testing.runners.batch --resume      # Resume interrupted run
```
Output: `data/batch_runs/{run_id}/ocr_results.jsonl` and `score_results.jsonl`

### 4. Run LLM Augmentation
=======

=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
Output: `data/latest_single_test.json`

### 3. Run Baseline Batch

Process all forms through Textract:

```bash
python -m iam_testing.runners.batch --limit 10    # Test with 10 forms
python -m iam_testing.runners.batch               # All 1539 forms
python -m iam_testing.runners.batch --resume      # Resume interrupted run
```
Output: `data/batch_runs/{run_id}/ocr_results.jsonl` and `score_results.jsonl`

<<<<<<< HEAD
Output:
- `data/ocr_results_<run_id>.jsonl` — Raw OCR output
- `data/score_results_<run_id>.jsonl` — WER/CER scores

### Run LLM Augmentation
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
### 4. Run LLM Augmentation
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

Apply LLM correction to baseline results:

```bash
<<<<<<< HEAD
<<<<<<< HEAD
python -m iam_testing.runners.augment --baseline-run 20260126_140000
python -m iam_testing.runners.augment --baseline-run 20260126_140000 --model nova-pro
```

The recommended prompt (v2) is used by default. Override with `--prompt v1/v3/v4` if needed.

Output: `data/batch_runs/{run_id}/augmented/{model}_{prompt}_{mode}.jsonl`

## LLM Models & Prompts

### Available Models

| Model | Provider | Notes |
|-------|----------|-------|
| `nova-pro` | Amazon | Best quality, recommended |
| `nova-lite` | Amazon | Good balance, default |
| `nova-micro` | Amazon | Fastest, cheapest |
| `mistral-7b`, `mixtral-8x7b`, `mistral-large` | Mistral AI | Generally auto-enabled |
| `llama-3-8b`, `llama-3-70b`, `llama-3-1-8b`, `llama-3-1-70b` | Meta | Generally auto-enabled |
| `claude-3-haiku`, `claude-3-5-haiku`, `claude-3-sonnet`, `claude-3-5-sonnet` | Anthropic | Requires Bedrock subscription |

### Prompt Versions

| Version | Style | Performance (100-sample) | Notes |
|---------|-------|--------------------------|-------|
| **v2** | Concise | **8.04% WER** | ⭐ Recommended - best performing |
| v1 | Detailed | 9.09% WER | Comprehensive guidelines |
| v3 | Context-aware | Not tested | Emphasizes understanding |
| v4 | Few-shot | 9.26% WER | With examples, struggled with over-correction |

All prompts include:
- British English spelling instructions
- Proper noun preservation (prevents "Kaldor" → "Colder")
- Short word preservation (keeps `in`/`is`/`on`, `we`/`he` as-is)

## Understanding Results

### Normalization Impact

The normalization pipeline handles common OCR variations that don't affect search:

| Issue | Prevalence | Example | Fix |
|-------|------------|---------|-----|
| Line-break hyphens | 247 forms | `govern- ment` | Rejoin to `government` |
| HTML entities | ~1100 chars | `&quot;hello&quot;` | Decode to `"hello"` |
| Dash variants | 37 instances | `self—determination` | Normalize to `self-determination` |
| Compound hyphens | Many | `self-determination` | Remove to `selfdetermination` |
| Punctuation | All | `hello,` vs `hello.` | Strip completely |

### Error Patterns

Common remaining errors after LLM augmentation (4.41% WER):
- Vowel confusions: `a↔o`, `e↔o`, `e↔a`
- Consonant swaps: `z→s` (British spelling), `n→r`, `w→m`
- Character similarity: OCR struggles with similar letterforms

Output: `data/batch_runs/{run_id}/augmented/{model}_{prompt}_{mode}.jsonl`

## Testing Custom Documents

To test your own documents (non-IAM dataset):

**1. Create ground truth file** (`data/custom_ground_truth.jsonl`):
```json
{"page_id": "page1", "image_path": "data/custom/page1.png", "gt_handwriting_text": "your ground truth"}
{"page_id": "page2", "image_path": "data/custom/page2.png", "gt_handwriting_text": "your ground truth"}
```

**2. Run baseline test**:
```bash
# Single page
python -m iam_testing.runners.custom --mode single --page-id page1

# All pages in batch
python -m iam_testing.runners.custom --mode batch
```

**3. Apply LLM augmentation**:
```bash
python -m iam_testing.runners.augment --baseline-run 20260204_120000 --dataset custom --model nova-pro
```

Custom testing skips IAM-specific filtering (headers/footers/signatures) and works with arbitrary documents.
=======
# List available baseline runs
ls data/score_results_*.jsonl

# Augment a baseline run
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
python -m iam_testing.runners.augment --baseline-run 20260126_140000
python -m iam_testing.runners.augment --baseline-run 20260126_140000 --model nova-pro
```

The recommended prompt (v2) is used by default. Override with `--prompt v1/v3/v4` if needed.

<<<<<<< HEAD
Output: `data/augmented_results_<run_id>_<model>.jsonl`
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
Output: `data/batch_runs/{run_id}/augmented/{model}_{prompt}_{mode}.jsonl`

## LLM Models & Prompts

### Available Models

| Model | Provider | Notes |
|-------|----------|-------|
| `nova-pro` | Amazon | Best quality, recommended |
| `nova-lite` | Amazon | Good balance, default |
| `nova-micro` | Amazon | Fastest, cheapest |
| `mistral-7b`, `mixtral-8x7b`, `mistral-large` | Mistral AI | Generally auto-enabled |
| `llama-3-8b`, `llama-3-70b`, `llama-3-1-8b`, `llama-3-1-70b` | Meta | Generally auto-enabled |
| `claude-3-haiku`, `claude-3-5-haiku`, `claude-3-sonnet`, `claude-3-5-sonnet` | Anthropic | Requires Bedrock subscription |

### Prompt Versions

| Version | Style | Performance (100-sample) | Notes |
|---------|-------|--------------------------|-------|
| **v2** | Concise | **8.04% WER** | ⭐ Recommended - best performing |
| v1 | Detailed | 9.09% WER | Comprehensive guidelines |
| v3 | Context-aware | Not tested | Emphasizes understanding |
| v4 | Few-shot | 9.26% WER | With examples, struggled with over-correction |

All prompts include:
- British English spelling instructions
- Proper noun preservation (prevents "Kaldor" → "Colder")
- Short word preservation (keeps `in`/`is`/`on`, `we`/`he` as-is)

## Understanding Results

### Normalization Impact

The normalization pipeline handles common OCR variations that don't affect search:

| Issue | Prevalence | Example | Fix |
|-------|------------|---------|-----|
| Line-break hyphens | 247 forms | `govern- ment` | Rejoin to `government` |
| HTML entities | ~1100 chars | `&quot;hello&quot;` | Decode to `"hello"` |
| Dash variants | 37 instances | `self—determination` | Normalize to `self-determination` |
| Compound hyphens | Many | `self-determination` | Remove to `selfdetermination` |
| Punctuation | All | `hello,` vs `hello.` | Strip completely |

### Error Patterns

Common remaining errors after LLM augmentation (4.41% WER):
- Vowel confusions: `a↔o`, `e↔o`, `e↔a`
- Consonant swaps: `z→s` (British spelling), `n→r`, `w→m`
- Character similarity: OCR struggles with similar letterforms

Output: `data/batch_runs/{run_id}/augmented/{model}_{prompt}_{mode}.jsonl`

## Testing Custom Documents

To test your own documents (non-IAM dataset):

**1. Create ground truth file** (`data/custom_ground_truth.jsonl`):
```json
{"page_id": "page1", "image_path": "data/custom/page1.png", "gt_handwriting_text": "your ground truth"}
{"page_id": "page2", "image_path": "data/custom/page2.png", "gt_handwriting_text": "your ground truth"}
```

**2. Run baseline test**:
```bash
# Single page
python -m iam_testing.runners.custom --mode single --page-id page1

# All pages in batch
python -m iam_testing.runners.custom --mode batch
```

**3. Apply LLM augmentation**:
```bash
python -m iam_testing.runners.augment --baseline-run 20260204_120000 --dataset custom --model nova-pro
```

Custom testing skips IAM-specific filtering (headers/footers/signatures) and works with arbitrary documents.
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

## Package Structure

```
iam_testing/
├── runners/              # CLI entry points
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
│   ├── single.py         # IAM single-form test
│   ├── batch.py          # IAM batch baseline runner  
│   ├── augment.py        # LLM augmentation (IAM or custom)
│   ├── custom.py         # Custom document runner
│   └── utils.py          # Shared JSONL I/O
├── llm/                  # LLM integration
│   ├── clients.py        # Nova, Claude, Llama, Mistral clients
│   ├── prompt.py         # Versioned system prompts (v1/v2/v3/v4)
│   ├── diff.py           # Diff generation
│   └── response.py       # Response handling
├── scoring.py            # WER/CER calculation
├── textract_ocr.py       # OCR processing
├── iam_filters.py        # Text normalization
├── ground_truth_parser.py # IAM XML parser
└── config.py             # Configuration
<<<<<<< HEAD
```

## How Normalization Works

Text normalization ensures WER improvements translate to real search quality. The pipeline is **search-neutral**: it only removes differences that OpenSearch already ignores.

**Example: Line-break hyphenation** (247 forms affected)
- Ground truth: `"govern- ment"` 
- LLM output: `"government"` 
- Normalization: Both → `"government"` (no WER penalty)
- OpenSearch: Both index identically

**Example: Compound word hyphens**
- Variants: `"self-determination"` vs `"selfdetermination"`
- OpenSearch: Tokenizes both → `["self", "determination"]`
- Normalization: Remove hyphens (no search impact)

Pipeline: `html.unescape()` → dash normalization → line-break rejoin → strip punctuation → lowercase

## Output Formats

**Baseline** (`score_results/`):
=======
│   ├── single.py         # Single-form test
│   ├── batch.py          # Batch baseline runner
│   └── augment.py        # LLM augmentation runner
├── llm/                  # LLM client layer
│   ├── __init__.py       # Factory: get_llm_client()
│   ├── clients.py        # Nova + Claude implementations
│   ├── prompt.py         # Versioned system prompt
│   └── response.py       # LLMResponse dataclass
├── schemas.py            # OCRResult, WordBlock
├── scoring.py            # ScoreResult, WER/CER calculation
├── textract_client.py    # AWS Textract utilities
├── textract_ocr.py       # OCR processing pipeline
├── iam_filters.py        # Header/footer/signature filters
├── ground_truth_parser.py # IAM XML → JSONL parser
└── config.py             # Settings loader
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
```

## How Normalization Works

Text normalization ensures WER improvements translate to real search quality. The pipeline is **search-neutral**: it only removes differences that OpenSearch already ignores.

**Example: Line-break hyphenation** (247 forms affected)
- Ground truth: `"govern- ment"` 
- LLM output: `"government"` 
- Normalization: Both → `"government"` (no WER penalty)
- OpenSearch: Both index identically

**Example: Compound word hyphens**
- Variants: `"self-determination"` vs `"selfdetermination"`
- OpenSearch: Tokenizes both → `["self", "determination"]`
- Normalization: Remove hyphens (no search impact)

Pipeline: `html.unescape()` → dash normalization → line-break rejoin → strip punctuation → lowercase

## Output Formats

<<<<<<< HEAD
### score_results (Baseline)
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
**Baseline** (`score_results/`):
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
```json
{
  "form_id": "r06-121",
  "wer_handwriting": 0.0789,
<<<<<<< HEAD
<<<<<<< HEAD
=======
  "cer_handwriting": 0.0236,
  "wer_print": 0.0,
  "cer_print": 0.0,
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
  "gt_handwriting_text": "...",
  "ocr_handwriting_text": "..."
}
```

<<<<<<< HEAD
<<<<<<< HEAD
**Augmented** (`augmented/`):
```json
{
  "form_id": "r06-121",
  "llm_model": "nova-pro",
  "prompt_version": "v2",
  "baseline_wer": 0.0789,
  "augmented_wer": 0.0395,
  "wer_improvement": 0.0394
}
```
=======
### augmented_results (LLM)
=======
**Augmented** (`augmented/`):
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
```json
{
  "form_id": "r06-121",
  "llm_model": "nova-pro",
  "prompt_version": "v2",
  "baseline_wer": 0.0789,
  "augmented_wer": 0.0395,
  "wer_improvement": 0.0394
}
```
<<<<<<< HEAD

## Cost Estimates

| Operation | Cost per form | 1000 forms |
|-----------|---------------|------------|
| Textract | ~$0.0015 | ~$1.50 |
| Nova Lite | ~$0.0002 | ~$0.20 |
| Claude Haiku | ~$0.0003 | ~$0.30 |

*Estimates based on typical form size. Actual costs may vary.*
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
