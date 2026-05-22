"""
Term extraction module using spaCy (primary) with KeyBERT/YAKE fallback.

Primary flow:
  1. spaCy noun chunks
  2. spaCy Matcher patterns from domain.patterns
  3. Deduplicate overlapping spans (keep longest)
  4. Filter by word count (1-6) and char length (>= 3)
  5. Classify each term via domain.categories.DOMAIN_TERMS

Fallback (< 3 terms from spaCy):
  KeyBERT top_n=10, then YAKE to supplement.
"""

from __future__ import annotations

import re
from typing import Optional

import spacy
from spacy.matcher import Matcher

from domain.patterns import get_matcher_patterns
from domain.categories import DOMAIN_TERMS

# ---------------------------------------------------------------------------
# Singleton NLP loader
# ---------------------------------------------------------------------------

_nlp_instance: Optional[spacy.language.Language] = None


def load_nlp() -> spacy.language.Language:
    """Load and cache the spaCy en_core_web_md model (singleton)."""
    global _nlp_instance
    if _nlp_instance is None:
        _nlp_instance = spacy.load("en_core_web_md")
    return _nlp_instance


# ---------------------------------------------------------------------------
# Singleton Matcher (Fix #3)
# Rebuilding the Matcher + re-adding all patterns on every extract_terms()
# call was pure overhead. The patterns are static, so the Matcher is built
# once and reused for the lifetime of the process.
# ---------------------------------------------------------------------------

_matcher_instance: Optional[Matcher] = None


def _get_matcher(nlp: spacy.language.Language) -> Matcher:
    """Return the cached spaCy Matcher, building it on first call."""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = Matcher(nlp.vocab)
        pattern_groups = get_matcher_patterns()
        for group_name, patterns in pattern_groups.items():
            # patterns may be a list-of-lists or a single list of token dicts
            if patterns and isinstance(patterns[0], dict):
                patterns = [patterns]
            _matcher_instance.add(group_name, patterns)
    return _matcher_instance


# ---------------------------------------------------------------------------
# Cached KeyBERT / YAKE singletons (Fix #8)
# Both models were instantiated fresh on every fallback call. KeyBERT loads
# a sentence-transformer internally — that's a full model load per call.
# ---------------------------------------------------------------------------

_keybert_instance = None
_yake_instance = None


def _get_keybert():
    """Lazy-load and cache the KeyBERT model (singleton)."""
    global _keybert_instance
    if _keybert_instance is None:
        from keybert import KeyBERT  # type: ignore
        _keybert_instance = KeyBERT()
    return _keybert_instance


def _get_yake():
    """Lazy-load and cache the YAKE extractor (singleton)."""
    global _yake_instance
    if _yake_instance is None:
        import yake  # type: ignore
        _yake_instance = yake.KeywordExtractor(
            lan="en",
            n=4,
            dedupLim=0.7,
            top=15,
        )
    return _yake_instance


# ---------------------------------------------------------------------------
# Domain classification  (Fix #7)
# Previously: O(n×m) scan with seed.lower().strip() recomputed on every call.
# Now: precomputed lookup dict built once at import time → O(1) exact match,
# with substring fallback only when the fast path misses.
# ---------------------------------------------------------------------------

# Precompute normalised seed → domain mapping
_DOMAIN_LOOKUP: dict[str, str] = {
    seed.lower().strip(): domain
    for domain, seeds in DOMAIN_TERMS.items()
    for seed in seeds
}

# Precomputed list of (normalised_seed, domain) for substring fallback
_DOMAIN_SEEDS: list[tuple[str, str]] = [
    (seed.lower().strip(), domain)
    for domain, seeds in DOMAIN_TERMS.items()
    for seed in seeds
]


def classify_domain(term: str) -> tuple[str, str]:
    """
    Classify a term into (domain, category) using DOMAIN_TERMS seed lists.

    Strategy:
      1. O(1) exact match via precomputed lookup dict.
      2. Substring containment scan (term in seed or seed in term) as fallback.
      3. Falls back to ("general", "general").
    """
    normalised = term.lower().strip()

    # Fast path: exact match
    if normalised in _DOMAIN_LOOKUP:
        domain = _DOMAIN_LOOKUP[normalised]
        return (domain, domain)

    # Slow path: substring containment (rare for well-typed terms)
    for seed_norm, domain in _DOMAIN_SEEDS:
        if normalised in seed_norm or seed_norm in normalised:
            return (domain, domain)

    return ("general", "general")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\S+")


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _is_valid_term(text: str) -> bool:
    """Return True if term has 1-6 words and >= 3 characters."""
    stripped = text.strip()
    return len(stripped) >= 3 and 1 <= _word_count(stripped) <= 6


