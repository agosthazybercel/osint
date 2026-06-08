from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    query TEXT NOT NULL,
    mode TEXT NOT NULL,
    target_type TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    confidence_overall TEXT NOT NULL DEFAULT 'unknown',
    html_path TEXT,
    json_path TEXT,
    summary_preview TEXT,
    report_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_searches_created_at ON searches(created_at);
CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query);
"""


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def record_search(report, json_path: str | None = None, html_path: str | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO searches
            (created_at, query, mode, target_type, evidence_count, confidence_overall, html_path, json_path, summary_preview, report_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.created_at or datetime.now().isoformat(timespec="seconds"),
                report.query,
                report.mode,
                report.target_type,
                len(report.evidence),
                report.confidence_overall,
                html_path,
                json_path,
                (report.executive_summary or report.summary or "")[:600],
                json.dumps(report.to_dict(), ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def recent_searches(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, query, mode, target_type, evidence_count, confidence_overall, html_path, json_path, summary_preview FROM searches ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def popular_searches(limit: int = 25) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT query, mode, COUNT(*) AS count, MAX(created_at) AS last_seen
            FROM searches
            GROUP BY LOWER(query), mode
            ORDER BY count DESC, last_seen DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def load_search(search_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
    return dict(row) if row else None
