"""Simple HTTP server to view glossary_candidates.db via DataTables.

Usage:
    python -m view.server
    Then open http://localhost:8080
"""
import json
import sqlite3
import sys
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH

PORT = 8000

# Column mapping for DataTables ordering
COLUMNS = [
    "id", "status", "source_term", "target_term", "target_locale",
    "domain", "field_origin", "frequency", "labse_score", "final_score",
    "reviewer_notes",
]


class ViewerHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/datatables":
            self._serve_datatables(params)
        elif path == "/api/stats":
            self._serve_stats()
        else:
            self.send_error(404)

    def _serve_html(self):
        html_path = Path(__file__).parent / "index.html"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_path.read_bytes())

    def _serve_datatables(self, params):
        """Handle DataTables server-side processing requests."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # DataTables params
        draw = int(params.get("draw", [1])[0])
        start = int(params.get("start", [0])[0])
        length = int(params.get("length", [50])[0])
        search_value = params.get("search[value]", [""])[0]

        # Custom filters
        status_filter = params.get("status", [""])[0]
        locale_filter = params.get("locale", [""])[0]

        # Ordering
        order_col_idx = int(params.get("order[0][column]", [0])[0])
        order_dir = params.get("order[0][dir]", ["asc"])[0]
        order_col = COLUMNS[order_col_idx] if order_col_idx < len(COLUMNS) else "id"
        order_dir = "ASC" if order_dir == "asc" else "DESC"

        # Total records (unfiltered)
        total_records = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

        # Build filtered query
        where_clauses = []
        binds = []

        if status_filter and status_filter != "all":
            where_clauses.append("status = ?")
            binds.append(status_filter)
        if locale_filter:
            where_clauses.append("target_locale = ?")
            binds.append(locale_filter)
        if search_value:
            where_clauses.append(
                "(source_term LIKE ? OR target_term LIKE ? OR normalized_source LIKE ? OR domain LIKE ?)"
            )
            sv = f"%{search_value}%"
            binds.extend([sv, sv, sv, sv])

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Filtered count
        filtered_count = conn.execute(
            f"SELECT COUNT(*) FROM candidates{where_sql}", binds
        ).fetchone()[0]

        # Data query
        query = f"SELECT * FROM candidates{where_sql} ORDER BY {order_col} {order_dir} LIMIT ? OFFSET ?"
        rows = conn.execute(query, binds + [length, start]).fetchall()
        conn.close()

        # Format response per DataTables spec
        data = {
            "draw": draw,
            "recordsTotal": total_records,
            "recordsFiltered": filtered_count,
            "data": [dict(r) for r in rows],
        }

        self._json_response(data)

    def _serve_stats(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM candidates GROUP BY status"
        ).fetchall()
        stats = {r["status"]: r["cnt"] for r in rows}

        locale_rows = conn.execute(
            "SELECT target_locale, COUNT(*) as cnt FROM candidates GROUP BY target_locale"
        ).fetchall()
        locales = {r["target_locale"]: r["cnt"] for r in locale_rows}

        total = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        conn.close()

        self._json_response({"total": total, "by_status": stats, "by_locale": locales})

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        if "/api/" not in str(args[0]):
            super().log_message(format, *args)


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), ViewerHandler)
    print(f"Glossary Viewer running at http://localhost:{PORT}")
    print(f"Database: {DB_PATH}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()
