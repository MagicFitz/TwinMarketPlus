"""Persistent metadata; credentials are deliberately stored elsewhere."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from backend.market_data.errors import MarketError


def now():
    return datetime.now(timezone.utc).isoformat()


class MarketRegistry:
    def __init__(self, settings):
        self.path = settings.registry_path.parent / "market.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sync_jobs (
                    job_id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
                    stage TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
                    error_code TEXT, error TEXT, snapshot_id TEXT, pid INTEGER,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    snapshot_id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS market_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def setting(self, key, default=None):
        with self.connection() as db:
            row = db.execute("SELECT value FROM market_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO market_settings VALUES (?,?)", (key, json.dumps(value)))

    def create_job(self, request):
        stamp, job_id = now(), "sync-" + uuid4().hex[:16]
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # One source, one writer. Also protects overlapping incremental baselines.
            if db.execute("SELECT 1 FROM sync_jobs WHERE status IN ('queued','running')").fetchone():
                raise MarketError("SYNC_JOB_CONFLICT", "已有同步任务正在执行", 409)
            db.execute("INSERT INTO sync_jobs(job_id,request,status,stage,created_at,updated_at) "
                       "VALUES (?,?,'queued','queued',?,?)", (job_id, json.dumps(request), stamp, stamp))
        return self.job(job_id)

    @staticmethod
    def _job(row):
        item = dict(row)
        item["request"] = json.loads(item["request"])
        item["cancel_requested"] = bool(item["cancel_requested"])
        return item

    def job(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM sync_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise MarketError("SYNC_JOB_NOT_FOUND", "同步任务不存在", 404)
        return self._job(row)

    def jobs(self):
        with self.connection() as db:
            return [self._job(row) for row in db.execute("SELECT * FROM sync_jobs ORDER BY created_at DESC LIMIT 30")]

    def update_job(self, job_id, **values):
        allowed = {"status", "stage", "progress", "error_code", "error", "pid", "snapshot_id"}
        if not set(values).issubset(allowed):
            raise ValueError("unsupported job field")
        values["updated_at"] = now()
        with self.connection() as db:
            db.execute("UPDATE sync_jobs SET " + ",".join(key + "=?" for key in values) + " WHERE job_id=?",
                       (*values.values(), job_id))
        return self.job(job_id)

    def claim(self, job_id, pid):
        with self.connection() as db:
            cursor = db.execute("UPDATE sync_jobs SET status='running', pid=?, updated_at=? "
                "WHERE job_id=? AND status='queued' AND cancel_requested=0", (pid, now(), job_id))
            return cursor.rowcount == 1

    def cancel(self, job_id):
        self.job(job_id)
        with self.connection() as db:
            db.execute("UPDATE sync_jobs SET cancel_requested=1, updated_at=?, "
                "status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END "
                "WHERE job_id=? AND status IN ('queued','running')", (now(), job_id))
        return self.job(job_id)

    def snapshots(self):
        active = self.setting("active_snapshot_id")
        with self.connection() as db:
            rows = db.execute("SELECT metadata FROM market_snapshots ORDER BY rowid DESC").fetchall()
        return [{**json.loads(row[0]), "active": json.loads(row[0])["snapshot_id"] == active} for row in rows]

    def snapshot(self, snapshot_id):
        with self.connection() as db:
            row = db.execute("SELECT metadata FROM market_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise MarketError("SNAPSHOT_NOT_FOUND", "市场快照不存在", 404)
        return json.loads(row[0])
