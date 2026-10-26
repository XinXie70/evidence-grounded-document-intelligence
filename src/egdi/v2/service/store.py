"""SQLite persistence for uploaded documents and question tasks."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    page_count INTEGER NOT NULL,
    low_text_pages INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spend_archive (   -- cost of deleted documents, so the spending cap cannot be reset by deleting
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(id),
    question TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued | running | done | failed
    result TEXT,                   -- JSON: final answer, trace, usage
    error TEXT,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _task(row: sqlite3.Row) -> dict[str, Any]:
    task = dict(row)
    task["result"] = json.loads(task["result"]) if task["result"] else None
    return task


class Store:
    """One short-lived connection per operation, so request threads never share a connection."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)
            # A restart cannot resume a running agent: mark those tasks as interrupted.
            db.execute(
                "UPDATE tasks SET status='failed', error='interrupted by a service restart', finished_at=? "
                "WHERE status IN ('queued','running')",
                (_now(),),
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def _run(self, sql: str, args: tuple = (), *, many: bool = False):
        with closing(self._connect()) as db, db:
            cursor = db.execute(sql, args)
            return cursor.fetchall() if many else (cursor.fetchone() if sql.lstrip().upper().startswith("SELECT") else cursor)

    # documents -------------------------------------------------------------------------
    def add_document(self, doc_id: str, name: str, sha256: str, page_count: int, low_text_pages: int) -> dict[str, Any]:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO documents (id, name, sha256, page_count, low_text_pages, created_at) VALUES (?,?,?,?,?,?)",
                (doc_id, name, sha256, page_count, low_text_pages, _now()),
            )
        return self.get_document(doc_id)

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        row = self._run("SELECT * FROM documents WHERE id=?", (doc_id,))
        return dict(row) if row else None

    def find_by_sha(self, sha256: str) -> dict[str, Any] | None:
        row = self._run("SELECT * FROM documents WHERE sha256=?", (sha256,))
        return dict(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._run("SELECT * FROM documents ORDER BY created_at DESC, id", many=True)]

    # tasks -----------------------------------------------------------------------------
    def create_task(self, doc_id: str, question: str) -> int:
        cursor = self._run(
            "INSERT INTO tasks (doc_id, question, status, created_at) VALUES (?,?, 'queued', ?)",
            (doc_id, question, _now()),
        )
        return cursor.lastrowid

    def mark_running(self, task_id: int) -> None:
        self._run("UPDATE tasks SET status='running' WHERE id=?", (task_id,))

    def finish_task(self, task_id: int, *, status: str, result: dict | None = None, error: str | None = None, cost_usd: float = 0.0) -> None:
        self._run(
            "UPDATE tasks SET status=?, result=?, error=?, cost_usd=?, finished_at=? WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error, cost_usd, _now(), task_id),
        )

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        row = self._run("SELECT * FROM tasks WHERE id=?", (task_id,))
        return _task(row) if row else None

    def list_tasks(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self._run("SELECT * FROM tasks WHERE doc_id=? ORDER BY id DESC", (doc_id,), many=True)
        return [_task(r) for r in rows]

    def has_active_tasks(self, doc_id: str) -> bool:
        row = self._run("SELECT COUNT(*) AS n FROM tasks WHERE doc_id=? AND status IN ('queued','running')", (doc_id,))
        return row["n"] > 0

    def delete_document(self, doc_id: str) -> None:
        """Remove a document and its tasks; the money already spent on them stays in the total."""
        with closing(self._connect()) as db, db:
            spent = db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM tasks WHERE doc_id=?", (doc_id,)).fetchone()[0]
            if spent:
                db.execute("INSERT INTO spend_archive (amount, created_at) VALUES (?,?)", (spent, _now()))
            db.execute("DELETE FROM tasks WHERE doc_id=?", (doc_id,))
            db.execute("DELETE FROM documents WHERE id=?", (doc_id,))

    def total_cost(self) -> float:
        row = self._run(
            "SELECT (SELECT COALESCE(SUM(cost_usd), 0) FROM tasks) + (SELECT COALESCE(SUM(amount), 0) FROM spend_archive) AS total"
        )
        return float(row["total"])
