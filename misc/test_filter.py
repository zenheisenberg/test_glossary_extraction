from pipeline.filter import filter_candidates, _strip_numeric_prefix, _PURE_MEASUREMENT_RE

# --- _strip_numeric_prefix ---
cases = [
    ('95% organic cotton', 'organic cotton'),
    ('82 recycled polyester', 'recycled polyester'),
    ('100% recycled polyester lining', 'recycled polyester lining'),
    ('organic cotton', 'organic cotton'),
    ('soft organic cotton', 'soft organic cotton'),
]
print('=== _strip_numeric_prefix ===')
for inp, expected in cases:
    got = _strip_numeric_prefix(inp)
    ok = got == expected
    print(f'  {"OK" if ok else "FAIL"}  {inp!r} -> {got!r}')

# --- _PURE_MEASUREMENT_RE ---
should_match = ['95 cm', '98.5 cm', '73x73 cm', '125.00 cm', '44.5 cm', '24x24 cm']
should_not = ['recycled polyester', '44-54 cm head circumference', 'organic cotton', '95% organic cotton']
print('\n=== _PURE_MEASUREMENT_RE (should match) ===')
for t in should_match:
    m = _PURE_MEASUREMENT_RE.fullmatch(t)
    print(f'  {"MATCH" if m else "NO-MATCH FAIL"}: {t!r}')
print('=== _PURE_MEASUREMENT_RE (should NOT match) ===')
for t in should_not:
    m = _PURE_MEASUREMENT_RE.fullmatch(t)
    print(f'  {"NO-MATCH" if not m else "MATCH FAIL"}: {t!r}')

# --- filter_candidates end-to-end ---
def make(term):
    return {'term': term, 'normalized_term': term.lower(), 'domain': 'materials', 'start': 0, 'end': len(term)}

test_terms = [make(t) for t in [
    '95% organic cotton',
    '82 recycled polyester',
    'organic cotton',
    'contains 95 organic cotton',
    'contain 82 recycled polyester',
    'made of recycled polyester',
    '95 cm',
    '73x73 cm',
    'recycled polyester lining',
    '100% recycled polyester lining',
    'soft organic cotton',
]]

filtered = filter_candidates(test_terms)
print('\n=== filter_candidates output (expected: organic cotton, recycled polyester, recycled polyester lining, soft organic cotton) ===')
for t in filtered:
    print(f'  {t["term"]!r}')
