"""Auto-generate per-query ground truth from the indexed corpus.

Instead of hand-annotating an ``expected_chunk_id`` per query (which is only
valid for one chunking strategy), the set of relevant chunks is derived from the
chunks currently in OpenSearch each run. This keeps ground truth valid for
whatever chunking strategy built the index.

Relevance rules (confirmed with the team):

* **keyword / phrase queries** (<= 4 words, no trailing ``?``):
  a chunk is relevant if it contains **any word** of the phrase.
* **question queries** (5+ words, or ending in ``?``):
  stop words are removed first, then a chunk is relevant if it contains any of
  the remaining content words.

Matching is whole-word and case-insensitive. Dates in queries (e.g.
"28 Jan 2018") keep their numeric/month tokens as content words, so a chunk
mentioning the date is treated as relevant.
"""

from __future__ import annotations

import re

from evaluation_suite.search_evaluation.relevance.term_matching import filter_stop_words

# A phrase is treated as a "question" at or above this word count, or if it
# ends with a question mark.
QUESTION_WORD_THRESHOLD = 5

_TOKEN_RE = re.compile(r"\b\w+\b")


def classify_query(query: str) -> str:
    """Classify a query as ``"question"`` or ``"keyword_phrase"``.

    A query is a question if it ends with ``?`` OR has at least
    ``QUESTION_WORD_THRESHOLD`` words.
    """
    stripped = query.strip()
    word_count = len(_TOKEN_RE.findall(stripped))
    if stripped.endswith("?") or word_count >= QUESTION_WORD_THRESHOLD:
        return "question"
    return "keyword_phrase"


def extract_query_terms(query: str, query_type: str | None = None) -> list[str]:
    """Return the lower-cased content tokens used for relevance matching.

    For keyword/phrase queries every word token is kept. For questions, stop
    words are removed so common words (the, was, did, ...) don't make every
    chunk relevant. Single-character tokens are always dropped.
    """
    if query_type is None:
        query_type = classify_query(query)

    tokens = [t.lower() for t in _TOKEN_RE.findall(query)]
    if query_type == "question":
        tokens = filter_stop_words(tokens)
    return [t for t in tokens if len(t) > 1]


def _chunk_matches(terms: list[str], chunk_text: str) -> bool:
    """True if any term appears as a whole word in the chunk text."""
    text_lower = chunk_text.lower()
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", text_lower):
            return True
    return False


def generate_expected_chunks(
    query: str,
    chunk_lookup: dict[str, str],
    query_type: str | None = None,
) -> list[str]:
    """Derive the relevant chunk IDs for a query from the indexed corpus.

    Args:
        query: The search phrase.
        chunk_lookup: Mapping of chunk_id -> chunk_text for the indexed corpus.
        query_type: Optional pre-computed classification (``"question"`` or
            ``"keyword_phrase"``); computed from the query if omitted.

    Returns:
        Sorted list of chunk IDs whose text satisfies the relevance rule.
        Empty if the query has no usable content terms or nothing matches.
    """
    if query_type is None:
        query_type = classify_query(query)

    terms = extract_query_terms(query, query_type)
    if not terms:
        return []

    matched = [chunk_id for chunk_id, text in chunk_lookup.items() if text and _chunk_matches(terms, text)]
    return sorted(matched)
