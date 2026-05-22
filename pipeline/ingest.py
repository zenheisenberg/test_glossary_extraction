"""Excel ingestion for Kappahl PIM glossary pairing."""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

import pandas as pd

from config import EXCEL_PATH, FIELD_WEIGHTS, SOURCE_LOCALE, TARGET_LOCALES

FIELDS = tuple(FIELD_WEIGHTS.keys())
SOURCE_SUFFIX = f"_{SOURCE_LOCALE}"
SKIP_LOCALES = {"en-US"}


def _resolve_excel_path(path: str | Path | None) -> Path:
    if path is None:
        path = EXCEL_PATH
    candidate = Path(path)

    if candidate.exists() and candidate.is_file():
        return candidate

    if any(ch in str(path) for ch in "*?[]"):
        matches = [Path(p) for p in glob.glob(str(path))]
        if matches:
            return matches[0]

    if candidate.is_dir():
        matches = [Path(p) for p in glob.glob(str(candidate / "*.xlsx"))]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            expected_name = Path(EXCEL_PATH).name
            for match in matches:
                if match.name == expected_name:
                    return match
            return matches[0]

    parent = candidate.parent if candidate.parent != Path("") else Path.cwd()
    expected_name = candidate.name or Path(EXCEL_PATH).name
    matches = [Path(p) for p in glob.glob(str(parent / "*.xlsx"))]
    for match in matches:
        if match.name == expected_name:
            return match

    return candidate


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def load_excel(path: str | Path = EXCEL_PATH) -> pd.DataFrame:
    """Read the Item sheet from the configured Excel workbook."""
    excel_path = _resolve_excel_path(path)
    return pd.read_excel(excel_path, sheet_name="Item", engine="openpyxl")


def get_field_locale_pairs(df: pd.DataFrame) -> list[dict[str, str]]:
    """Pair English source text with each target locale text."""
    pairs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for _, row in df.iterrows():
        product_id = _clean_text(row.get("sys_id"))
        entity_type = _clean_text(row.get("sys_entitytype"))
        if not product_id or not entity_type:
            continue

        for field in FIELDS:
            source_col = f"{field}{SOURCE_SUFFIX}"
            source_text = _clean_text(row.get(source_col))
            if not source_text:
                continue

            for locale in TARGET_LOCALES:
                if locale in SKIP_LOCALES:
                    continue

                target_col = f"{field}_{locale}"
                target_text = _clean_text(row.get(target_col))
                if not target_text:
                    continue

                dedupe_key = (field, source_text, target_text)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                pairs.append(
                    {
                        "product_id": product_id,
                        "entity_type": entity_type,
                        "field": field,
                        "source_locale": SOURCE_LOCALE,
                        "source_text": source_text,
                        "target_locale": locale,
                        "target_text": target_text,
                    }
                )

    return pairs
