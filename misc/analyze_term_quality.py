"""
analyze_term_quality.py  (v2 - tightened classifiers, false-positives fixed)
==============================================================================
Analyzes glossary source terms and classifies those that are poor candidates
for a PIM translation glossary.

Categories
----------
A  Leading punctuation artifacts    '"BFF#', ', bonded edges', '= 132 mm Size'
B  Standalone filler words          'Perfect', 'Ideal' (single word only)
C  Marketing / filler phrases       'Perfect socks', 'Easy-to-wear summer garment'
D  Care / washing instructions      'Machine wash 40', 'Do not tumble dry'
E  Sentence fragments with comma    'grass, fruit and vegetable stains' (6+ words)
F  Size-chart / body spec data      '109 cm tall, select size', '23/24-15.8 cm'
G  Long phrases (7+ words)          full sentence-like product copy
H  Age / year ranges                '8-14 years', '2-4 years'
"""

import csv, re
from collections import defaultdict

CSV_PATH = "glossary_new.csv"

with open(CSV_PATH, encoding="utf-8-sig") as f:
    rows = list(csv.reader(f))
source_terms = [r[0] for r in rows[1:]]
print(f"Loaded {len(source_terms):,} source terms\n")


# ──────────────────────────────────────────────────────────────────────────────
# Classifiers
# ──────────────────────────────────────────────────────────────────────────────

# A: starts with a non-alphanumeric char that is clearly a parsing artifact
_A = re.compile(r'^[^A-Za-z0-9]')

# B: single-word marketing filler with no terminological value
_FILLER_SINGLES = {
    'perfect', 'ideal', 'great', 'excellent', 'nice', 'comfortable',
    'stylish', 'beautiful', 'gorgeous', 'amazing',
}

# C: multi-word marketing / filler phrase (not real product terminology)
_C = re.compile(
    r'^(perfect\s+\w|easy[\s-]to[\s-]wear|ideal\s+(for|gift|choice)|'
    r'great\s+(for|gift)|this\s+(is|product|item)|these\s+(are|products)|'
    r'sold\s+(separately|together)|not\s+(included|applicable|available))',
    re.I
)

# D: care / laundry instructions
_D = re.compile(
    r'^(machine\s*(wash|washable)|hand\s*(wash|washable)|'
    r'do\s+not\s+(wash|bleach|tumble|iron|wring|dry)|'
    r'tumble\s+dry|dry\s+clean|iron\s+(at|on|low|medium|high|\d)|'
    r'line\s+dry|lay\s+flat|hang\s+to\s+dry|warm\s+wash|cold\s+wash|'
    r'gentle\s+(cycle|wash|program)|wash\s+at\s+\d)',
    re.I
)

# E: sentence fragments with comma and 6+ words, containing a sentence verb
_HAS_COMMA = re.compile(r',')
_SENTENCE_VERB = re.compile(
    r'\b(is|are|was|were|has|have|had|to\s+wear|to\s+use|to\s+keep|'
    r'can\s+be|will\s+be|includes?|contains?|provides?|offers?|ensures?|'
    r'suitable|designed|made\s+to)\b',
    re.I
)

def _is_comma_fragment(t):
    wc = len(t.split())
    if wc < 6:
        return False
    if _HAS_COMMA.search(t) and _SENTENCE_VERB.search(t):
        return True
    if wc >= 9 and _HAS_COMMA.search(t):   # very long comma-joined copy
        return True
    return False

# F: size chart / body measurement data (tight — avoids "100% cotton" false positives)
_F = re.compile(
    # "23/24-15.8 cm", "19/20 -  cm",  digit/digit patterns before unit
    r'^\d+/\d+[\d.,\s\-]*\s*(cm|mm)\b'
    # "109 cm tall, select size" — measurement followed by body/fit word
    r'|\b\d+\s*(cm|mm)\s+(tall|wide|long|height|shoulder|chest|waist|hip|'
    r'inseam|length|size\s*\d|extra\s+chain|select)',
    re.I
)

# G: 7+ words
def _is_long(t):
    return len(t.split()) >= 7

# H: age / year ranges (pure duration with no translation value)
_H = re.compile(r'^\d[\d.,\-]*\s*(year|month|yr|age)s?\b', re.I)


