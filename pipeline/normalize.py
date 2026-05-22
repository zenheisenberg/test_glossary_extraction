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


def normalize_text(text: str) -> str:
    """Full normalization pipeline for fashion/PIM content."""
    text = strip_html(text)
    text = decode_entities(text)
    text = normalize_whitespace(text)
    text = normalize_fashion_compounds(text)
    text = normalize_punctuation(text)
    return text
