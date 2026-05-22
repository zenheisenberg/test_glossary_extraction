import sqlite3, json
conn = sqlite3.connect('glossary_candidates.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Stats
cur.execute("SELECT status, COUNT(*) as cnt FROM candidates GROUP BY status")
print('=== Status breakdown ===')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]}')

cur.execute('SELECT COUNT(*) FROM candidates')
print(f'  TOTAL: {cur.fetchone()[0]}')

# Domain breakdown
cur.execute("SELECT domain, COUNT(*) as cnt FROM candidates GROUP BY domain ORDER BY cnt DESC LIMIT 15")
print('\n=== Domain breakdown ===')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]}')

# Locale breakdown
cur.execute("SELECT target_locale, COUNT(*) as cnt FROM candidates GROUP BY target_locale")
print('\n=== Locale breakdown ===')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]}')

# Score distribution
cur.execute('SELECT MIN(final_score), MAX(final_score), AVG(final_score) FROM candidates')
r = cur.fetchone()
print(f'\n=== Scores === min:{r[0]:.3f} max:{r[1]:.3f} avg:{r[2]:.3f}')

# Sample rows - top approved
cur.execute('SELECT source_term, target_term, target_locale, domain, field_origin, labse_score, final_score, status FROM candidates ORDER BY final_score DESC LIMIT 20')
print('\n=== Top 20 candidates ===')
for r in cur.fetchall():
    print(f'  [{r[7]}] score={r[6]:.3f} labse={r[5]:.3f} | {r[0]} -> {r[1]} | {r[2]} | {r[3]} | {r[4]}')

# Sample needs_review
cur.execute("SELECT source_term, target_term, target_locale, domain, labse_score, final_score FROM candidates WHERE status='needs_review' ORDER BY final_score DESC LIMIT 10")
print('\n=== Sample needs_review ===')
for r in cur.fetchall():
    print(f'  score={r[5]:.3f} labse={r[4]:.3f} | {r[0]} -> {r[1]} | {r[2]} | {r[3]}')

# Sample noisy ones
cur.execute("SELECT source_term, target_term, target_locale, domain, labse_score, final_score FROM candidates WHERE final_score < 0.6 LIMIT 10")
print('\n=== Low score samples ===')
for r in cur.fetchall():
    print(f'  score={r[5]:.3f} labse={r[4]:.3f} | {r[0]} -> {r[1]} | {r[2]} | {r[3]}')

conn.close()
