"""Filtering helpers for glossary candidates."""

from __future__ import annotations

import re
import string

from config import BLACKLIST, MAX_TERM_WORDS, MIN_TERM_CHARS

_SKU_RE = re.compile(r"^[A-Z0-9\-]{5,}$")
_PURE_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")

_SENTENCE_STARTERS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "because",
    "but",
    "can",
    "do",
    "does",
    "for",
    "from",
    "he",
    "her",
    "here",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "let",
    "may",
    "me",
    "might",
    "my",
    "of",
    "on",
    "or",
    "our",
    "should",
    "so",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
}

_COMMON_STOPWORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "just",
    "let",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
}

_PUNCTUATION_NO_HYPHEN = set(string.punctuation) - {"-"}

# ── Custom domain exclusion patterns ──────────────────────────────────────────
# These generalise the quality issues identified in the Kappahl dataset.
# Each pattern is labelled with the category letter from analyze_term_quality.py.

# A: Leading punctuation artifact — term begins with a non-alphanumeric character
#    e.g. '"BFF#', '(PU', ', bonded edges', '/day', '= 132 mm Size'
_LEADING_PUNCT_RE = re.compile(r"^[^A-Za-z0-9]")

# B: Standalone filler / marketing adjective (single-word terms)
#    e.g. 'Ideal', 'gorgeous'
_STANDALONE_FILLER_WORDS: frozenset = frozenset({
    "ideal", "gorgeous", "perfect", "lovely", "stunning", "amazing",
})

# C: Marketing "Perfect <noun>" and "Easy-to-wear <noun>" phrases
#    — catches "Perfect socks", "Perfect spring jacket", "Easy-to-wear summer garment"
#    — does NOT catch "perfect for …" (already in BLACKLIST) so the negative
#      lookahead (?!for\b) is redundant but harmless
_MARKETING_PHRASE_RE = re.compile(
    r"^(?:perfect\s+(?!for\b)|easy[-\s]to[-\s]wear\b)", re.I
)

# F: Dimension-label spec — a leading number + physical unit + alpha label word
#    e.g. "43 cm height", "4.2 cm Length", "23 cm Shoulder strap", "40 cm wide"
#    Does NOT match pure measurements like "100 cm" (no trailing word) — those
#    are already handled by is_pure_measurement() in export_glossary.py.
_DIM_LABEL_RE = re.compile(
    r"^\d[\d.,]*\s*(?:cm|mm|m|km|kg|g|ml|l|oz|lb|in|ft)\b\s+[A-Za-z]", re.I
)

# H: Age / year ranges  e.g. "3 years", "8-14 years", "12+ years"
_AGE_RANGE_RE = re.compile(r"^\d+(?:[–\-]\d+)?\+?\s+years?\b$", re.I)


def is_valid_candidate(term_dict: dict) -> bool:
    """Return True when the glossary candidate passes filtering rules."""

    term = str(term_dict.get("term", "")).strip()
    if len(term) < MIN_TERM_CHARS:
        return False

    if term.replace(" ", "").isdigit() or _PURE_NUMBER_RE.fullmatch(term):
        return False

    if _SKU_RE.fullmatch(term):
        return False

    lower_term = term.lower()
    if any(blacklist_item.lower() in lower_term for blacklist_item in BLACKLIST):
        return False

    word_count = len(term.split())
    if word_count > MAX_TERM_WORDS:
        return False

    if word_count > 6:
        return False

    if word_count == 1 and lower_term in _COMMON_STOPWORDS:
        return False

    if word_count >= 2 and term.split()[0].lower() in _SENTENCE_STARTERS:
        return False

    punctuation_count = sum(1 for ch in term if ch in _PUNCTUATION_NO_HYPHEN)
    if punctuation_count > 2:
        return False

    # ── Custom domain rules (Kappahl quality categories A / B / C / F / H) ──
    if _LEADING_PUNCT_RE.match(term):
        return False

    if word_count == 1 and lower_term in _STANDALONE_FILLER_WORDS:
        return False

    if _MARKETING_PHRASE_RE.match(term):
        return False

    if _DIM_LABEL_RE.match(term):
        return False

    if _AGE_RANGE_RE.match(term):
        return False

    return True


def filter_candidates(terms: list[dict]) -> list[dict]:
    """Return only valid glossary candidates while preserving input dictionaries."""

    return [term_dict for term_dict in terms if is_valid_candidate(term_dict)]
