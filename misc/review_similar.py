"""
review_similar.py
=================
Step 1 of 2 in the glossary extraction pipeline.

Phase 1 – Auto-merges source terms that differ only by case ("Ankle socks" → "ankle socks").
Phase 2 – Detects fuzzy-similar canonical terms (punctuation variants, small edits) and
           presents them for interactive user review.

Saves all decisions to  dedup_decisions.json.
Run export_glossary.py afterwards to produce the final CSV.
"""

import sqlite3
import json
import re
import os
import sys
from collections import defaultdict

DB_PATH = "glossary_candidates.db"
DECISIONS_PATH = "dedup_decisions.json"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def normalize_case(term: str) -> str:
    return term.lower().strip()


_UNITS_PAT = r"cm|mm|m|km|kg|g|mg|ml|l|cl|dl|oz|lb|lbs|in|ft|yd|inch|inches|%"


def is_pure_measurement(term: str) -> bool:
    """Returns True for purely numeric / unit-of-measure terms (no translatable meaning)."""
    t = term.strip()
    if re.match(r"^[\d\s.,x×\-/()]+(?:" + _UNITS_PAT + r")?$", t, re.I):
        return True
    _dim = r"[\d.,]+(?:\s*[x×/]\s*[\d.,]+)*"
    if re.match(rf"^{_dim}(?:\s*(?:{_UNITS_PAT}))?$", t, re.I):
        return True
    if re.match(r"^(?:" + _UNITS_PAT + r")$", t, re.I):
        return True
    return False


def strip_punctuation(term: str) -> str:
    """Remove leading/trailing non-alphanumeric characters."""
    return re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', term).strip()


def levenshtein(a: str, b: str) -> int:
    """Standard Levenshtein edit distance."""
    n, m = len(a), len(b)
    if abs(n - m) > 3:
        return 999  # fast exit – too far apart
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, m + 1):
            temp = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (0 if a[i - 1] == b[j - 1] else 1))
            prev = temp
    return dp[m]


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────

