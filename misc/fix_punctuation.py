"""One-time cleanup: strip leading/trailing punctuation from source_term and target_term.

Usage:
    python misc/fix_punctuation.py [--dry-run]

This updates the existing glossary_candidates.db in place.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DB_PATH
from pipeline.normalize import strip_term_punctuation


def main():
    parser = argparse.ArgumentParser(description="Fix leading/trailing punctuation in DB terms")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--db", type=str, default=str(DB_PATH), help="Path to DB")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, source_term, target_term, normalized_source, normalized_target FROM candidates"
    ).fetchall()

    updates = []
    for row in rows:
        clean_source = strip_term_punctuation(row["source_term"])
        clean_target = strip_term_punctuation(row["target_term"])

        changed = (clean_source != row["source_term"] or clean_target != row["target_term"])
        if changed:
            updates.append((
                clean_source,
                clean_target,
                clean_source.lower().strip(),
                clean_target.lower().strip(),
                row["id"],
            ))

    print(f"Total rows: {len(rows)}")
    print(f"Rows needing fix: {len(updates)}")

    if args.dry_run:
        print("\n[DRY RUN] Sample of changes (first 20):")
        for clean_src, clean_tgt, _, _, row_id in updates[:20]:
            orig = conn.execute("SELECT source_term, target_term FROM candidates WHERE id=?", (row_id,)).fetchone()
            print(f"  id={row_id}:")
            if clean_src != orig["source_term"]:
                print(f"    source: {orig['source_term']!r} -> {clean_src!r}")
            if clean_tgt != orig["target_term"]:
                print(f"    target: {orig['target_term']!r} -> {clean_tgt!r}")
        print("\nRe-run without --dry-run to apply.")
        conn.close()
        return

    # Apply updates
    with conn:
        conn.executemany(
            """UPDATE candidates
               SET source_term=?, target_term=?, normalized_source=?, normalized_target=?
               WHERE id=?""",
            updates,
        )

    print(f"Updated {len(updates)} rows.")

    # Remove rows where stripping resulted in empty terms (shouldn't happen, but safety)
    with conn:
        deleted = conn.execute(
            "DELETE FROM candidates WHERE source_term = '' OR target_term = ''"
        ).rowcount
    if deleted:
        print(f"Deleted {deleted} rows with empty terms after cleanup.")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
