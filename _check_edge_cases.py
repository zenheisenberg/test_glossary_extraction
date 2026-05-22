"""Check additional edge cases in non-numeric keep_separate."""
import json, re, random

with open('_groups_enriched.json', 'r', encoding='utf-8') as f:
    groups_data = json.load(f)

def has_diff_numbers(a, b):
    nums_a = re.findall(r'\d+', a)
    nums_b = re.findall(r'\d+', b)
    if not nums_a and not nums_b: return False
    return nums_a != nums_b

def normalize_for_compare(term):
    t = term.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    return t

def is_hyphen_vs_space(a, b):
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    if na.replace('-', ' ') == nb.replace('-', ' ') and na != nb:
        return True, a if '-' in a else b
    return False, None

def is_percent_vs_no_percent(a, b):
    na = re.sub(r'\s+', ' ', normalize_for_compare(a).replace('%', '')).strip()
    nb = re.sub(r'\s+', ' ', normalize_for_compare(b).replace('%', '')).strip()
    if na == nb and ('%' in a or '%' in b):
        return True, a if '%' in a else b
    return False, None

def is_contain_vs_contains(a, b):
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    na2 = re.sub(r'\bcontains\b', 'contain', na)
    nb2 = re.sub(r'\bcontains\b', 'contain', nb)
    if na2 == nb2 and na != nb:
        return True, a if re.search(r'\bcontains\b', a, re.I) else b
    return False, None

def is_trailing_period_only(a, b):
    na = normalize_for_compare(a).rstrip('.')
    nb = normalize_for_compare(b).rstrip('.')
    if na == nb:
        return True, a if not a.endswith('.') else b
    return False, None

# Check: "N cm" vs "Ncm" pattern
def is_unit_space_variant(a, b):
    """'12 cm' vs '12cm' - number+space+unit vs number+unit"""
    na = normalize_for_compare(a)
    nb = normalize_for_compare(b)
    # Insert space after number if missing and compare
    na_spaced = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', na)
    nb_spaced = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', nb)
    if na_spaced == nb_spaced and na != nb:
        # Prefer version with space
        canonical = a if re.search(r'\d [a-zA-Z]', a) else b
        return True, canonical
    return False, None

# Now find cases that should be merged but aren't
non_numeric_ks = []
for g in groups_data:
    if g['type'] != 'levenshtein': continue
    terms = list(g['terms'].keys())
    a, b = terms
    if has_diff_numbers(a, b): continue
    if is_hyphen_vs_space(a, b)[0]: continue
    if is_percent_vs_no_percent(a, b)[0]: continue
    if is_contain_vs_contains(a, b)[0]: continue
    if is_trailing_period_only(a, b)[0]: continue
    non_numeric_ks.append((a, b, g))

# Find unit-space variants
unit_space_cases = []
other_ks = []
for a, b, g in non_numeric_ks:
    matched, canonical = is_unit_space_variant(a, b)
    if matched:
        unit_space_cases.append((a, b, canonical, g['terms']))
    else:
        other_ks.append((a, b, g))

print(f"Unit-space variant merges found: {len(unit_space_cases)}")
for a, b, c, td in unit_space_cases[:20]:
    fa = td[a]['total_freq']
    fb = td[b]['total_freq']
    print(f"  {a!r:25s} vs {b!r:25s} -> {c!r}  (freq {fa}/{fb})")

print(f"\nRemaining non-numeric KEEP_SEPARATE: {len(other_ks)}")
print("\nRandom sample of 30:")
random.seed(42)
sample = random.sample(other_ks, min(30, len(other_ks)))
for a, b, g in sample:
    fa = g['terms'][a]['total_freq']
    fb = g['terms'][b]['total_freq']
    print(f"  {a!r:45s} vs {b!r:45s}  ({fa}/{fb})")
