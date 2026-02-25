"""Shared utilities for runner modules.

Common JSONL I/O and CLI helpers used by batch and augment runners.
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
#   │   ├── ocr_results.jsonl
#   │   ├── score_results.jsonl
#   │   ├── summary.json
#   │   └── augmented/
#   │       ├── {model}_{prompt}_{mode}.jsonl
#   │       └── {model}_{prompt}_{mode}_summary.json
#   └── {run_id}/
#       └── ...


def get_run_dir(batch_runs_dir: Path, run_id: str) -> Path:
    """Get the directory for a specific baseline run.

    Args:
        batch_runs_dir: Path to batch_runs directory.
        run_id: Run identifier (e.g., '20260128_172501').

    Returns:
        Path to the run directory (e.g., batch_runs/20260128_172501/).
    """
    return batch_runs_dir / run_id


def get_baseline_paths(batch_runs_dir: Path, run_id: str) -> dict[str, Path]:
    """Get all baseline file paths for a run.

    Args:
        batch_runs_dir: Path to batch_runs directory.
        run_id: Run identifier.

    Returns:
        Dict with keys: 'dir', 'ocr', 'scores', 'summary'.
    """
    run_dir = get_run_dir(batch_runs_dir, run_id)
    return {
        "dir": run_dir,
        "ocr": run_dir / "ocr_results.jsonl",
        "scores": run_dir / "score_results.jsonl",
        "summary": run_dir / "summary.json",
    }


def get_augmented_paths(
    batch_runs_dir: Path,
    run_id: str,
    model: str,
    prompt: str,
    mode: str,
) -> dict[str, Path]:
    """Get all augmented file paths for a run/model/prompt/mode combination.

    Args:
        batch_runs_dir: Path to batch_runs directory.
        run_id: Baseline run identifier.
        model: Model name (e.g., 'nova-pro').
        prompt: Prompt version (e.g., 'v2').
        mode: Augmentation mode (e.g., 'all').

    Returns:
        Dict with keys: 'dir', 'results', 'summary'.
    """
    run_dir = get_run_dir(batch_runs_dir, run_id)
    augmented_dir = run_dir / "augmented"
    filename_base = f"{model}_{prompt}_{mode}"
    return {
        "dir": augmented_dir,
        "results": augmented_dir / f"{filename_base}.jsonl",
        "summary": augmented_dir / f"{filename_base}_summary.json",
    }


def list_baseline_runs(batch_runs_dir: Path) -> list[str]:
    """List all available baseline run IDs.

    Args:
        batch_runs_dir: Path to batch_runs directory.

    Returns:
        Sorted list of run IDs (newest last).
    """
    if not batch_runs_dir.exists():
        return []

    runs = []
    for item in batch_runs_dir.iterdir():
        if item.is_dir() and (item / "score_results.jsonl").exists():
            runs.append(item.name)

    return sorted(runs)


def list_augmented_runs(batch_runs_dir: Path, run_id: str) -> list[str]:
    """List all augmented run names for a baseline run.

    Args:
        batch_runs_dir: Path to batch_runs directory.
        run_id: Baseline run identifier.

    Returns:
        List of augmented run names (e.g., ['nova-pro_v2_all', 'mistral-7b_v1_all']).
    """
    augmented_dir = get_run_dir(batch_runs_dir, run_id) / "augmented"
    if not augmented_dir.exists():
        return []

    runs = []
    for item in augmented_dir.glob("*.jsonl"):
        runs.append(item.stem)  # e.g., 'nova-pro_v2_all'

    return sorted(runs)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load records from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of record dicts, or empty list if file doesn't exist.
    """
    if not path.exists():
        logger.warning("File not found: %s", path)
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    logger.info("Loaded %d records from %s", len(records), path.name)
    return records


def load_jsonl_as_dict(path: Path, key_field: str = "form_id") -> dict[str, dict[str, Any]]:
    """Load JSONL file into a dict keyed by a field.

    Args:
        path: Path to the JSONL file.
        key_field: Field name to use as dict key.

    Returns:
        Dict mapping key_field values to records.
    """
    records = load_jsonl(path)
    return {r[key_field]: r for r in records if key_field in r}


def write_jsonl(path: Path, records: list[Any]) -> None:
    """Write a list of records to a JSONL file (overwriting).

    Args:
        path: Path to the JSONL file.
        records: List of dicts to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")


def append_jsonl(record: Any, path: Path) -> None:
    """Append a single record to a JSONL file.

    Args:
        record: Dataclass or dict to append.
        path: Path to the JSONL file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert dataclass to dict if needed
    data = asdict(record) if hasattr(record, "__dataclass_fields__") else record

    with open(path, "a", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.write("\n")


def get_completed_ids(path: Path, id_field: str = "form_id") -> set[str]:
    """Get set of IDs already processed in a JSONL file.

    Args:
        path: Path to the JSONL file.
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
                try:
                    record = json.loads(line)
                    if id_field in record:
                        completed.add(record[id_field])
                except json.JSONDecodeError:
                    continue

    if completed:
        logger.info("Found %d already processed records", len(completed))
    return completed
