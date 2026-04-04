"""SQLite-backed 任务状态存储（不依赖 Qt / cfg）"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    note_id     TEXT NOT NULL,
    filename    TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    INTEGER NOT NULL DEFAULT 0,
    stage       TEXT NOT NULL DEFAULT '等待中',
    error       TEXT,
    scene       TEXT NOT NULL DEFAULT '通用',
    language    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

# 终态
TERMINAL_STATUSES = {"done", "failed"}


class JobStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            conn.execute(_SCHEMA)
            conn.commit()
            conn.close()

    def create(self, job_id: str, note_id: str, filename: str, scene: str = "通用", language: str = "") -> dict:
        now = datetime.utcnow().isoformat()
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO jobs (job_id,note_id,filename,status,progress,stage,scene,language,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job_id, note_id, filename, "queued", 0, "等待中", scene, language, now, now),
            )
            conn.commit()
            conn.close()
        return self.get(job_id)  # type: ignore[return-value]

    def update(self, job_id: str, **kwargs):
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [job_id]
        with self._lock:
            conn = self._connect()
            conn.execute(f"UPDATE jobs SET {cols} WHERE job_id=?", vals)
            conn.commit()
            conn.close()

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            conn.close()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            conn.close()
        return [dict(r) for r in rows]
