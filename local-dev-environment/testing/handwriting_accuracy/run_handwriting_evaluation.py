"""Handwriting evaluation: direct vision + augmentation + multimodal + multimodal-structured.

Part 1: Direct vision extraction
  - Model: configured via VISION_MODEL
  - Prompt: configured via VISION_PROMPT
  - Ground truth: case_documents_ground_truth.jsonl

Part 2: Textract OCR + LLM augmentation
  - Model: configured via AUGMENT_MODEL
  - Prompt: configured via AUGMENT_PROMPT
  - Textract baseline: custom_batch_runs/20260224_103557/ocr_results.jsonl

Part 3: Multimodal — image + flat OCR text hint -> vision model
  - Model: configured via MULTIMODAL_MODEL
  - Prompt: configured via MULTIMODAL_PROMPT

Part 4: Multimodal structured — image + Textract spatial word table -> vision model
  - Calls Textract live to get per-word bounding boxes, TextType, and confidence
  - Model: configured via MULTIMODAL_STRUCT_MODEL
  - Prompt: configured via MULTIMODAL_STRUCT_PROMPT

Outputs written to:
  - data/litellm_evaluation/vision/
  - data/litellm_evaluation/augment/
  - data/litellm_evaluation/multimodal/
  - data/litellm_evaluation/combined_results_v3.csv
"""

import csv
import json
import logging
import sys
import time
from pathlib import Path

API_CALL_DELAY = 5

