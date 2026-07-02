"""
SQLite database for storing screenshot capture records.
"""

import sqlite3
import sys
from pathlib import Path

# DB path: next to exe when frozen, else in project root
if getattr(sys, "frozen", False):
    DB_PATH = Path.cwd() / "domaincap.db"
else:
    DB_PATH = Path(__file__).resolve().parent / "domaincap.db"


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def get_whois_data(url: str) -> tuple[str, str, str]:
    """
    WHOIS data gathering disabled.
    Returns ("NA", "NA", "NA") for all queries.
    """
    return "NA", "NA", "NA"


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                duration_seconds REAL,
                url TEXT NOT NULL,
                status_code INTEGER,
                os_model TEXT NOT NULL,
                browser_model TEXT NOT NULL,
                screenshot_path TEXT,
                location TEXT,
                domain_ips TEXT,
                ip_geo TEXT
            )
        """)
        for col, col_type in (("duration_seconds", "REAL"), ("location", "TEXT"), ("domain_ips", "TEXT"), ("ip_geo", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE captures ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
        
        # Add WHOIS columns
        for col, col_type in (("domain_registered_date", "TEXT"), ("domain_expiration_date", "TEXT"), ("domain_registrar", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE captures ADD COLUMN {col} {col_type} DEFAULT 'NA'")
            except sqlite3.OperationalError:
                pass
        
        conn.commit()


def insert_capture(
    created_at: str,
    url: str,
    status_code: int | None,
    os_model: str,
    browser_model: str,
    screenshot_path: str | None,
    duration_seconds: float | None = None,
    location: str | None = None,
    domain_ips: str | None = None,
    ip_geo: str | None = None,
    domain_registered_date: str | None = None,
    domain_expiration_date: str | None = None,
    domain_registrar: str | None = None,
):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO captures (created_at, duration_seconds, url, status_code, os_model, browser_model, screenshot_path, location, domain_ips, ip_geo, domain_registered_date, domain_expiration_date, domain_registrar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, duration_seconds, url, status_code, os_model, browser_model, screenshot_path, location, domain_ips, ip_geo, domain_registered_date or "NA", domain_expiration_date or "NA", domain_registrar or "NA"),
        )
        conn.commit()


def delete_capture(capture_id: int) -> tuple[bool, str | None]:
    """Delete a capture by id. Returns (success, screenshot_path)."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT screenshot_path FROM captures WHERE id = ?", (capture_id,)).fetchone()
        if not row:
            return False, None
        path = row["screenshot_path"]
        conn.execute("DELETE FROM captures WHERE id = ?", (capture_id,))
        conn.commit()
        return True, path


def delete_captures_bulk(capture_ids: list[int]) -> tuple[int, list[str]]:
    """Delete multiple captures by ids. Returns (deleted_count, list of screenshot_paths)."""
    if not capture_ids:
        return 0, []
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(capture_ids))
        rows = conn.execute(
            f"SELECT id, screenshot_path FROM captures WHERE id IN ({placeholders})",
            capture_ids,
        ).fetchall()
        paths = [r["screenshot_path"] for r in rows if r["screenshot_path"]]
        ids_found = [r["id"] for r in rows]
        if ids_found:
            ph = ",".join("?" * len(ids_found))
            conn.execute(f"DELETE FROM captures WHERE id IN ({ph})", ids_found)
            conn.commit()
        return len(ids_found), paths


def get_all_captures(limit: int = 500):
    """Return all captures, newest first."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, created_at, duration_seconds, url, status_code, os_model, browser_model, screenshot_path, location, domain_ips, ip_geo, domain_registered_date, domain_expiration_date, domain_registrar
            FROM captures
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_capture(capture_id: int) -> dict | None:
    """Return a single capture by id, or None if not found."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, created_at, duration_seconds, url, status_code, os_model, browser_model, screenshot_path, location, domain_ips, ip_geo, domain_registered_date, domain_expiration_date, domain_registrar FROM captures WHERE id = ?",
            (capture_id,),
        ).fetchone()
        return dict(row) if row else None
