"""Shared utilities for vision model testing runners.

Common JSONL I/O and path helpers, adapted from iam_testing.
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp.

    Returns:
        Run ID in format: YYYYMMDD_HHMMSS
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# =============================================================================
# Path helpers for hierarchical batch_runs structure
# =============================================================================
#
# Structure:
#   batch_runs/
#   ├── {run_id}/
#   │   ├── vision_results.jsonl
#   │   ├── vision_scores.jsonl
#   │   ├── summary.json
#   │   └── augmented/
#   │       ├── {model}_{prompt}.jsonl
#   │       └── {model}_{prompt}_summary.json
#   └── {run_id}/
#       └── ...


def get_run_dir(batch_runs_dir: Path, run_id: str) -> Path:
    """Get the directory for a specific vision run.

    Args:
        batch_runs_dir: Path to batch_runs directory.
        run_id: Run identifier (e.g., '20260128_172501').

    Returns:
        Path to the run directory.
    """
    return batch_runs_dir / run_id


def get_vision_paths(
    batch_runs_dir: Path,
    run_id: str,
    model: str,
    prompt: str,
) -> dict[str, Path]:
    """Get all file paths for a vision run.

    Args:
        batch_runs_dir: Path to batch_runs directory.
        run_id: Run identifier.
        model: Vision model name (e.g., 'nova-pro').
        prompt: Prompt version (e.g., 'v1').

    Returns:
        Dict with keys: 'dir', 'results', 'scores', 'summary'.
    """
    run_dir = get_run_dir(batch_runs_dir, run_id)
    filename_base = f"vision_{model}_{prompt}"
    return {
        "dir": run_dir,
        "results": run_dir / f"{filename_base}.jsonl",
        "scores": run_dir / f"{filename_base}_scores.jsonl",
        "summary": run_dir / f"{filename_base}_summary.json",
    }


def get_augmented_paths(
    batch_runs_dir: Path,
    run_id: str,
    vision_model: str,
    vision_prompt: str,
    llm_model: str,
    llm_prompt: str,
) -> dict[str, Path]:
    """Get paths for vision + LLM augmentation results.

    Args:
        batch_runs_dir: Path to batch_runs directory.
        run_id: Baseline vision run identifier.
        vision_model: Vision model name.
        vision_prompt: Vision prompt version.
        llm_model: LLM model name for augmentation.
        llm_prompt: LLM prompt version.

    Returns:
        Dict with keys: 'dir', 'results', 'summary'.
    """
    run_dir = get_run_dir(batch_runs_dir, run_id)
    augmented_dir = run_dir / "augmented"
    filename_base = f"vision_{vision_model}_{vision_prompt}_llm_{llm_model}_{llm_prompt}"
    return {
        "dir": augmented_dir,
        "results": augmented_dir / f"{filename_base}.jsonl",
        "summary": augmented_dir / f"{filename_base}_summary.json",
    }


def list_vision_runs(batch_runs_dir: Path) -> list[str]:
    """List all available vision run IDs.

    Args:
        batch_runs_dir: Path to batch_runs directory.

    Returns:
        Sorted list of run IDs (newest last).
    """
    if not batch_runs_dir.exists():
        return []

    runs = []
    for item in batch_runs_dir.iterdir():
        if item.is_dir():
            # Check for any vision_*.jsonl file
            if list(item.glob("vision_*.jsonl")):
                runs.append(item.name)

    return sorted(runs)


# =============================================================================
# JSONL I/O
# =============================================================================


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load records from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of records as dicts.
    """
    if not path.exists():
        logger.warning("File not found: %s", path)
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    return records


def load_jsonl_as_dict(path: Path, key_field: str = "page_id") -> dict[str, dict]:
    """Load JSONL records into a dict keyed by specified field.

    Args:
        path: Path to the JSONL file.
        key_field: Field to use as dict key.

    Returns:
        Dict mapping key_field values to records.
    """
    records = load_jsonl(path)
    return {r[key_field]: r for r in records if key_field in r}


def append_jsonl(path: Path, record: dict | Any) -> None:
    """Append a single record to a JSONL file.

    Args:
        path: Path to the JSONL file.
        record: Record to append (dict or dataclass with asdict).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(record, "__dataclass_fields__"):
        record = asdict(record)

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def write_jsonl(path: Path, records: list[dict | Any]) -> None:
    """Write records to a JSONL file, overwriting if exists.

    Args:
        path: Path to the JSONL file.
        records: List of records to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            if hasattr(record, "__dataclass_fields__"):
                record = asdict(record)
            f.write(json.dumps(record) + "\n")


def get_completed_ids(path: Path, id_field: str = "page_id") -> set[str]:
    """Get set of IDs already processed in a results file.

    Args:
        path: Path to results JSONL file.
        id_field: Field name containing the ID.

    Returns:
        Set of completed IDs.
    """
    if not path.exists():
        return set()

    completed = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                if id_field in record:
                    completed.add(record[id_field])

    return completed


def save_summary(path: Path, summary: dict) -> None:
    """Save summary statistics to JSON file.

    Args:
        path: Path to save the summary JSON.
        summary: Summary dict to save.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
