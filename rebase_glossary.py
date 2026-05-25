"""
Rebase a glossary CSV to a different source locale.

Given glossary_export.csv (en, sv-SE, fi-FI, …), produce a new CSV where
the specified locale becomes the source (first column) and all others become
targets.  Rows where the new source column is empty are dropped — there is
nothing to serve as the source term.

Usage:
    python rebase_glossary.py --source sv-SE
    python rebase_glossary.py --source de-DE --in glossary_export.csv --out glossary_sv-SE.csv
"""

import argparse
import csv
import sys
from pathlib import Path

DEFAULT_INPUT = Path("glossary_export.csv")


def rebase(in_path: Path, out_path: Path, new_source: str) -> None:
    with open(in_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        all_rows = list(reader)
        original_cols: list[str] = reader.fieldnames or []

    if new_source not in original_cols:
        print(
            f"ERROR: locale '{new_source}' not found in {in_path}.\n"
            f"Available locales: {', '.join(original_cols)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # New column order: chosen source first, remaining locales after
    target_cols = [col for col in original_cols if col != new_source]
    fieldnames = [new_source] + target_cols

    kept = skipped = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            if not row[new_source].strip():
                skipped += 1
                continue
            writer.writerow({col: row[col] for col in fieldnames})
            kept += 1

    print(f"Input        : {in_path}  ({len(all_rows)} rows)")
    print(f"New source   : {new_source}")
    print(f"Columns      : {', '.join(fieldnames)}")
    print(f"Rows written : {kept}")
    print(f"Rows skipped : {skipped}  (no translation for '{new_source}')")
    print(f"Output       : {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebase a glossary CSV to a different source locale"
    )
    parser.add_argument(
        "--source",
        required=True,
        metavar="LOCALE",
        help="The locale to use as the new source column (e.g. sv-SE)",
    )
    parser.add_argument(
        "--in",
        dest="input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input glossary CSV (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--out",
        dest="output",
        type=Path,
        default=None,
        help="Output CSV path (default: glossary_<source>.csv)",
    )
    args = parser.parse_args()

    out_path = args.output or Path(f"glossary_{args.source}.csv")
    rebase(args.input, out_path, args.source)


if __name__ == "__main__":
    main()
