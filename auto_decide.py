"""
auto_decide.py
==============
Automated decision engine for review_similar.py groups.

Rules:
  PUNCTUATION groups (14 total):
    → Always MERGE, canonical = term without leading/trailing punctuation

  LEVENSHTEIN groups (8199 total):
    → Default: KEEP SEPARATE (conservative - different numbers = different facts)
    
    MERGE exceptions (clear same-term variants):
      1. Hyphen vs space/no-hyphen with same words ("pattern-knitted" vs "pattern knitted")
      2. % suffix present vs absent, SAME numeric value and surrounding words
      3. "contain" vs "contains" (or similar inflection), SAME rest of string
      4. Trailing/leading punctuation difference only (e.g., trailing period)
      5. Mid-length vs midi length type synonyms - handled per known list

Writes output to dedup_decisions.json in the same format review_similar.py expects.
"""

import json
import re
import os
from collections import defaultdict
import sqlite3

DB_PATH = "glossary_candidates.db"
DECISIONS_PATH = "dedup_decisions.json"
GROUPS_PATH = "_groups_enriched.json"

# ── Load existing decisions ────────────────────────────────────────────────────
def load_decisions():
    if os.path.exists(DECISIONS_PATH):
        with open(DECISIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"case_canonical_map": {}, "auto_merged_report": [], "decisions": {}}

