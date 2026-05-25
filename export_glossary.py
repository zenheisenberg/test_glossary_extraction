"""
Export a glossary CSV from approved + phase2_verbatim_entry candidates
with a LaBSE score >= 0.85.

Output format:
    <source_locale>,<target_locale_1>,<target_locale_2>,...
    <source_term>,<translation_1>,<translation_2>,...

Usage:
    python export_glossary.py [--db PATH] [--out PATH] [--min-score FLOAT]
"""

import argparse
import csv
import sqlite3
from pathlib import Path

from config import DB_PATH, SOURCE_LOCALE, TARGET_LOCALES, LABSE_STRONG

# Statuses considered "good enough" for the glossary
INCLUDE_STATUSES = ("approved", "phase2_verbatim_entry")


def fetch_candidates(db_path: Path, min_score: float) -> list[dict]:
    """Return all qualifying rows as a list of dicts."""
    placeholders = ",".join("?" * len(INCLUDE_STATUSES))
    query = f"""
        SELECT source_term, target_locale, target_term
        FROM   candidates
        WHERE  status IN ({placeholders})
          AND  labse_score >= ?
        ORDER  BY source_term, target_locale
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(query, (*INCLUDE_STATUSES, min_score))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def pivot(rows: list[dict], target_locales: list[str]) -> list[dict]:
    """
    Pivot from (source_term, target_locale, target_term) rows into one
    dict per source_term with a key per target locale.

    When a source_term has multiple translations for the same locale
    (shouldn't normally happen after dedup, but just in case) the first
    one encountered wins.
    """
    pivoted: dict[str, dict] = {}
    for row in rows:
        src = row["source_term"]
        if src not in pivoted:
            pivoted[src] = {loc: "" for loc in target_locales}
        loc = row["target_locale"]
        if loc in pivoted[src] and not pivoted[src][loc]:
            pivoted[src][loc] = row["target_term"]
    return [
        {SOURCE_LOCALE: src, **translations}
        for src, translations in pivoted.items()
    ]


def write_csv(records: list[dict], out_path: Path, target_locales: list[str]) -> None:
    fieldnames = [SOURCE_LOCALE] + target_locales
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export approved glossary to CSV")
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to SQLite DB (default: {DB_PATH})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("glossary_export.csv"),
        help="Output CSV path (default: glossary_export.csv)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=LABSE_STRONG,
        help=f"Minimum LaBSE score (default: {LABSE_STRONG})",
    )
    args = parser.parse_args()

    print(f"DB          : {args.db}")
    print(f"Output      : {args.out}")
    print(f"Min score   : {args.min_score}")
    print(f"Statuses    : {INCLUDE_STATUSES}")
    print()

    rows = fetch_candidates(args.db, args.min_score)
    print(f"Qualifying rows  : {len(rows)}")

    records = pivot(rows, TARGET_LOCALES)
    print(f"Unique source terms: {len(records)}")

    write_csv(records, args.out, TARGET_LOCALES)
    print(f"Written -> {args.out}")


if __name__ == "__main__":
    main()