def load_data() -> dict:
    """
    Returns term_data: { source_term -> [ {locale, term, score, freq}, ... ] }
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT source_term, target_locale, target_term, final_score, frequency "
        "FROM candidates"
    )
    rows = cur.fetchall()
    conn.close()

    term_data: dict = defaultdict(list)
    for source_term, target_locale, target_term, final_score, frequency in rows:
        term_data[source_term].append({
            "locale": target_locale,
            "term": target_term,
            "score": final_score or 0.0,
            "freq": frequency or 0,
        })
    return dict(term_data)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 – Case-only deduplication (automatic)
# ──────────────────────────────────────────────────────────────────────────────

def phase1_case_dedup(term_data: dict):
    """
    Groups source terms that differ only by casing.
    Canonical = lowercase form (the actual DB term if it exists, else the
                lowercased string).

    Returns:
        case_canonical_map : { original_term -> canonical_term }  (every term)
        auto_merged_report : list of { canonical, aliases }  (only merged groups)
    """
    # Group all original terms by their lowercase form
    case_groups: dict = defaultdict(list)
    for term in term_data:
        case_groups[normalize_case(term)].append(term)

    case_canonical_map: dict = {}
    auto_merged_report: list = []

    for norm, variants in case_groups.items():
        # Prefer the fully lowercase variant if present, else use the norm string
        if norm in variants:
            canonical = norm
        else:
            # Fallback: pick the most-lowercase-looking variant
            canonical = sorted(variants, key=lambda x: sum(1 for c in x if c.isupper()))[0]

        for v in variants:
            case_canonical_map[v] = canonical

        if len(variants) > 1:
            aliases = [v for v in variants if v != canonical]
            auto_merged_report.append({"canonical": canonical, "aliases": aliases})

    return case_canonical_map, auto_merged_report


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 – Fuzzy similarity detection
# ──────────────────────────────────────────────────────────────────────────────

def phase2_fuzzy_groups(canonical_set: set) -> list:
    """
    Detects pairs/groups of canonical terms that look similar but are not
    identical.  Two detection strategies:

    A) Punctuation stripping – terms that become identical after removing
       leading/trailing non-alphanumeric characters.
       e.g. "(5-pack" → "5-pack"

    B) Levenshtein distance – terms within edit distance 1 (short terms ≤ 8
       chars) or 2 (longer terms).  Uses two sorted passes (forward + reversed)
       to catch both suffix-only and prefix-only differences efficiently.

    Returns a list of group dicts: { type, reason, terms[] }
    """
    terms = sorted(canonical_set, key=str.lower)
    groups: list = []
    seen_pairs: set = set()

    # ── A: Punctuation stripping ──────────────────────────────────────────────
    stripped_map: dict = defaultdict(list)
    for term in terms:
        s = strip_punctuation(term)
        if s and s != term:               # only flag when stripping changed it
            stripped_map[s].append(term)
        else:
            stripped_map[s]               # ensure the key exists (no-op)

    # Also include stripped forms that match an existing clean canonical term
    for s, members in list(stripped_map.items()):
        if s in canonical_set and s not in members:
            members.append(s)
        if len(members) > 1:
            pair_key = tuple(sorted(members))
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                groups.append({
                    "type": "punctuation",
                    "reason": f"Both strip to: \"{s}\"",
                    "terms": list(members),
                })

    # ── B: Levenshtein (sorted forward + reversed) ────────────────────────────
    def lev_pass(sorted_list: list, window: int = 120):
        for i, a in enumerate(sorted_list):
            for j in range(i + 1, min(i + window, len(sorted_list))):
                b = sorted_list[j]
                la, lb = len(a), len(b)
                if abs(la - lb) > 2:
                    continue
                threshold = 1 if max(la, lb) <= 8 else 2
                dist = levenshtein(a.lower(), b.lower())
                if 0 < dist <= threshold:
                    pair_key = tuple(sorted([a, b]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        groups.append({
                            "type": "levenshtein",
                            "reason": f"Edit distance {dist}",
                            "terms": [a, b],
                        })

    print("  Scanning forward-sorted pairs…", end=" ", flush=True)
    lev_pass(terms)
    print("done")

    print("  Scanning reverse-sorted pairs (catches prefix diffs)…", end=" ", flush=True)
    rev_terms = sorted(canonical_set, key=lambda x: x.lower()[::-1])
    lev_pass(rev_terms)
    print("done")

    return groups


# ──────────────────────────────────────────────────────────────────────────────
# Decisions file I/O
# ──────────────────────────────────────────────────────────────────────────────

def load_decisions() -> dict:
    if os.path.exists(DECISIONS_PATH):
        with open(DECISIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"case_canonical_map": {}, "auto_merged_report": [], "decisions": {}}


def save_decisions(data: dict):
    with open(DECISIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────────
# Interactive review
# ──────────────────────────────────────────────────────────────────────────────

def show_term_preview(term: str, term_data: dict, case_canonical_map: dict):
    """Print a compact translation preview for a term."""
    # Collect translations: own translations + any alias translations from Phase 1
    translations: list = list(term_data.get(term, []))

    # Also include translations from case-aliases that map to this canonical
    for original, canonical in case_canonical_map.items():
        if canonical == term and original != term:
            translations.extend(term_data.get(original, []))

    if not translations:
        print("      (no translations found)")
        return

    by_locale: dict = defaultdict(list)
    for t in translations:
        by_locale[t["locale"]].append(t)

    locales = sorted(by_locale.keys())
    total_freq = sum(t["freq"] for t in translations)
    best_score = max(t["score"] for t in translations)

    print(f"      Locales : {', '.join(locales)}")
    print(f"      Freq    : {total_freq}   Best score: {best_score:.4f}")
    for loc in locales:
        best = max(by_locale[loc], key=lambda x: (x["score"], x["freq"]))
        print(f"      {loc:10s}: {best['term']}")


def review_one_group(
    idx: int,
    total: int,
    group: dict,
    term_data: dict,
    case_canonical_map: dict,
) -> dict | None:
    """
    Prompt the user about one similar group.
    Returns a decision dict, or None if skipped.
    """
    terms = group["terms"]
    sep = "=" * 62
    print(f"\n{sep}")
    print(f"  Group {idx + 1}/{total}  [{group['type']}]  {group['reason']}")
    print(sep)

    for i, term in enumerate(terms, 1):
        print(f"\n  [{i}] \"{term}\"")
        show_term_preview(term, term_data, case_canonical_map)

    print()
    print("  Options:")
    for i, term in enumerate(terms, 1):
        print(f"    [{i}] Merge → keep \"{term}\" as canonical")
    print("    [k] Keep all separate (they are genuinely different terms)")
    print("    [s] Skip (decide later)")
    print()

    while True:
        try:
            raw = input("  Choice: ").strip().lower()
        except EOFError:
            raise KeyboardInterrupt

        if raw == "k":
            return {"action": "keep_separate", "terms": terms}
        if raw == "s":
            return None
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(terms):
                canonical = terms[n - 1]
                aliases = [t for t in terms if t != canonical]
                return {
                    "action": "merge",
                    "canonical": canonical,
                    "aliases": aliases,
                    "terms": terms,
                }
        print(f"  ✗ Invalid — enter 1–{len(terms)}, k, or s.")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  Glossary Deduplication Review")
    print("=" * 62)

    # ── Load ──────────────────────────────────────────────────────────────────
    print("\nLoading data from DB…", end=" ", flush=True)
    term_data = load_data()
    print(f"{len(term_data):,} distinct source terms loaded.")

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    print("\nPhase 1 — Case-only deduplication (automatic)…", end=" ", flush=True)
    case_canonical_map, auto_merged_report = phase1_case_dedup(term_data)
    canonical_set = set(case_canonical_map.values())
    n_merged = sum(len(r["aliases"]) for r in auto_merged_report)
    print(
        f"{n_merged} case-variants auto-merged → "
        f"{len(canonical_set):,} canonical terms remain."
    )

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    print("\nPhase 2 — Fuzzy similarity detection…")
    all_groups = phase2_fuzzy_groups(canonical_set)
    # Skip groups where every member is a pure measurement — those are excluded
    # from the glossary entirely, so reviewing them is pointless.
    groups = [g for g in all_groups if not all(is_pure_measurement(t) for t in g["terms"])]
    skipped_meas = len(all_groups) - len(groups)
    print(f"  {len(groups)} similar groups for review "
          f"({skipped_meas} measurement-only groups auto-skipped).")

    # ── Load existing decisions (for resumability) ────────────────────────────
    decisions_data = load_decisions()
    decisions_data["case_canonical_map"] = case_canonical_map
    decisions_data["auto_merged_report"] = auto_merged_report
    save_decisions(decisions_data)   # persist Phase 1 results immediately

    already_reviewed = set(decisions_data.get("decisions", {}).keys())
    pending = [(i, g) for i, g in enumerate(groups) if str(i) not in already_reviewed]

    if not pending:
        print("\n✓ All groups already reviewed!")
        print("  Run:  python export_glossary.py")
        return

    print(
        f"\n  {len(already_reviewed)} groups already reviewed, "
        f"{len(pending)} remaining."
    )
    print("  Tip: Press Ctrl+C at any time — progress is saved after each answer.\n")

    reviewed_this_session = 0
    try:
        for idx, group in pending:
            decision = review_one_group(
                idx, len(groups), group, term_data, case_canonical_map
            )
            if decision is not None:
                decisions_data.setdefault("decisions", {})[str(idx)] = decision
                save_decisions(decisions_data)
            reviewed_this_session += 1
    except KeyboardInterrupt:
        print(f"\n\n  Interrupted. {reviewed_this_session} new decisions saved.")
        print(f"  Resume by running this script again.")
        sys.exit(0)

    save_decisions(decisions_data)
    total_decided = len(decisions_data.get("decisions", {}))
    skipped = len(groups) - total_decided
    print(f"\n✓ Review complete — {total_decided} decisions saved, {skipped} skipped.")
    print("  Run:  python export_glossary.py")


if __name__ == "__main__":
    main()
