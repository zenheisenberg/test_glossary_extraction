"""
export_glossary.py
==================
Step 2 of 2 in the glossary extraction pipeline.

Reads  dedup_decisions.json  (produced by review_similar.py), applies all
deduplication decisions, then pivots the data into a translation glossary CSV.

Output format
-------------
en,sv-SE,fi-FI,de-DE,nb-NO,pl-PL
5-pack,5-pack,5 paria,...,...,...

Rules
-----
- One row per unique (canonical) source term.
- Columns are: en  +  all distinct target locales (sorted).
- When multiple candidate translations exist for the same (source, locale)
  after merging, the one with the highest final_score wins
  (tie-broken by frequency DESC).
- Rows where EVERY target locale is empty are excluded.
- Rows with at least one translation are included; empty locales stay blank.
- Output is sorted alphabetically by source term (case-insensitive).
"""

import sqlite3
import json
import csv
import os
import re
from collections import defaultdict

DB_PATH = "glossary_candidates.db"
DECISIONS_PATH = "dedup_decisions.json"
OUTPUT_PATH = "glossary.csv"

# Locale column order in the output
TARGET_LOCALES = ["sv-SE", "fi-FI", "de-DE", "nb-NO", "pl-PL"]

_UNITS_PAT = r"cm|mm|m|km|kg|g|mg|ml|l|cl|dl|oz|lb|lbs|in|ft|yd|inch|inches|%"

# ── Quality exclusions ────────────────────────────────────────────────────────
# Terms flagged by analyze_term_quality.py (categories A–H) and approved for
# exclusion. Matched case-insensitively against the final canonical source term.
QUALITY_EXCLUSIONS: frozenset = frozenset({
    # A: Leading punctuation artifacts (parsing junk)
    '"bff#',
    '"la dolce vita',
    '"more amor por favour',
    '"more amor por favour" print',
    '"more espresso',
    '"more espresso" print',
    '"pomodori',
    '"pomodori" print',
    '"saint germain" embroidered text',
    '"today',
    '"today" print',
    '% lenzing',
    '(pu',
    ', bonded edges',
    '/ solid colour coat',
    '/day',
    '= 132 mm size',
    '= 139 mm size',
    # B: Standalone filler / marketing words
    'ideal',
    'gorgeous',
    # C: Marketing / filler phrases
    'easy-to-wear summer garment',
    'perfect comfortable joggers',
    'perfect leggings',
    'perfect pyjama tank top',
    'perfect shorts',
    'perfect socks',
    'perfect spring jacket',
    'perfect protection',
    # F: Size-chart / body spec data
    '109 cm tall, select size',
    '13 cm height',
    '19 cm extra chain',
    '23 cm shoulder strap',
    '4.2 cm length',
    '40 cm wide',
    '40 cm wide 32',
    '43 cm height',
    '43 cm height 38',
    'two 55 cm long handles',
    'width 43 cm height',
    # H: Age / year ranges
    '3 years',
    '8-14 years',
})


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def normalize_case(term: str) -> str:
    return term.lower().strip()


def is_pure_measurement(term: str) -> bool:
    """
    Returns True when the source term carries no translatable meaning —
    i.e. it is purely a number, dimension, percentage, or unit of measure.

    Examples that return True:
        '100 cm', '82%', '60x60', '18x25 cm', '180 80 cm', '12 x'
    Examples that return False:
        '10,000 mm water column', '23 cm Shoulder strap', 'width cm', '5-pack'
    """
    t = term.strip()
    # purely numeric / operator characters + optional trailing unit
    if re.match(r"^[\d\s.,x×\-/()]+(?:" + _UNITS_PAT + r")?$", t, re.I):
        return True
    # dimension expression (NxN or N) + optional unit  →  '100 cm', '18x25 cm', '82%'
    _dim = r"[\d.,]+(?:\s*[x×/]\s*[\d.,]+)*"
    if re.match(rf"^{_dim}(?:\s*(?:{_UNITS_PAT}))?$", t, re.I):
        return True
    # bare unit token only
    if re.match(r"^(?:" + _UNITS_PAT + r")$", t, re.I):
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Load raw data
# ──────────────────────────────────────────────────────────────────────────────

def load_raw_rows() -> list:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT source_term, target_locale, target_term, final_score, frequency "
        "FROM candidates"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Build full canonical map from decisions file
# ──────────────────────────────────────────────────────────────────────────────

