import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('glossary_candidates.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Find percentage-prefixed terms
cur.execute("""
SELECT source_term, COUNT(*) as cnt, GROUP_CONCAT(DISTINCT target_locale) as locales
FROM candidates
WHERE source_term GLOB '[0-9]*%*'
   OR source_term GLOB '[0-9][0-9]* *'
GROUP BY source_term
ORDER BY cnt DESC
LIMIT 40
""")
print('=== Percentage / number-prefixed source terms ===')
for r in cur.fetchall():
    print(f'  ({r[1]} locales: {r[2]}) {r[0]}')

# Find 'contains' prefixed terms
cur.execute("""
SELECT source_term, target_term, target_locale
FROM candidates
WHERE LOWER(source_term) LIKE 'contains%'
LIMIT 15
""")
print('\n=== contains-prefixed terms ===')
for r in cur.fetchall():
    print(f'  {r[0]} -> {r[1]} | {r[2]}')

# Count of percentage-containing source terms
cur.execute("""
SELECT COUNT(*) FROM candidates
WHERE source_term GLOB '[0-9]*%*'
""")
print(f'\n=== Count of pct-prefixed source terms: {cur.fetchone()[0]}')

# Show the same core concept extracted in multiple polluted forms
cur.execute("""
SELECT source_term, COUNT(*) as cnt
FROM candidates
WHERE LOWER(source_term) LIKE '%recycled polyester%'
GROUP BY source_term
ORDER BY cnt DESC
""")
print('\n=== "recycled polyester" variants ===')
for r in cur.fetchall():
    print(f'  ({r[1]}) {r[0]}')

# Similar for organic cotton
cur.execute("""
SELECT source_term, COUNT(*) as cnt
FROM candidates
WHERE LOWER(source_term) LIKE '%organic cotton%'
GROUP BY source_term
ORDER BY cnt DESC
""")
print('\n=== "organic cotton" variants ===')
for r in cur.fetchall():
    print(f'  ({r[1]}) {r[0]}')

conn.close()
