"""SQLite database layer for glossary candidates."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_locale TEXT NOT NULL,
    target_locale TEXT NOT NULL,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    normalized_source TEXT NOT NULL,
    normalized_target TEXT NOT NULL,
    domain TEXT,
    category TEXT,
    field_origin TEXT,
    frequency INTEGER DEFAULT 1,
    labse_score REAL,
    final_score REAL,
    status TEXT DEFAULT 'needs_review',
    source_context TEXT,
    target_context TEXT,
    evidence_product_ids TEXT,
    reviewer_notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(source_locale, target_locale, normalized_source, domain)
);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_locale ON candidates(target_locale);
CREATE INDEX IF NOT EXISTS idx_candidates_domain ON candidates(domain);
CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(final_score DESC);
"""


class CandidateDB:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_db()

    def _init_db(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _candidate_to_row(self, candidate: dict, now: str) -> tuple:
        """Serialize a candidate dict to the ordered tuple expected by the upsert SQL."""
        evidence = candidate.get("evidence_product_ids", [])
        if isinstance(evidence, list):
            evidence = json.dumps(evidence)
        return (
            candidate["source_locale"], candidate["target_locale"],
            candidate["source_term"], candidate["target_term"],
            candidate["normalized_source"], candidate["normalized_target"],
            candidate.get("domain"), candidate.get("category"),
            candidate.get("field_origin"), candidate.get("frequency", 1),
            candidate.get("labse_score"), candidate.get("final_score"),
            candidate.get("status", "needs_review"),
            candidate.get("source_context"), candidate.get("target_context"),
            evidence, now, now,
        )

    def upsert_candidate(self, candidate: dict) -> int:
        """Insert or update a candidate. On conflict, increment frequency and update scores."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._candidate_to_row(candidate, now)
        cursor = self.conn.execute("""
            INSERT INTO candidates (
                source_locale, target_locale, source_term, target_term,
                normalized_source, normalized_target, domain, category,
                field_origin, frequency, labse_score, final_score, status,
                source_context, target_context, evidence_product_ids,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_locale, target_locale, normalized_source, domain) DO UPDATE SET
                frequency = frequency + 1,
                labse_score = MAX(labse_score, excluded.labse_score),
                final_score = MAX(final_score, excluded.final_score),
                evidence_product_ids = excluded.evidence_product_ids,
                updated_at = excluded.updated_at
        """, row)
        self.conn.commit()
        return cursor.lastrowid

    def bulk_upsert(self, candidates: list[dict]) -> int:
        """Upsert multiple candidates in a single transaction.

        Previously called upsert_candidate() (and conn.commit()) once per row,
        causing one fsync per candidate. This wraps the entire batch in one
        transaction — orders of magnitude fewer commits for large batches.
        """
        if not candidates:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        rows = [self._candidate_to_row(c, now) for c in candidates]

        with self.conn:  # single transaction; auto-commits on exit, rolls back on error
            self.conn.executemany("""
                INSERT INTO candidates (
                    source_locale, target_locale, source_term, target_term,
                    normalized_source, normalized_target, domain, category,
                    field_origin, frequency, labse_score, final_score, status,
                    source_context, target_context, evidence_product_ids,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_locale, target_locale, normalized_source, domain) DO UPDATE SET
                    frequency = frequency + 1,
                    labse_score = MAX(labse_score, excluded.labse_score),
                    final_score = MAX(final_score, excluded.final_score),
                    evidence_product_ids = excluded.evidence_product_ids,
                    updated_at = excluded.updated_at
            """, rows)

        return len(rows)

    def get_candidates(self, status: str = None, target_locale: str = None,
                       domain: str = None, min_score: float = None,
                       limit: int = 500) -> list[dict]:
        """Retrieve candidates with optional filters."""
        query = "SELECT * FROM candidates WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if target_locale:
            query += " AND target_locale = ?"
            params.append(target_locale)
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if min_score is not None:
            query += " AND final_score >= ?"
            params.append(min_score)
        query += " ORDER BY final_score DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get summary statistics."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM candidates GROUP BY status"
        ).fetchall()
        stats = {r["status"]: r["cnt"] for r in rows}
        total = self.conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        stats["total"] = total
        return stats

    def update_status(self, candidate_id: int, status: str, notes: str = None):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE candidates SET status=?, reviewer_notes=?, updated_at=? WHERE id=?",
            (status, notes, now, candidate_id)
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