def _span_key(span) -> tuple[int, int]:
    return (span.start_char, span.end_char)


def _deduplicate_spans(spans: list) -> list:
    """
    Remove overlapping spans, keeping the longest one.
    Spans must have .start_char and .end_char attributes.
    """
    if not spans:
        return []

    # Sort by start, then by length descending so longest comes first
    sorted_spans = sorted(spans, key=lambda s: (s.start_char, -(s.end_char - s.start_char)))

    kept: list = []
    last_end = -1

    for span in sorted_spans:
        if span.start_char >= last_end:
            kept.append(span)
            last_end = span.end_char
        else:
            # Overlapping — keep the longer one (already sorted longest-first per start)
            if kept and span.end_char > kept[-1].end_char:
                kept[-1] = span
                last_end = span.end_char

    return kept


def _build_term_dict(text: str, start_char: int, end_char: int) -> dict:
    term = text.strip()
    domain, _category = classify_domain(term)
    return {
        "term": term,
        "normalized_term": term.lower(),
        "domain": domain,
        "start": start_char,
        "end": end_char,
    }


# ---------------------------------------------------------------------------
# Primary extraction
# ---------------------------------------------------------------------------

def extract_terms(text: str, nlp=None) -> list[dict]:
    """
    Extract terms from *text* using spaCy noun chunks + Matcher patterns.

    Parameters
    ----------
    text:
        Input English text.
    nlp:
        Optional pre-loaded spaCy Language object. If None, load_nlp() is called.

    Returns
    -------
    List of dicts with keys: term, normalized_term, domain, start, end.
    Falls back to extract_terms_fallback() if fewer than 3 terms are found.
    """
    if not text or not text.strip():
        return []

    if nlp is None:
        nlp = load_nlp()

    doc = nlp(text)

    # --- 1. Collect noun chunk spans ---
    candidate_spans = list(doc.noun_chunks)

    # --- 2. Apply cached Matcher patterns ---
    matcher = _get_matcher(nlp)
    matches = matcher(doc)
    for _match_id, start, end in matches:
        span = doc[start:end]
        candidate_spans.append(span)

    # --- 3. Deduplicate overlapping spans (keep longest) ---
    unique_spans = _deduplicate_spans(candidate_spans)

    # --- 4. Filter by word count and char length ---
    results: list[dict] = []
    seen_normalised: set[str] = set()

    for span in unique_spans:
        span_text = span.text.strip()
        if not _is_valid_term(span_text):
            continue
        norm = span_text.lower()
        if norm in seen_normalised:
            continue
        seen_normalised.add(norm)
        results.append(_build_term_dict(span_text, span.start_char, span.end_char))

    # --- 5. Fallback if too few terms ---
    if len(results) < 3:
        fallback = extract_terms_fallback(text)
        existing_norms = {r["normalized_term"] for r in results}
        for item in fallback:
            if item["normalized_term"] not in existing_norms:
                results.append(item)
                existing_norms.add(item["normalized_term"])

    return results


# ---------------------------------------------------------------------------
# Fallback extraction
# ---------------------------------------------------------------------------

def extract_terms_fallback(text: str) -> list[dict]:
    """
    Fallback term extraction using KeyBERT (top_n=10) supplemented by YAKE.

    Returns the same dict schema as extract_terms().
    Character offsets are approximated via str.find() since KeyBERT/YAKE
    do not provide them natively.
    """
    if not text or not text.strip():
        return []

    results: list[dict] = []
    seen_norms: set[str] = set()

    # --- KeyBERT ---
    try:
        kw_model = _get_keybert()
        kb_keywords = kw_model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 4),
            stop_words="english",
            top_n=10,
        )
        for phrase, _score in kb_keywords:
            phrase = phrase.strip()
            if not _is_valid_term(phrase):
                continue
            norm = phrase.lower()
            if norm in seen_norms:
                continue
            seen_norms.add(norm)
            start = text.lower().find(norm)
            end = start + len(phrase) if start != -1 else -1
            results.append(_build_term_dict(phrase, max(start, 0), max(end, 0)))
    except ImportError:
        pass  # KeyBERT not installed; continue to YAKE

    # --- YAKE (supplement) ---
    try:
        yake_extractor = _get_yake()
        yake_keywords = yake_extractor.extract_keywords(text)
        for phrase, _score in yake_keywords:
            phrase = phrase.strip()
            if not _is_valid_term(phrase):
                continue
            norm = phrase.lower()
            if norm in seen_norms:
                continue
            seen_norms.add(norm)
            start = text.lower().find(norm)
            end = start + len(phrase) if start != -1 else -1
            results.append(_build_term_dict(phrase, max(start, 0), max(end, 0)))
    except ImportError:
        pass  # YAKE not installed

    return results