def save_decisions(data):
    with open(DECISIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── Load enriched groups ───────────────────────────────────────────────────────
with open(GROUPS_PATH, "r", encoding="utf-8") as f:
    groups = json.load(f)

decisions_data = load_decisions()
already_reviewed = set(decisions_data.get("decisions", {}).keys())
print(f"Groups total: {len(groups)}, already reviewed: {len(already_reviewed)}")

# ── Helpers ────────────────────────────────────────────────────────────────────

def strip_punctuation(term: str) -> str:
    return re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', term).strip()

def has_diff_numbers(a: str, b: str) -> bool:
    """True if a and b contain numbers and those numbers differ."""
    nums_a = re.findall(r'\d+', a)
    nums_b = re.findall(r'\d+', b)
    if not nums_a and not nums_b:
        return False
    return nums_a != nums_b

def normalize_for_compare(term: str) -> str:
    """Normalise term for structural comparison: lowercase, collapse spaces."""
    t = term.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    return t

def is_hyphen_vs_space(a: str, b: str) -> tuple:
    """
    If a and b differ only by hyphen↔space (or hyphen removed), return
    (True, preferred_canonical). Preferred = hyphenated version.
    """
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    # Replace hyphens with spaces and compare
    na_stripped = na.replace('-', ' ')
    nb_stripped = nb.replace('-', ' ')
    if na_stripped == nb_stripped and na != nb:
        # prefer hyphenated
        canonical = a if '-' in a else b
        return True, canonical
    return False, None

def is_percent_vs_no_percent(a: str, b: str) -> tuple:
    """
    If one term has '50%' and the other has '50' (same number, same surrounding words),
    return (True, preferred_canonical). Preferred = % version.
    """
    # Normalise: remove % then compare
    na = normalize_for_compare(a).replace('%', '')
    nb = normalize_for_compare(b).replace('%', '')
    na = re.sub(r'\s+', ' ', na).strip()
    nb = re.sub(r'\s+', ' ', nb).strip()
    if na == nb and '%' in a or '%' in b:
        if na == nb:
            # prefer the % version
            canonical = a if '%' in a else b
            return True, canonical
    return False, None

def is_contain_vs_contains(a: str, b: str) -> tuple:
    """
    If differ only by 'contain' vs 'contains', return (True, canonical='contains' version).
    """
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    # Replace 'contains' → 'contain' in both, then compare
    na2 = re.sub(r'\bcontains\b', 'contain', na)
    nb2 = re.sub(r'\bcontains\b', 'contain', nb)
    if na2 == nb2 and na != nb:
        # keep 'contains' version
        canonical = a if re.search(r'\bcontains\b', a, re.I) else b
        return True, canonical
    return False, None

def is_unit_space_variant(a: str, b: str) -> tuple:
    """'12 cm' vs '12cm' - number followed by space+unit vs number directly touching unit."""
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    na_spaced = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', na)
    nb_spaced = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', nb)
    if na_spaced == nb_spaced and na != nb:
        # Prefer version with space between number and unit
        canonical = a if re.search(r'\d [a-zA-Z]', a) else b
        return True, canonical
    return False, None


def is_trailing_period_only(a: str, b: str) -> tuple:
    """If differ only by trailing period."""
    na = normalize_for_compare(a).rstrip('.')
    nb = normalize_for_compare(b).rstrip('.')
    if na == nb and na != normalize_for_compare(a) or nb != normalize_for_compare(b):
        # keep version without trailing period
        canonical = a if not a.endswith('.') else b
        return True, canonical
    if na == nb:
        canonical = a if not a.endswith('.') else b
        return True, canonical
    return False, None

# Known synonym pairs → merge (lower → preferred canonical)
SYNONYM_PAIRS = {
    frozenset({"mid-length", "midi length"}): "mid-length",
    frozenset({"mid length", "midi length"}): "mid-length",
    frozenset({"polo-neck", "polo neck"}): "polo-neck",
    frozenset({"crew-neck", "crew neck"}): "crew-neck",
    frozenset({"v-neck", "v neck"}): "v-neck",
    frozenset({"round-neck", "round neck"}): "round-neck",
    frozenset({"t-shirt", "tshirt"}): "t-shirt",
}

# ── Decision engine ────────────────────────────────────────────────────────────

stats = {"merge": 0, "keep_separate": 0, "skipped_already": 0}
new_decisions = {}

for g in groups:
    idx = str(g["idx"])
    
    if idx in already_reviewed:
        stats["skipped_already"] += 1
        continue
    
    terms = list(g["terms"].keys())
    gtype = g["type"]
    
    # ── PUNCTUATION groups ────────────────────────────────────────────────────
    if gtype == "punctuation":
        # Canonical = the version that is already stripped (no leading/trailing punct)
        clean_versions = [t for t in terms if strip_punctuation(t) == t]
        if clean_versions:
            canonical = clean_versions[0]
        else:
            # All have leading punct - pick shortest
            canonical = min(terms, key=len)
        
        aliases = [t for t in terms if t != canonical]
        new_decisions[idx] = {
            "action": "merge",
            "canonical": canonical,
            "aliases": aliases,
            "terms": terms,
            "_auto_reason": f"punctuation: clean version = {canonical!r}",
        }
        stats["merge"] += 1
        continue
    
    # ── LEVENSHTEIN groups ────────────────────────────────────────────────────
    assert len(terms) == 2, f"Expected 2 terms in levenshtein group, got {len(terms)}"
    a, b = terms
    
    # Check synonym pairs first
    pair_key = frozenset({normalize_for_compare(a), normalize_for_compare(b)})
    if pair_key in SYNONYM_PAIRS:
        canonical = SYNONYM_PAIRS[pair_key]
        # find actual term matching canonical
        canon_actual = a if normalize_for_compare(a) == canonical else b
        aliases = [t for t in terms if t != canon_actual]
        new_decisions[idx] = {
            "action": "merge",
            "canonical": canon_actual,
            "aliases": aliases,
            "terms": terms,
            "_auto_reason": f"known synonym pair",
        }
        stats["merge"] += 1
        continue
    
    # Check: different numbers → keep separate
    if has_diff_numbers(a, b):
        new_decisions[idx] = {
            "action": "keep_separate",
            "terms": terms,
            "_auto_reason": "different numeric values = different product specs",
        }
        stats["keep_separate"] += 1
        continue
    
    # Check: hyphen vs space
    matched, canonical = is_hyphen_vs_space(a, b)
    if matched:
        aliases = [t for t in terms if t != canonical]
        new_decisions[idx] = {
            "action": "merge",
            "canonical": canonical,
            "aliases": aliases,
            "terms": terms,
            "_auto_reason": "hyphen vs space variant",
        }
        stats["merge"] += 1
        continue
    
    # Check: % vs no %
    matched, canonical = is_percent_vs_no_percent(a, b)
    if matched:
        aliases = [t for t in terms if t != canonical]
        new_decisions[idx] = {
            "action": "merge",
            "canonical": canonical,
            "aliases": aliases,
            "terms": terms,
            "_auto_reason": "percent symbol variant",
        }
        stats["merge"] += 1
        continue
    
    # Check: contain vs contains (same number)
    matched, canonical = is_contain_vs_contains(a, b)
    if matched:
        aliases = [t for t in terms if t != canonical]
        new_decisions[idx] = {
            "action": "merge",
            "canonical": canonical,
            "aliases": aliases,
            "terms": terms,
            "_auto_reason": "contain vs contains morphological variant",
        }
        stats["merge"] += 1
        continue
    
    # Check: unit-space formatting ("12 cm" vs "12cm")
    matched, canonical = is_unit_space_variant(a, b)
    if matched:
        aliases = [t for t in terms if t != canonical]
        new_decisions[idx] = {
            "action": "merge",
            "canonical": canonical,
            "aliases": aliases,
            "terms": terms,
            "_auto_reason": "unit-space formatting variant (N cm vs Ncm)",
        }
        stats["merge"] += 1
        continue

    # Check: trailing period difference only
    matched, canonical = is_trailing_period_only(a, b)
    if matched:
        aliases = [t for t in terms if t != canonical]
        new_decisions[idx] = {
            "action": "merge",
            "canonical": canonical,
            "aliases": aliases,
            "terms": terms,
            "_auto_reason": "trailing period variant",
        }
        stats["merge"] += 1
        continue
    
    # Default: keep separate (conservative)
    new_decisions[idx] = {
        "action": "keep_separate",
        "terms": terms,
        "_auto_reason": "no clear merge rule matched; keeping separate",
    }
    stats["keep_separate"] += 1

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\nDecision summary:")
print(f"  Already reviewed (skipped): {stats['skipped_already']}")
print(f"  New MERGE decisions:        {stats['merge']}")
print(f"  New KEEP_SEPARATE decisions:{stats['keep_separate']}")
print(f"  Total new decisions:        {stats['merge'] + stats['keep_separate']}")

# Show sample of merge decisions for verification
merges = [(idx, d) for idx, d in new_decisions.items() if d["action"] == "merge"]
print(f"\nSample MERGE decisions (first 20):")
for idx, d in merges[:20]:
    reason = d.get("_auto_reason", "")
    terms = d["terms"]
    canonical = d.get("canonical", "?")
    print(f"  [{idx}] {terms[0]!r} -> {terms[1]!r}  | keep: {canonical!r}  ({reason})")

# Breakdown of keep_separate reasons
print(f"\nSample KEEP_SEPARATE decisions (first 10):")
ks = [(idx, d) for idx, d in new_decisions.items() if d["action"] == "keep_separate"]
for idx, d in ks[:10]:
    terms = d["terms"]
    reason = d.get("_auto_reason", "")
    print(f"  [{idx}] {terms[0]!r} vs {terms[1]!r}  ({reason})")

# Ask before writing
print(f"\n{'='*60}")
print(f"Ready to write {len(new_decisions)} decisions to {DECISIONS_PATH}")
ans = input("Write decisions? [y/N]: ").strip().lower()
if ans == 'y':
    decisions_data["decisions"].update(new_decisions)
    save_decisions(decisions_data)
    print(f"Done. {len(decisions_data['decisions'])} total decisions saved.")
else:
    print("Aborted.")