def classify(term):
    flags = []
    if _A.match(term):
        flags.append("A")
    if len(term.split()) == 1 and term.lower() in _FILLER_SINGLES:
        flags.append("B")
    if _C.match(term):
        flags.append("C")
    if _D.match(term):
        flags.append("D")
    if _is_comma_fragment(term):
        flags.append("E")
    if _F.search(term):
        flags.append("F")
    if _is_long(term):
        flags.append("G")
    if _H.match(term):
        flags.append("H")
    return flags


# ──────────────────────────────────────────────────────────────────────────────
# Run & report
# ──────────────────────────────────────────────────────────────────────────────
flagged = {t: classify(t) for t in source_terms if classify(t)}

cat_counts = defaultdict(int)
for flags in flagged.values():
    for f in flags:
        cat_counts[f] += 1

cat_meta = {
    "A": ("A  Leading punctuation artifacts",         "AUTO-EXCLUDE"),
    "B": ("B  Standalone filler / marketing words",   "AUTO-EXCLUDE"),
    "C": ("C  Marketing / filler phrases",            "RECOMMEND EXCLUDE"),
    "D": ("D  Care & washing instructions",           "RECOMMEND EXCLUDE"),
    "E": ("E  Sentence fragments with comma (6+w)",   "REVIEW"),
    "F": ("F  Size-chart / body spec data",           "REVIEW"),
    "G": ("G  Long phrases 7+ words",                 "REVIEW"),
    "H": ("H  Age / year ranges",                     "RECOMMEND EXCLUDE"),
}

print("=" * 74)
print("  PIM GLOSSARY — SOURCE TERM QUALITY ANALYSIS")
print("=" * 74)

total = len(flagged)
print(f"\n  Flagged : {total:,} / {len(source_terms):,} ({100*total/len(source_terms):.1f}%)")
print(f"  Clean   : {len(source_terms)-total:,} / {len(source_terms):,}\n")

for k, (label, action) in cat_meta.items():
    n = cat_counts[k]
    if n:
        print(f"  [{action:20s}]  {label:<44s}  {n:>4}")

# ── Per-category detail ───────────────────────────────────────────────────────
for k, (label, _) in cat_meta.items():
    members = sorted(t for t, f in flagged.items() if k in f)
    if not members:
        continue
    print(f"\n{'─'*74}")
    print(f"  {label}  [{len(members)}]")
    print(f"{'─'*74}")
    for t in members[:35]:
        print(f"    {repr(t)}")
    if len(members) > 35:
        print(f"    ... and {len(members)-35} more")

# ── Word-count distribution ───────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("  Word-count distribution (all terms)")
print(f"{'─'*74}")
wc_dist = defaultdict(int)
for t in source_terms:
    wc_dist[len(t.split())] += 1
for wc in sorted(wc_dist):
    n = wc_dist[wc]
    bar = "#" * min(n // 40, 50)
    pct = 100 * n / len(source_terms)
    print(f"  {wc:2d} word{'s' if wc!=1 else ' '}  {n:>5,}  ({pct:4.1f}%)  {bar}")

# ── Summary buckets ───────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("  ACTION SUMMARY")
print(f"{'─'*74}")
auto_excl = [t for t, f in flagged.items() if any(c in f for c in ['A', 'B'])]
rec_excl  = [t for t, f in flagged.items()
             if any(c in f for c in ['C', 'D', 'H'])
             and not any(c in f for c in ['A', 'B'])]
needs_rev = [t for t, f in flagged.items()
             if any(c in f for c in ['E', 'F', 'G'])
             and not any(c in f for c in ['A', 'B', 'C', 'D', 'H'])]
clean     = [t for t in source_terms if t not in flagged]

print(f"  Auto-exclude  (clear junk / no translation value) : {len(auto_excl):>4}")
print(f"  Recommend exclude (patterns, instructions)        : {len(rec_excl):>4}")
print(f"  Needs your review (borderline)                    : {len(needs_rev):>4}")
print(f"  Clean — keep as-is                                : {len(clean):>4}")
print()
print(f"  Total source terms                                : {len(source_terms):>4}")
