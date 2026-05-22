import json

with open('_groups_enriched.json', 'r', encoding='utf-8') as f:
    groups = json.load(f)

punct = [g for g in groups if g['type'] == 'punctuation']
lev = [g for g in groups if g['type'] == 'levenshtein']

print(f'Punctuation groups: {len(punct)}')
print(f'Levenshtein groups: {len(lev)}')

# Sample levenshtein groups to understand patterns
import random
random.seed(42)
samples = random.sample(lev, min(40, len(lev)))

for g in samples[:40]:
    terms = list(g['terms'].keys())
    freqs = {t: g['terms'][t]['total_freq'] for t in terms}
    print(f"  {terms[0]!r:40s} vs {terms[1]!r:40s}  | freq: {freqs[terms[0]]} vs {freqs[terms[1]]}")
