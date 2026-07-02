"""Acceptable-term (synonym) generation for relevance evaluation.

Acceptable terms feed the *acceptable-term precision* metric: a returned chunk
counts as acceptable if it contains the search term **or** a semantically
similar term. Rather than hand-curating synonyms per query, this module derives
them automatically from a domain word-vector model.

Design notes
------------
* **Provider is pluggable.** ``generate_acceptable_terms`` delegates to a
  ``SynonymProvider``. The default is :class:`SciSpacySynonymProvider`
  (scispaCy ``en_core_sci_lg`` word vectors), chosen for clinical-domain fit
  over generic word2vec/GloVe. :class:`BedrockSynonymProvider` uses Claude Haiku
  via Amazon Bedrock for higher-quality, context-aware synonyms (handles
  abbreviations, multi-word terms, and domain-specific alternatives).
* **Graceful degradation.** If scispaCy or the model is not installed, the
  provider logs a warning once and returns no synonyms (empty string), so the
  rest of the evaluation still runs — acceptable-term precision simply collapses
  onto plain term precision until the model is available.
* **Deterministic + cached.** The model is loaded lazily once; per-query results
  are memoised so repeated queries (e.g. across chunking strategies) are cheap.

Inspection
----------
Run this module directly to print synonyms for all search terms::

    .venv/bin/python -m evaluation_suite.search_evaluation.relevance.synonym_generator
    .venv/bin/python -m evaluation_suite.search_evaluation.relevance.synonym_generator --provider bedrock
    .venv/bin/python -m evaluation_suite.search_evaluation.relevance.synonym_generator --compare
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

from evaluation_suite.search_evaluation.relevance.term_matching import filter_stop_words

# Claude Haiku 3.5 cross-region inference profile for eu-west-2.
_BEDROCK_DEFAULT_MODEL_ID = "eu.anthropic.claude-3-5-haiku-20241022-v1:0"

logger = logging.getLogger("synonym_generator")

# Default number of similar terms to generate per query.
DEFAULT_SYNONYMS_PER_QUERY = 10

# scispaCy model that ships word vectors (the *_sm model has none).
_SCISPACY_MODEL = "en_core_sci_lg"

_WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z\-]+\b")
_VOWEL_RE = re.compile(r"[aeiou]")


def _is_reasonable_word(text: str) -> bool:
    """Reject obvious junk lexemes from the model vocab.

    ``en_core_sci_lg`` is trained on PubMed text and its vector vocabulary
    contains OCR/garbage tokens (e.g. ``fjwtk``, ``nleas``). We keep only
    tokens that look like real words: alphabetic (a single internal hyphen
    allowed), of sensible length, containing a vowel, and without long runs of
    the same character.
    """
    if not 3 <= len(text) <= 30:
        return False
    core = text.replace("-", "")
    if not core.isalpha():
        return False
    if not _VOWEL_RE.search(text):
        return False
    # Reject 3+ identical consecutive characters (e.g. "aaab").
    if re.search(r"(.)\1\1", text):
        return False
    return True


class SynonymProvider(Protocol):
    """A source of semantically similar terms for a query string."""

    def synonyms(self, query: str, top_n: int) -> list[str]:
        """Return up to ``top_n`` similar terms for ``query`` (may be empty)."""
        ...


def _content_words(query: str) -> list[str]:
    """Extract lower-cased, stop-word-filtered content words from a query.

    Single-letter tokens and pure punctuation are dropped. Stop words are
    removed so synonyms are generated for meaningful terms only (e.g. for
    "Was the applicant in a coma?" only "applicant" and "coma" are expanded).
    """
    words = [w.lower() for w in _WORD_RE.findall(query)]
    return filter_stop_words(words)


class SciSpacySynonymProvider:
    """Generate synonyms from scispaCy ``en_core_sci_lg`` word vectors.

    For each content word in the query we look up its vector and find the
    nearest neighbours in the model's vector table, returning their lexemes.
    Results are de-duplicated, exclude the query's own words, and are capped at
    ``top_n``.
    """

    def __init__(self, model_name: str = _SCISPACY_MODEL) -> None:
        """Initialise with the given spaCy model name (loaded lazily on first use)."""
        self._model_name = model_name
        self._nlp = None  # lazily loaded spaCy pipeline
        self._load_failed = False

    def _ensure_model(self):
        """Load the spaCy model on first use; cache the (possibly failed) result."""
        if self._nlp is not None or self._load_failed:
            return self._nlp
        try:
            import spacy

            self._nlp = spacy.load(self._model_name, exclude=["parser", "ner", "tagger", "lemmatizer"])
        except Exception as exc:  # ImportError or model-not-found
            self._load_failed = True
            logger.warning(
                "scispaCy model '%s' unavailable (%s). Acceptable terms will be empty. "
                "Install with: uv sync --extra evaluation",
                self._model_name,
                exc,
            )
        return self._nlp

    def _similar_words(self, word: str, nlp, n: int) -> list[str]:
        """Return up to ``n`` nearest-neighbour lexeme texts for a single word."""
        import numpy as np

        lex = nlp.vocab[word]
        if not lex.has_vector:
            return []
        vectors = nlp.vocab.vectors
        # Over-fetch then filter junk, so we still return ~n real words.
        keys, _, _ = vectors.most_similar(np.asarray([lex.vector]), n=(n + 1) * 4)
        results: list[str] = []
        for key in keys[0]:
            text = nlp.vocab.strings[key].lower()
            if text != word and _is_reasonable_word(text):
                results.append(text)
            if len(results) >= n:
                break
        return results

    def synonyms(self, query: str, top_n: int) -> list[str]:
        """Return up to ``top_n`` similar terms for ``query`` using word vectors."""
        nlp = self._ensure_model()
        if nlp is None:
            return []

        query_words = _content_words(query)
        if not query_words:
            return []

        # Spread the budget across the query's content words.
        per_word = max(2, top_n // len(query_words) + 1)
        seen: set[str] = set(query_words)
        collected: list[str] = []
        for word in query_words:
            for syn in self._similar_words(word, nlp, per_word):
                if syn not in seen:
                    seen.add(syn)
                    collected.append(syn)
                    if len(collected) >= top_n:
                        return collected
        return collected


# Module-level default provider (lazily loads the model on first real use).
_default_provider: SynonymProvider = SciSpacySynonymProvider()


def set_default_provider(provider: SynonymProvider) -> None:
    """Override the default synonym provider (e.g. inject an LLM or a stub)."""
    global _default_provider
    _default_provider = provider


class BedrockSynonymProvider:
    """Generate synonyms using Amazon Bedrock (Claude Haiku 3.5).

    Compared to the scispaCy word-vector approach, an LLM can handle:

    * Medical abbreviations (CBT → cognitive behavioural therapy, CMHT → community
      mental health team)
    * Multi-word terms (brain injury → traumatic brain injury, TBI)
    * Context-appropriate synonyms rather than pure distributional similarity

    Requires valid AWS credentials (the same ``AWS_MOD_PLATFORM_*`` variables used
    by the ingestion pipeline). Results are cached in memory so repeated calls for
    the same query within a single run are free.

    Args:
        model_id: Bedrock model/inference-profile ID. Defaults to the eu-west-2
            cross-region Claude Haiku 3.5 inference profile.
    """

    def __init__(self, model_id: str = _BEDROCK_DEFAULT_MODEL_ID) -> None:
        """Initialise with the given Bedrock model/inference-profile ID."""
        self._model_id = model_id
        self._client = None  # lazily created
        self._cache: dict[tuple[str, int], list[str]] = {}

    def _get_client(self):
        if self._client is None:
            import boto3

            from ingestion_pipeline.config import settings as ingestion_settings

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=ingestion_settings.AWS_REGION,
                aws_access_key_id=ingestion_settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
                aws_secret_access_key=ingestion_settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
                aws_session_token=ingestion_settings.AWS_MOD_PLATFORM_SESSION_TOKEN or None,
            )
        return self._client

    def synonyms(self, query: str, top_n: int) -> list[str]:
        """Return up to ``top_n`` similar terms for ``query`` via Bedrock."""
        cache_key = (query.lower().strip(), top_n)
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = (
            f'For the medical/legal document search query: "{query}"\n\n'
            f"List up to {top_n} synonymous or related terms that a UK medical or "
            f"legal document about this topic would use. Include abbreviations, "
            f"alternative phrasings, and closely related concepts.\n"
            f"Return ONLY a comma-separated list of terms, no explanations or numbering."
        )

        try:
            client = self._get_client()
            response = client.converse(
                modelId=self._model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 256, "temperature": 0.0},
            )
            raw = response["output"]["message"]["content"][0]["text"].strip()
        except Exception as exc:
            logger.warning("Bedrock synonym call failed for %r: %s", query, exc)
            return []

        terms = [t.strip().lower() for t in raw.split(",") if t.strip()]
        # Drop anything that looks like a sentence (too long or contains newlines).
        terms = [t for t in terms if 2 <= len(t) <= 60 and "\n" not in t][:top_n]
        self._cache[cache_key] = terms
        return terms


def generate_acceptable_terms(
    query: str,
    top_n: int = DEFAULT_SYNONYMS_PER_QUERY,
    provider: SynonymProvider | None = None,
) -> str:
    """Generate a comma-separated list of acceptable (similar) terms for a query.

    Args:
        query: The search phrase.
        top_n: Maximum number of similar terms to return.
        provider: Optional provider override; defaults to the module provider.

    Returns:
        Comma-separated synonyms, or an empty string if none could be generated.
    """
    active = provider or _default_provider
    try:
        terms = active.synonyms(query, top_n)
    except Exception as exc:  # defensive: never let synonym gen break a run
        logger.warning("Synonym generation failed for %r: %s", query, exc)
        return ""
    return ", ".join(terms)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import csv
    import sys
    from pathlib import Path

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    _SEARCH_TERMS_CSV = Path(__file__).resolve().parents[3] / "testing_docs" / "search_terms.csv"

    parser = argparse.ArgumentParser(description="Inspect synonym generation for all search terms.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--provider",
        choices=["scispacy", "bedrock"],
        default="scispacy",
        help="Which provider to use (default: scispacy).",
    )
    group.add_argument(
        "--compare",
        action="store_true",
        help="Show scispaCy and Bedrock side-by-side for every query.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_SYNONYMS_PER_QUERY,
        help=f"Maximum synonyms per query (default: {DEFAULT_SYNONYMS_PER_QUERY}).",
    )
    args = parser.parse_args()

    with open(_SEARCH_TERMS_CSV, newline="") as fh:
        queries = [row["search_term"] for row in csv.DictReader(fh)]

    if args.compare:
        scispacy_p = SciSpacySynonymProvider()
        bedrock_p = BedrockSynonymProvider()
        col_w = 38
        print(f"\n{'QUERY':<35}  {'SCISPACY':<{col_w}}  {'BEDROCK'}")  # noqa: T201
        print("-" * (35 + 2 + col_w + 2 + col_w))  # noqa: T201
        for q in queries:
            sci = generate_acceptable_terms(q, args.top_n, scispacy_p) or "(none)"
            bed = generate_acceptable_terms(q, args.top_n, bedrock_p) or "(none)"
            print(f"{q:<35}  {sci:<{col_w}}  {bed}")  # noqa: T201
    else:
        if args.provider == "bedrock":
            provider_obj: SynonymProvider = BedrockSynonymProvider()
            label = f"Bedrock ({_BEDROCK_DEFAULT_MODEL_ID})"
        else:
            provider_obj = SciSpacySynonymProvider()
            label = f"scispaCy ({_SCISPACY_MODEL})"

        print(f"\nSynonyms via {label}  (top_n={args.top_n})\n")  # noqa: T201
        print(f"{'QUERY':<35}  SYNONYMS")  # noqa: T201
        print("-" * 100)  # noqa: T201
        for q in queries:
            result = generate_acceptable_terms(q, args.top_n, provider_obj) or "(none)"
            print(f"{q:<35}  {result}")  # noqa: T201
