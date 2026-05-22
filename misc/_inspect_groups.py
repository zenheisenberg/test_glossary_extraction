import sqlite3, json
from collections import defaultdict
import re

DB_PATH = 'glossary_candidates.db'

def normalize_case(term): return term.lower().strip()
def strip_punctuation(term): return re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', term).strip()
def levenshtein(a, b):
    n, m = len(a), len(b)
    if abs(n - m) > 3: return 999
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[0]; dp[0] = i
        for j in range(1, m + 1):
            temp = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (0 if a[i-1] == b[j-1] else 1))
            prev = temp
    return dp[m]

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute('SELECT source_term, target_locale, target_term, final_score, frequency FROM candidates')
rows = cur.fetchall()
conn.close()

term_data = defaultdict(list)
for source_term, target_locale, target_term, final_score, frequency in rows:
    term_data[source_term].append({'locale': target_locale, 'term': target_term, 'score': final_score or 0.0, 'freq': frequency or 0})

case_groups = defaultdict(list)
for term in term_data:
    case_groups[normalize_case(term)].append(term)

case_canonical_map = {}
for norm, variants in case_groups.items():
    canonical = norm if norm in variants else sorted(variants, key=lambda x: sum(1 for c in x if c.isupper()))[0]
    for v in variants:
        case_canonical_map[v] = canonical

canonical_set = set(case_canonical_map.values())
print(f'Canonical set size: {len(canonical_set)}')

# Phase 2: Fuzzy
terms = sorted(canonical_set, key=str.lower)
groups = []
seen_pairs = set()

stripped_map = defaultdict(list)
for term in terms:
    s = strip_punctuation(term)
    if s and s != term:
        stripped_map[s].append(term)
    else:
        stripped_map[s]

for s, members in list(stripped_map.items()):
    if s in canonical_set and s not in members:
        members.append(s)
    if len(members) > 1:
        pair_key = tuple(sorted(members))
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            groups.append({'type': 'punctuation', 'reason': f'Both strip to: "{s}"', 'terms': list(members)})

def lev_pass(sorted_list, window=120):
    for i, a in enumerate(sorted_list):
        for j in range(i+1, min(i+window, len(sorted_list))):
            b = sorted_list[j]
            la, lb = len(a), len(b)
            if abs(la-lb) > 2: continue
            threshold = 1 if max(la,lb) <= 8 else 2
            dist = levenshtein(a.lower(), b.lower())
            if 0 < dist <= threshold:
                pair_key = tuple(sorted([a,b]))
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    groups.append({'type': 'levenshtein', 'reason': f'Edit distance {dist}', 'terms': [a, b]})

lev_pass(terms)
rev_terms = sorted(canonical_set, key=lambda x: x.lower()[::-1])
lev_pass(rev_terms)

print(f'Total groups: {len(groups)}')

# Enrich groups with translation data
def get_translations(term):
    translations = list(term_data.get(term, []))
    for original, canonical in case_canonical_map.items():
        if canonical == term and original != term:
            translations.extend(term_data.get(original, []))
    by_locale = defaultdict(list)
    for t in translations:
        by_locale[t['locale']].append(t)
    result = {}
    for loc, items in by_locale.items():
        best = max(items, key=lambda x: (x['score'], x['freq']))
        result[loc] = {'term': best['term'], 'score': round(best['score'], 4), 'freq': best['freq']}
    total_freq = sum(t['freq'] for t in translations)
    best_score = max((t['score'] for t in translations), default=0)
    return {'locales': result, 'total_freq': total_freq, 'best_score': round(best_score, 4)}

enriched = []
for i, g in enumerate(groups):
    entry = {
        'idx': i,
        'type': g['type'],
        'reason': g['reason'],
        'terms': {}
    }
    for t in g['terms']:
        entry['terms'][t] = get_translations(t)
    enriched.append(entry)

with open('_groups_enriched.json', 'w', encoding='utf-8') as f:
    json.dump(enriched, f, indent=2, ensure_ascii=False)

print('Saved _groups_enriched.json')
print('\nFirst 5 groups:')
print(json.dumps(enriched[:5], indent=2, ensure_ascii=False))
