"""Diff generation for tracking LLM changes."""

import difflib


def generate_diff(original: str, corrected: str) -> str:
    """Generate a human-readable diff showing changes.

    Uses word-level comparison to show what the LLM changed.

    Args:
        original: Original OCR text.
        corrected: LLM-corrected text.

    Returns:
        String showing word-level changes, e.g.:
        "'balked' -> 'talked'; 'lund' -> 'lunch'"
    """
    if original == corrected:
        return "(no changes)"

    original_words = original.split()
    corrected_words = corrected.split()

    differ = difflib.SequenceMatcher(None, original_words, corrected_words)
    changes = []

    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag == "replace":
            orig = " ".join(original_words[i1:i2])
            new = " ".join(corrected_words[j1:j2])
            changes.append(f"'{orig}' -> '{new}'")
        elif tag == "delete":
            orig = " ".join(original_words[i1:i2])
            changes.append(f"DELETE: '{orig}'")
        elif tag == "insert":
            new = " ".join(corrected_words[j1:j2])
            changes.append(f"INSERT: '{new}'")

    if not changes:
        return "(whitespace only)"

    return "; ".join(changes)