def build_canonical_map(decisions_data: dict) -> dict:
    """
    Returns a dict: original_source_term -> final_canonical_term

    Resolution order:
      1. Phase 1 case map  (from review_similar.py auto-merge)
      2. Phase 2 user merge decisions
    """
    # Phase 1: case_canonical_map is { original -> canonical }
    cmap: dict = dict(decisions_data.get("case_canonical_map", {}))

    # Phase 2: user decisions
    for decision in decisions_data.get("decisions", {}).values():
        if decision["action"] != "merge":
            continue
        canonical = decision["canonical"]
        for alias in decision.get("aliases", []):
            # aliases are canonical-form terms (lowercase after Phase 1)
            # map them to the chosen canonical
            cmap[alias] = canonical
            # also make sure the alias's original-case variants point to canonical
            # (they already do via the Phase 1 map → Phase 2 chain below)

    return cmap


def resolve_canonical(source_term: str, cmap: dict) -> str:
    """
    Resolve a raw source_term to its final canonical form.

    Chain: original → (Phase1 map) → phase1_canonical → (Phase2 map if any)
    """
    # Step 1: apply Phase 1 (case normalisation)
    step1 = cmap.get(source_term, normalize_case(source_term))

    # Step 2: apply Phase 2 user merge decisions (stored by alias = phase1 canonical)
    step2 = cmap.get(step1, step1)

    return step2


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Glossary CSV Export")
    print("=" * 60)

    # ── Load decisions ────────────────────────────────────────────────────────
    if not os.path.exists(DECISIONS_PATH):
        print(
            f"\nWARNING: {DECISIONS_PATH} not found.\n"
            "  Run  review_similar.py  first to review similar terms.\n"
            "  Proceeding with case-deduplication only.\n"
        )
        decisions_data: dict = {"case_canonical_map": {}, "decisions": {}}
    else:
        with open(DECISIONS_PATH, "r", encoding="utf-8") as f:
            decisions_data = json.load(f)
        print(
            f"\nLoaded decisions: "
            f"{len(decisions_data.get('decisions', {}))} user decisions, "
            f"{len(decisions_data.get('case_canonical_map', {}))} case-dedup entries."
        )

    cmap = build_canonical_map(decisions_data)

    # Count how many merge decisions came from Phase 2
    merge_count = sum(
        1 for d in decisions_data.get("decisions", {}).values()
        if d["action"] == "merge"
    )
    print(f"  Phase 2 merges applied: {merge_count}")

    # ── Load raw rows ─────────────────────────────────────────────────────────
    print("\nLoading translations from DB…", end=" ", flush=True)
    raw_rows = load_raw_rows()
    print(f"{len(raw_rows):,} rows.")

    # ── Build translation map  ────────────────────────────────────────────────
    # canonical_term -> locale -> [ {term, score, freq} ]
    trans_map: dict = defaultdict(lambda: defaultdict(list))

    for source_term, target_locale, target_term, final_score, frequency in raw_rows:
        if not target_term or not target_term.strip():
            continue
        canonical = resolve_canonical(source_term, cmap)
        trans_map[canonical][target_locale].append({
            "term": target_term.strip(),
            "score": final_score or 0.0,
            "freq": frequency or 0,
        })

    print(f"  {len(trans_map):,} unique canonical source terms after deduplication.")

    # ── Pivot to rows ─────────────────────────────────────────────────────────
    output_rows: list = []
    skipped_no_translation = 0
    skipped_measurement = 0
    skipped_quality = 0

    for canonical_term in sorted(trans_map.keys(), key=str.lower):
        if is_pure_measurement(canonical_term):
            skipped_measurement += 1
            continue

        if canonical_term.lower() in QUALITY_EXCLUSIONS:
            skipped_quality += 1
            continue

        locale_map = trans_map[canonical_term]

        row = [canonical_term]
        has_any = False

        for locale in TARGET_LOCALES:
            candidates = locale_map.get(locale, [])
            if candidates:
                best = max(candidates, key=lambda x: (x["score"], x["freq"]))
                row.append(best["term"])
                has_any = True
            else:
                row.append("")

        if has_any:
            output_rows.append(row)
        else:
            skipped_no_translation += 1

    # ── Write CSV ─────────────────────────────────────────────────────────────
    header = ["en"] + TARGET_LOCALES
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(output_rows)

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n✓ Written {len(output_rows):,} rows to {OUTPUT_PATH}")
    print(f"  Columns : {', '.join(header)}")
    if skipped_measurement:
        print(f"  Skipped : {skipped_measurement} pure-measurement terms")
    if skipped_quality:
        print(f"  Skipped : {skipped_quality} quality-flagged terms (A–H categories)")
    if skipped_no_translation:
        print(f"  Skipped : {skipped_no_translation} terms with no translations at all")

    print("\nTranslation coverage:")
    for i, loc in enumerate(TARGET_LOCALES):
        count = sum(1 for r in output_rows if r[i + 1])
        pct = count / len(output_rows) * 100 if output_rows else 0
        bar = "█" * int(pct / 5)
        print(f"  {loc:8s}  {count:>6,} / {len(output_rows):,}  ({pct:5.1f}%)  {bar}")


if __name__ == "__main__":
    main()
