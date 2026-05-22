"""Verify the auto-decisions more carefully - check non-numeric keep_separate cases."""
import json

with open('_groups_enriched.json', 'r', encoding='utf-8') as f:
    groups_data = json.load(f)

# Rebuild decisions (dry run)
import re
from collections import defaultdict

def has_diff_numbers(a, b):
    nums_a = re.findall(r'\d+', a)
    nums_b = re.findall(r'\d+', b)
    if not nums_a and not nums_b:
        return False
    return nums_a != nums_b

def normalize_for_compare(term):
    t = term.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    return t

def strip_punctuation(term):
    return re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', term).strip()

def is_hyphen_vs_space(a, b):
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    na_stripped = na.replace('-', ' ')
    nb_stripped = nb.replace('-', ' ')
    if na_stripped == nb_stripped and na != nb:
        canonical = a if '-' in a else b
        return True, canonical
    return False, None

def is_percent_vs_no_percent(a, b):
    na = normalize_for_compare(a).replace('%', '')
    nb = normalize_for_compare(b).replace('%', '')
    na = re.sub(r'\s+', ' ', na).strip()
    nb = re.sub(r'\s+', ' ', nb).strip()
    if na == nb and ('%' in a or '%' in b):
        canonical = a if '%' in a else b
        return True, canonical
    return False, None

def is_contain_vs_contains(a, b):
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    na2 = re.sub(r'\bcontains\b', 'contain', na)
    nb2 = re.sub(r'\bcontains\b', 'contain', nb)
    if na2 == nb2 and na != nb:
        canonical = a if re.search(r'\bcontains\b', a, re.I) else b
        return True, canonical
    return False, None

def is_trailing_period_only(a, b):
    na = normalize_for_compare(a).rstrip('.')
    nb = normalize_for_compare(b).rstrip('.')
    if na == nb:
        canonical = a if not a.endswith('.') else b
        return True, canonical
    return False, None

# Find all non-numeric keep_separate lev cases
non_numeric_ks = []
merge_non_numeric = []

for g in groups_data:
    if g['type'] != 'levenshtein':
        continue
    terms = list(g['terms'].keys())
    a, b = terms
    
    if has_diff_numbers(a, b):
        continue  # numeric diff - handled
    
    # Check all merge conditions
    if is_hyphen_vs_space(a, b)[0]: 
        merge_non_numeric.append(('hyphen_space', a, b))
        continue
    if is_percent_vs_no_percent(a, b)[0]:
        merge_non_numeric.append(('pct_variant', a, b))
        continue
    if is_contain_vs_contains(a, b)[0]:
        merge_non_numeric.append(('contain_s', a, b))
        continue
    if is_trailing_period_only(a, b)[0]:
        merge_non_numeric.append(('trailing_period', a, b))
        continue
    
    non_numeric_ks.append((a, b, g['terms']))

print(f"Non-numeric KEEP_SEPARATE: {len(non_numeric_ks)}")
print(f"Non-numeric MERGE:         {len(merge_non_numeric)}")

print("\n--- MERGE (non-numeric) sample ---")
for reason, a, b in merge_non_numeric[:15]:
    print(f"  [{reason}] {a!r} vs {b!r}")

print("\n--- KEEP_SEPARATE (non-numeric) sample (50) ---")
import random; random.seed(1)
sample_ks = random.sample(non_numeric_ks, min(50, len(non_numeric_ks)))
for a, b, tdata in sample_ks:
    fa = tdata[a]['total_freq']
    fb = tdata[b]['total_freq']
    print(f"  {a!r:45s} vs {b!r:45s}  (freq {fa} / {fb})")