TESTING_ROOT = Path(__file__).parent
sys.path.insert(0, str(TESTING_ROOT))
sys.path.insert(0, str(TESTING_ROOT.parent.parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(TESTING_ROOT.parent.parent.parent / ".env")

from iam_testing.iam_filters import normalize_text  # noqa: E402
from iam_testing.llm import get_llm_client  # noqa: E402
from iam_testing.textract_client import analyze_image_sync, extract_word_blocks, get_textract_client  # noqa: E402
from jiwer import cer, wer  # noqa: E402
from vision_model_testing.llm import get_vision_client  # noqa: E402
from vision_model_testing.scoring import score_vision_result  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = TESTING_ROOT / "data"
GT_FILE = DATA_DIR / "case_documents_ground_truth.jsonl"
OCR_FILE = DATA_DIR / "custom_batch_runs" / "20260224_103557" / "ocr_results.jsonl"
OUTPUT_DIR = DATA_DIR / "litellm_evaluation"

VISION_MODEL = "bedrock-claude-opus-4-6"
VISION_PROMPT = "v1.5"
AUGMENT_MODEL = "bedrock-claude-sonnet-4-6"
AUGMENT_PROMPT = "v2.6"
MULTIMODAL_MODEL = "bedrock-claude-opus-4-6"
MULTIMODAL_PROMPT = "v1.5-mm"
MULTIMODAL_STRUCT_MODEL = "bedrock-claude-opus-4-6"
MULTIMODAL_STRUCT_PROMPT = "v1.5-mm-struct2"


def load_ground_truth() -> list[dict]:
    """Load ground truth records from the JSONL file."""
    records = []
    with open(GT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    logger.info("Loaded %d ground truth records", len(records))
    return records


def load_textract_ocr() -> dict[str, str]:
    """Load Textract OCR handwriting text keyed by page ID."""
    ocr_map = {}
    with open(OCR_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                page_id = data.get("form_id", "")
                ocr_text = data.get("ocr_handwriting_text", "")
                if page_id and ocr_text:
                    ocr_map[page_id] = ocr_text
    logger.info("Loaded Textract OCR for %d pages", len(ocr_map))
    return ocr_map


def resolve_image(image_path_str: str) -> Path:
    """Resolve an image path relative to DATA_DIR or TESTING_ROOT."""
    p = DATA_DIR / image_path_str
    if p.exists():
        return p
    p = TESTING_ROOT / image_path_str
    if p.exists():
        return p
    raise FileNotFoundError(f"Image not found: {image_path_str}")


def run_vision_extraction(gt_records: list[dict]) -> list[dict]:
    """Run direct vision extraction for all ground truth pages."""
    logger.info("=" * 60)
    logger.info("VISION EXTRACTION: %s (prompt %s)", VISION_MODEL, VISION_PROMPT)
    logger.info("=" * 60)

    client = get_vision_client(model=VISION_MODEL, prompt_version=VISION_PROMPT)
    results = []

    for i, gt in enumerate(gt_records, 1):
        page_id = gt["page_id"]
        image_path = resolve_image(gt["image_path"])

        if not image_path.exists():
            logger.warning("Image not found: %s", image_path)
            continue

        try:
            logger.info("[%d/%d] %s -> %s", i, len(gt_records), VISION_MODEL, page_id)
            response = client.extract_text_from_image(image_path)
            score = score_vision_result(
                page_id=page_id,
                gt_text=gt["gt_handwriting_text"],
                vision_text=response.extracted_text,
                vision_model=response.model,
                vision_prompt=response.prompt_version,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            results.append(
                {
                    "page_id": page_id,
                    "document_type": gt.get("document_type", ""),
                    "vision_text": response.extracted_text,
                    "wer": score.wer,
                    "cer": score.cer,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                }
            )
            logger.info("  WER: %.4f  CER: %.4f", score.wer, score.cer)
            time.sleep(API_CALL_DELAY)
        except Exception as e:
            logger.error("  Failed: %s", e)
            continue

    return results


def run_augmentation(gt_records: list[dict], ocr_map: dict[str, str]) -> list[dict]:
    """Run Textract OCR + LLM augmentation for matched pages."""
    logger.info("=" * 60)
    logger.info("TEXTRACT + LLM AUGMENTATION: %s (prompt %s)", AUGMENT_MODEL, AUGMENT_PROMPT)
    logger.info("=" * 60)

    llm_client = get_llm_client(model=AUGMENT_MODEL, prompt_version=AUGMENT_PROMPT)
    results = []
    matched = [(gt, ocr_map[gt["page_id"]]) for gt in gt_records if gt["page_id"] in ocr_map]

    for i, (gt, ocr_text) in enumerate(matched, 1):
        page_id = gt["page_id"]
        gt_text = gt["gt_handwriting_text"]

        try:
            logger.info("[%d/%d] %s -> %s", i, len(matched), AUGMENT_MODEL, page_id)
            gt_norm = normalize_text(gt_text)
            ocr_norm = normalize_text(ocr_text)
            baseline_wer = wer(gt_norm, ocr_norm) if gt_norm and ocr_norm else 1.0
            baseline_cer = cer(gt_norm, ocr_norm) if gt_norm and ocr_norm else 1.0

            llm_response = llm_client.correct_ocr_text(ocr_text)
            augmented_text = llm_response.corrected_text
            augmented_norm = normalize_text(augmented_text)
            augmented_wer = wer(gt_norm, augmented_norm) if gt_norm and augmented_norm else 1.0
            augmented_cer = cer(gt_norm, augmented_norm) if gt_norm and augmented_norm else 1.0

            results.append(
                {
                    "page_id": page_id,
                    "document_type": gt.get("document_type", ""),
                    "ocr_text": ocr_text,
                    "augmented_text": augmented_text,
                    "baseline_wer": baseline_wer,
                    "baseline_cer": baseline_cer,
                    "augmented_wer": augmented_wer,
                    "augmented_cer": augmented_cer,
                    "wer_improvement": baseline_wer - augmented_wer,
                }
            )
            logger.info(
                "  Textract WER: %.4f -> Augmented WER: %.4f (%+.4f)",
                baseline_wer,
                augmented_wer,
                baseline_wer - augmented_wer,
            )
            time.sleep(API_CALL_DELAY)
        except Exception as e:
            logger.error("  Failed: %s", e)
            continue

    return results


def print_table(headers: list[str], rows: list[list[str]], title: str = "") -> None:  # noqa: T201
    """Print a formatted table to stdout."""
    if title:
        print(f"\n{'=' * 80}")  # noqa: T201
        print(f"  {title}")  # noqa: T201
        print(f"{'=' * 80}")  # noqa: T201
    col_widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    print("\n" + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)))  # noqa: T201
    print("-+-".join("-" * w for w in col_widths))  # noqa: T201
    for row in rows:
        print(" | ".join(r.ljust(w) for r, w in zip(row, col_widths)))  # noqa: T201
    print()  # noqa: T201


def print_summary(vision_results: list[dict], augment_results: list[dict]) -> None:
    """Print per-page and average WER summary tables for vision and augmentation results."""
    # Vision summary
    if vision_results:
        headers = ["Page ID", "Vision WER", "Vision CER"]
        rows = [[r["page_id"], f"{r['wer']:.4f}", f"{r['cer']:.4f}"] for r in vision_results]
        n = len(vision_results)
        rows.append(
            [
                "AVERAGE",
                f"{sum(r['wer'] for r in vision_results) / n:.4f}",
                f"{sum(r['cer'] for r in vision_results) / n:.4f}",
            ]
        )
        print_table(headers, rows, f"VISION EXTRACTION ({VISION_MODEL}, prompt {VISION_PROMPT})")

    # Augmentation summary
    if augment_results:
        headers = ["Page ID", "Textract WER", "Aug WER", "WER Δ"]
        rows = [
            [r["page_id"], f"{r['baseline_wer']:.4f}", f"{r['augmented_wer']:.4f}", f"{r['wer_improvement']:+.4f}"]
            for r in augment_results
        ]
        n = len(augment_results)
        rows.append(
            [
                "AVERAGE",
                f"{sum(r['baseline_wer'] for r in augment_results) / n:.4f}",
                f"{sum(r['augmented_wer'] for r in augment_results) / n:.4f}",
                f"{sum(r['wer_improvement'] for r in augment_results) / n:+.4f}",
            ]
        )
        improved = sum(1 for r in augment_results if r["wer_improvement"] > 0)
        print_table(headers, rows, f"TEXTRACT AUGMENTATION ({AUGMENT_MODEL}, prompt {AUGMENT_PROMPT})")
        print(  # noqa: T201
            f"  Improved: {improved}/{n}  Degraded: {sum(1 for r in augment_results if r['wer_improvement'] < 0)}/{n}"
        )


def _print_by_type(results: list[dict], wer_key: str, label: str) -> None:
    for doc_type in ("structured_form", "free_text"):
        subset = [r for r in results if r.get("document_type") == doc_type]
        if not subset:
            continue
        avg = sum(r[wer_key] for r in subset) / len(subset)
        print(f"  {label} [{doc_type}]: avg WER {avg:.4f} over {len(subset)} pages")  # noqa: T201


def print_summary_by_type(
    vision_results: list[dict],
    augment_results: list[dict],
    multimodal_results: list[dict],
    multimodal_struct_results: list[dict],
) -> None:
    """Print average WER broken down by document type for all methods."""
    print(f"\n{'=' * 80}")  # noqa: T201
    print("  WER BY DOCUMENT TYPE")  # noqa: T201
    print(f"{'=' * 80}")  # noqa: T201
    if vision_results:
        _print_by_type(vision_results, "wer", f"Vision ({VISION_MODEL} {VISION_PROMPT})")
    if augment_results:
        _print_by_type(augment_results, "augmented_wer", f"Augment ({AUGMENT_MODEL} {AUGMENT_PROMPT})")
    if multimodal_results:
        _print_by_type(multimodal_results, "wer", f"Multimodal ({MULTIMODAL_MODEL} {MULTIMODAL_PROMPT})")
    if multimodal_struct_results:
        _print_by_type(
            multimodal_struct_results,
            "wer",
            f"Multimodal-struct ({MULTIMODAL_STRUCT_MODEL} {MULTIMODAL_STRUCT_PROMPT})",
        )


def run_multimodal_structured(gt_records: list[dict]) -> list[dict]:
    """Run multimodal extraction with structured Textract spatial word table."""
    logger.info("=" * 60)
    logger.info("MULTIMODAL STRUCTURED: %s (prompt %s)", MULTIMODAL_STRUCT_MODEL, MULTIMODAL_STRUCT_PROMPT)
    logger.info("=" * 60)

    client = get_vision_client(model=MULTIMODAL_STRUCT_MODEL, prompt_version=MULTIMODAL_STRUCT_PROMPT)
    textract_client = get_textract_client()
    results = []

    for i, gt in enumerate(gt_records, 1):
        page_id = gt["page_id"]
        image_path = resolve_image(gt["image_path"])

        if not image_path.exists():
            logger.warning("Image not found: %s", image_path)
            continue

        try:
            logger.info("[%d/%d] Textract -> %s", i, len(gt_records), page_id)
            response = analyze_image_sync(textract_client, image_path)
            word_blocks = extract_word_blocks(response)
            logger.info(
                "  Textract words: %d (HW: %d, PRINT: %d)",
                len(word_blocks),
                sum(1 for w in word_blocks if w.text_type == "HANDWRITING"),
                sum(1 for w in word_blocks if w.text_type == "PRINTED"),
            )

            logger.info("  Sending to %s...", MULTIMODAL_STRUCT_MODEL)
            vision_response = client.extract_text_with_structured_ocr(image_path, word_blocks)
            score = score_vision_result(
                page_id=page_id,
                gt_text=gt["gt_handwriting_text"],
                vision_text=vision_response.extracted_text,
                vision_model=vision_response.model,
                vision_prompt=vision_response.prompt_version,
                input_tokens=vision_response.input_tokens,
                output_tokens=vision_response.output_tokens,
            )
            results.append(
                {
                    "page_id": page_id,
                    "document_type": gt.get("document_type", ""),
                    "multimodal_struct_text": vision_response.extracted_text,
                    "wer": score.wer,
                    "cer": score.cer,
                    "input_tokens": vision_response.input_tokens,
                    "output_tokens": vision_response.output_tokens,
                }
            )
            logger.info("  WER: %.4f  CER: %.4f", score.wer, score.cer)
            time.sleep(API_CALL_DELAY)
        except Exception as e:
            logger.error("  Failed %s: %s", page_id, e)
            continue

    return results


def run_multimodal_extraction(gt_records: list[dict], ocr_map: dict[str, str]) -> list[dict]:
    """Run multimodal extraction with flat OCR text hint alongside the image."""
    logger.info("=" * 60)
    logger.info("MULTIMODAL EXTRACTION: %s (prompt %s)", MULTIMODAL_MODEL, MULTIMODAL_PROMPT)
    logger.info("=" * 60)

    client = get_vision_client(model=MULTIMODAL_MODEL, prompt_version=MULTIMODAL_PROMPT)
    results = []
    matched = [(gt, ocr_map[gt["page_id"]]) for gt in gt_records if gt["page_id"] in ocr_map]

    for i, (gt, ocr_text) in enumerate(matched, 1):
        page_id = gt["page_id"]
        image_path = resolve_image(gt["image_path"])

        if not image_path.exists():
            logger.warning("Image not found: %s", image_path)
            continue

        try:
            logger.info("[%d/%d] %s -> %s", i, len(matched), MULTIMODAL_MODEL, page_id)
            response = client.extract_text_with_ocr_hint(image_path, ocr_text)
            score = score_vision_result(
                page_id=page_id,
                gt_text=gt["gt_handwriting_text"],
                vision_text=response.extracted_text,
                vision_model=response.model,
                vision_prompt=response.prompt_version,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            results.append(
                {
                    "page_id": page_id,
                    "document_type": gt.get("document_type", ""),
                    "multimodal_text": response.extracted_text,
                    "wer": score.wer,
                    "cer": score.cer,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                }
            )
            logger.info("  WER: %.4f  CER: %.4f", score.wer, score.cer)
            time.sleep(API_CALL_DELAY)
        except Exception as e:
            logger.error("  Failed: %s", e)
            continue

    return results


def save_results(
    vision_results: list[dict],
    augment_results: list[dict],
    multimodal_results: list[dict],
    multimodal_struct_results: list[dict],
) -> None:
    """Save all evaluation results as JSONL files."""
    vision_dir = OUTPUT_DIR / "vision"
    augment_dir = OUTPUT_DIR / "augment"
    multimodal_dir = OUTPUT_DIR / "multimodal"
    for d in (vision_dir, augment_dir, multimodal_dir):
        d.mkdir(parents=True, exist_ok=True)

    vision_file = vision_dir / f"vision_{VISION_MODEL}_{VISION_PROMPT}.jsonl"
    with open(vision_file, "w", encoding="utf-8") as f:
        for r in vision_results:
            f.write(json.dumps(r) + "\n")
    logger.info("Saved vision results: %s", vision_file)

    augment_file = augment_dir / f"textract_augment_{AUGMENT_MODEL}_{AUGMENT_PROMPT}.jsonl"
    with open(augment_file, "w", encoding="utf-8") as f:
        for r in augment_results:
            f.write(json.dumps(r) + "\n")
    logger.info("Saved augment results: %s", augment_file)

    if multimodal_results:
        mm_file = multimodal_dir / f"multimodal_{MULTIMODAL_MODEL}_{MULTIMODAL_PROMPT}.jsonl"
        with open(mm_file, "w", encoding="utf-8") as f:
            for r in multimodal_results:
                f.write(json.dumps(r) + "\n")
        logger.info("Saved multimodal results: %s", mm_file)

    if multimodal_struct_results:
        mm_struct_file = multimodal_dir / f"multimodal_{MULTIMODAL_STRUCT_MODEL}_{MULTIMODAL_STRUCT_PROMPT}.jsonl"
        with open(mm_struct_file, "w", encoding="utf-8") as f:
            for r in multimodal_struct_results:
                f.write(json.dumps(r) + "\n")
        logger.info("Saved multimodal-structured results: %s", mm_struct_file)


def build_csv(
    gt_records: list[dict],
    vision_results: list[dict],
    augment_results: list[dict],
    multimodal_results: list[dict],
    multimodal_struct_results: list[dict],
) -> None:
    """Write a combined CSV comparing all evaluation methods side by side."""
    vision_map = {r["page_id"]: r for r in vision_results}
    augment_map = {r["page_id"]: r for r in augment_results}
    multimodal_map = {r["page_id"]: r for r in multimodal_results}
    mm_struct_map = {r["page_id"]: r for r in multimodal_struct_results}
    gt_map = {r["page_id"]: r["gt_handwriting_text"] for r in gt_records}
    type_map = {r["page_id"]: r.get("document_type", "") for r in gt_records}

    all_pages = sorted(
        set(
            list(vision_map.keys())
            + list(augment_map.keys())
            + list(multimodal_map.keys())
            + list(mm_struct_map.keys())
        ),
        key=lambda x: (x.split("page")[0], int(x.split("page")[1])),
    )

    out_file = OUTPUT_DIR / "combined_results_v3.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "case and page",
                "document type",
                "ground truth text",
                "ocr text (textract)",
                "textract WER",
                f"augmented text ({AUGMENT_MODEL} {AUGMENT_PROMPT})",
                "augmented WER",
                f"vision text ({VISION_MODEL} {VISION_PROMPT})",
                "vision WER",
                f"multimodal text ({MULTIMODAL_MODEL} {MULTIMODAL_PROMPT})",
                "multimodal WER",
                f"multimodal-struct text ({MULTIMODAL_STRUCT_MODEL} {MULTIMODAL_STRUCT_PROMPT})",
                "multimodal-struct WER",
            ]
        )
        for pid in all_pages:
            aug = augment_map.get(pid, {})
            vis = vision_map.get(pid, {})
            mm = multimodal_map.get(pid, {})
            mms = mm_struct_map.get(pid, {})
            writer.writerow(
                [
                    pid,
                    type_map.get(pid, ""),
                    gt_map.get(pid, ""),
                    aug.get("ocr_text", ""),
                    f"{aug['baseline_wer']:.4f}" if aug else "",
                    aug.get("augmented_text", ""),
                    f"{aug['augmented_wer']:.4f}" if aug else "",
                    vis.get("vision_text", ""),
                    f"{vis['wer']:.4f}" if vis else "",
                    mm.get("multimodal_text", ""),
                    f"{mm['wer']:.4f}" if mm else "",
                    mms.get("multimodal_struct_text", ""),
                    f"{mms['wer']:.4f}" if mms else "",
                ]
            )

    logger.info("Saved CSV: %s (%d rows)", out_file, len(all_pages))


def load_jsonl(path: Path) -> list[dict]:
    """Load records from a JSONL file."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> None:
    """Run all four evaluation parts and print combined summary."""
    gt_records = load_ground_truth()
    ocr_map = load_textract_ocr()

    matched = [gt["page_id"] for gt in gt_records if gt["page_id"] in ocr_map]
    missing = [gt["page_id"] for gt in gt_records if gt["page_id"] not in ocr_map]
    logger.info("Matched %d pages for augmentation, missing OCR for: %s", len(matched), missing or "none")

    vision_file = OUTPUT_DIR / "vision" / f"vision_{VISION_MODEL}_{VISION_PROMPT}.jsonl"
    if vision_file.exists():
        logger.info("PART 1: Loading existing vision results from %s", vision_file)
        vision_results = load_jsonl(vision_file)
    else:
        logger.info("=" * 70)
        logger.info(
            "PART 1: Vision extraction — %s (prompt %s), %d pages", VISION_MODEL, VISION_PROMPT, len(gt_records)
        )
        logger.info("=" * 70)
        vision_results = run_vision_extraction(gt_records)

    augment_file = OUTPUT_DIR / "augment" / f"textract_augment_{AUGMENT_MODEL}_{AUGMENT_PROMPT}.jsonl"
    if augment_file.exists():
        logger.info("PART 2: Loading existing augment results from %s", augment_file)
        augment_results = load_jsonl(augment_file)
    else:
        logger.info("=" * 70)
        logger.info(
            "PART 2: Textract augmentation — %s (prompt %s), %d pages", AUGMENT_MODEL, AUGMENT_PROMPT, len(matched)
        )
        logger.info("=" * 70)
        augment_results = run_augmentation(gt_records, ocr_map)

    mm_file = OUTPUT_DIR / "multimodal" / f"multimodal_{MULTIMODAL_MODEL}_{MULTIMODAL_PROMPT}.jsonl"
    if mm_file.exists():
        logger.info("PART 3: Loading existing multimodal results from %s", mm_file)
        multimodal_results = load_jsonl(mm_file)
    else:
        logger.info("=" * 70)
        logger.info("PART 3: Multimodal — %s (prompt %s), %d pages", MULTIMODAL_MODEL, MULTIMODAL_PROMPT, len(matched))
        logger.info("=" * 70)
        multimodal_results = run_multimodal_extraction(gt_records, ocr_map)

    logger.info("=" * 70)
    logger.info(
        "PART 4: Multimodal structured — %s (prompt %s), %d pages",
        MULTIMODAL_STRUCT_MODEL,
        MULTIMODAL_STRUCT_PROMPT,
        len(gt_records),
    )
    logger.info("=" * 70)
    multimodal_struct_results = run_multimodal_structured(gt_records)

    save_results(vision_results, augment_results, multimodal_results, multimodal_struct_results)
    print_summary(vision_results, augment_results)
    if multimodal_results:
        headers = ["Page ID", "Multimodal WER", "Multimodal CER"]
        rows = [[r["page_id"], f"{r['wer']:.4f}", f"{r['cer']:.4f}"] for r in multimodal_results]
        n = len(multimodal_results)
        rows.append(
            [
                "AVERAGE",
                f"{sum(r['wer'] for r in multimodal_results) / n:.4f}",
                f"{sum(r['cer'] for r in multimodal_results) / n:.4f}",
            ]
        )
        print_table(headers, rows, f"MULTIMODAL ({MULTIMODAL_MODEL}, prompt {MULTIMODAL_PROMPT})")
    if multimodal_struct_results:
        headers = ["Page ID", "MM-Struct WER", "MM-Struct CER"]
        rows = [[r["page_id"], f"{r['wer']:.4f}", f"{r['cer']:.4f}"] for r in multimodal_struct_results]
        n = len(multimodal_struct_results)
        rows.append(
            [
                "AVERAGE",
                f"{sum(r['wer'] for r in multimodal_struct_results) / n:.4f}",
                f"{sum(r['cer'] for r in multimodal_struct_results) / n:.4f}",
            ]
        )
        print_table(
            headers, rows, f"MULTIMODAL STRUCTURED ({MULTIMODAL_STRUCT_MODEL}, prompt {MULTIMODAL_STRUCT_PROMPT})"
        )
    print_summary_by_type(vision_results, augment_results, multimodal_results, multimodal_struct_results)
    build_csv(gt_records, vision_results, augment_results, multimodal_results, multimodal_struct_results)


if __name__ == "__main__":
    main()
