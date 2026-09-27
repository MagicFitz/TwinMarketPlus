"""SQLite-backed Run Registry and lifecycle transition rules."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUSES = frozenset(("draft", "queued", "running", "stopping", "completed", "failed", "cancelled"))
HEALTH = frozenset(("healthy", "degraded", "stale", "unavailable"))
TRANSITIONS = {
    "draft": {"queued", "cancelled"},
    "queued": {"running", "failed", "cancelled"},
    "running": {"stopping", "completed", "failed", "cancelled"},
    "stopping": {"cancelled", "failed"},
    "failed": {"queued", "cancelled"},
    "completed": set(),
    "cancelled": {"queued"},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConflictError(RuntimeError):
    pass


class NotFoundError(KeyError):
    pass


class RunRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL,
                started_at TEXT, ended_at TEXT, status TEXT NOT NULL, health TEXT NOT NULL, config_json TEXT NOT NULL,
                output_dir TEXT NOT NULL UNIQUE, checkpoint_json TEXT NOT NULL, pid INTEGER, exit_code INTEGER,
                failure_reason TEXT, last_heartbeat TEXT, last_event_id INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0)"""
            )

    def connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json"))
        item["checkpoint"] = json.loads(item.pop("checkpoint_json"))
        item["archived"] = bool(item["archived"])
        return item

    def create(
        self,
        run_id: str,
        name: str,
        description: str,
        config: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        with self.lock, self.connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO runs(run_id,name,description,created_at,status,health,config_json,output_dir,checkpoint_json) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        name,
                        description,
                        now(),
                        "draft",
                        "healthy",
                        json.dumps(config),
                        str(output_dir),
                        json.dumps({"last_completed_date": None, "next_date": config["start_date"]}),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ConflictError("run_id already exists") from error
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise NotFoundError(run_id)
        return self.row(row)

    def list(
        self,
        status: str | None = None,
        archived: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = ["archived=?"]
        values: list[Any] = [int(archived)]
        if status:
            clauses.append("status=?")
            values.append(status)
        where = " AND ".join(clauses)
        with self.connection() as conn:
            total = conn.execute(f"SELECT count(*) FROM runs WHERE {where}", values).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM runs WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
        return [self.row(row) for row in rows], total

    def update(self, run_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "name",
            "description",
            "status",
            "health",
            "config_json",
            "checkpoint_json",
            "pid",
            "exit_code",
            "failure_reason",
            "last_heartbeat",
            "last_event_id",
            "started_at",
            "ended_at",
            "archived",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get(run_id)
        keys = ", ".join(f"{key}=?" for key in updates)
        with self.lock, self.connection() as conn:
            if conn.execute(
                f"UPDATE runs SET {keys} WHERE run_id=?", (*updates.values(), run_id)
            ).rowcount != 1:
                raise NotFoundError(run_id)
        return self.get(run_id)

    def transition(self, run_id: str, target: str, **fields: Any) -> dict[str, Any]:
        current = self.get(run_id)
        if current["status"] == target:
            return current
        if target not in TRANSITIONS.get(current["status"], set()):
            raise ConflictError(f"cannot change {current['status']} to {target}")
        if target == "running":
            fields.setdefault("started_at", now())
        if target in {"completed", "failed", "cancelled"}:
            fields.setdefault("ended_at", now())
        return self.update(run_id, status=target, **fields)
