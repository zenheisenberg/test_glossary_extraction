"""Text normalization utilities for fashion/PIM content."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

from config import FASHION_COMPOUNDS


def strip_html(text: str) -> str:
    """Remove HTML tags and return plain text.

    Skips BeautifulSoup entirely when the text contains no ``<`` character,
    avoiding the overhead of a full HTML parse for plain-text content.
    """
    if not text:
        return ""
    if "<" not in text:
        return text
    return BeautifulSoup(text, "html.parser").get_text(" ")


def decode_entities(text: str) -> str:
    """Decode HTML entities like &amp;."""
    if not text:
        return ""
    return html.unescape(text)


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace to single spaces and trim."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalize_fashion_compounds(text: str) -> str:
    """Apply fashion compound regex replacements from config."""
    if not text:
        return ""

    normalized = text
    for pattern, replacement in FASHION_COMPOUNDS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


def normalize_punctuation(text: str) -> str:
    """Standardize punctuation without changing casing."""
    if not text:
        return ""

    normalized = text
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    return normalized


def strip_term_punctuation(term: str) -> str:
    """Strip leading/trailing punctuation, symbols, and non-alphanumeric chars from a term.

    Glossary terms should not start or end with punctuation, delimiters,
    separators, symbols, orthographic marks, or special characters.
    Hyphens are preserved internally (e.g. "T-shirt") but stripped from edges.

    Examples:
        ". cotton"      → "cotton"
        "polyester."    → "polyester"
        ",bomull"       → "bomull"
        "(recycled)"    → "recycled"
        "- jersey -"    → "jersey"
        "100% cotton"   → "100% cotton"  (% is internal, not edge)
    """
    if not term:
        return ""
    # Strip characters that are NOT alphanumeric from both ends.
    # \w matches [a-zA-Z0-9_] — we also want to keep digits and accented chars at edges.
    stripped = re.sub(r'^[^\w]+', '', term)
    stripped = re.sub(r'[^\w]+$', '', stripped)
    # The above keeps underscores; strip those too from edges
    stripped = stripped.strip('_')
    return stripped if stripped else term


def normalize_text(text: str) -> str:
    """Full normalization pipeline for fashion/PIM content."""
    text = strip_html(text)
    text = decode_entities(text)
    text = normalize_whitespace(text)
    text = normalize_fashion_compounds(text)
    text = normalize_punctuation(text)
    return text
