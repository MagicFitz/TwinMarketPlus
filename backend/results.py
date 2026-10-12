"""Read-only queries and export helpers for run output artifacts."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from runtime.schemas import redact


def _run_folder(run: dict[str, Any]) -> Path:
    """Resolve a run's output directory once for descendant safety checks.

    The HTTP layer is responsible for verifying a Registry output is beneath
    its configured runs directory.  These helpers additionally ensure that a
    symlink *inside* that trusted output cannot redirect a result read outside
    it.
    """
    return Path(run["output_dir"]).resolve()


def _safe_directory(folder: Path, *parts: str) -> Path | None:
    candidate = folder.joinpath(*parts).resolve()
    if not candidate.is_relative_to(folder) or not candidate.is_dir():
        return None
    return candidate


def _safe_files(folder: Path, pattern: str) -> Iterator[Path]:
    if not folder.is_dir():
        return
    for candidate in sorted(folder.glob(pattern)):
        try:
            path = candidate.resolve()
        except OSError:
            continue
        if path.is_relative_to(folder) and path.is_file():
            yield path


def result_files(folder: Path) -> list[Path]:
    root = Path(folder).resolve()
    return list(_safe_files(root, "simulation_results/*/daily_summary_*.csv"))


def results_summary(run: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in result_files(_run_folder(run)):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return {
        "items": rows,
        "source": "simulation_results/daily_summary_*.csv",
        "market_snapshot_id": run["config"].get("market_snapshot_id"),
        "allow_missing_news": run["config"].get("allow_missing_news", False),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def paged_json_records(
    folder: Path,
    kind: str,
    page: int,
    page_size: int,
    date: str | None = None,
    asset: str | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    root = Path(folder).resolve()
    records_dir = _safe_directory(root, "trading_records")
    for path in _safe_files(records_dir, "*.json") if records_dir is not None else ():
        if path.name.endswith("_orders.json") != (kind == "orders"):
            continue
        if date and path.stem[:10] != date:
            continue
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
            values = content.values() if isinstance(content, dict) else content
            for row in values:
                if isinstance(row, dict) and (
                    not asset or asset in json.dumps(row, ensure_ascii=False)
                ):
                    items.append({"date": path.stem[:10], **redact(row)})
        except (OSError, ValueError):
            continue
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "source": "trading_records JSON",
    }


def results_agents(run: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    folder = _run_folder(run)
    db = (folder / f"user_{run['config']['user_count']}.db").resolve()
    if not db.is_relative_to(folder) or not db.is_file():
        return {
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "source": "unavailable",
        }
    # Result inspection must not obtain a writable SQLite connection, even
    # though these are per-run generated databases.
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
        conn.execute("PRAGMA query_only = ON")
        total = conn.execute("SELECT count(*) FROM (SELECT DISTINCT user_id FROM Profiles)").fetchone()[0]
        rows = conn.execute(
            "SELECT user_id,current_cash,total_value,return_rate,cur_positions,created_at "
            "FROM Profiles WHERE created_at=(SELECT max(created_at) FROM Profiles) "
            "ORDER BY user_id LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "items": [
            {
                "agent_id": row[0],
                "cash": row[1],
                "total_value": row[2],
                "return_rate": row[3],
                "positions": row[4],
                "as_of": row[5],
            }
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "source": "user database latest Profiles snapshot",
    }


def results_social(run: dict[str, Any]) -> dict[str, int]:
    folder = _run_folder(run)
    result: dict[str, int] = {}
    for name in ("post_records", "reaction_records"):
        records_dir = _safe_directory(folder, name)
        result[name] = len(list(_safe_files(records_dir, "*.json"))) if records_dir else 0
    return result


def artifact_items(run: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    folder = _run_folder(run)
    items: list[dict[str, Any]] = []
    if folder.is_dir():
        for candidate in folder.rglob("*"):
            try:
                path = candidate.resolve()
            except OSError:
                continue
            if not path.is_relative_to(folder) or not path.is_file() or path.name == "run.lock":
                continue
            try:
                items.append(
                    {"path": candidate.relative_to(folder).as_posix(), "bytes": path.stat().st_size}
                )
            except OSError:
                continue
    return {"items": items}


def downloadable_artifact(run: dict[str, Any], artifact_path: str) -> Path | None:
    """Return only an allowed, regular artifact beneath the run directory."""
    folder = _run_folder(run)
    try:
        target = (folder / artifact_path).resolve()
    except OSError:
        return None
    if (
        not target.is_relative_to(folder)
        or not target.is_file()
        or target.suffix not in {".csv", ".json", ".txt"}
    ):
        return None
    return target


def export_records(folder: Path, kind: str) -> Iterator[dict[str, Any]]:
    """Yield the same unredacted record shape used by the established download API."""
    if kind not in {"trades", "orders"}:
        raise ValueError("不支持导出的结果类型")
    root = Path(folder).resolve()
    records_dir = _safe_directory(root, "trading_records")
    if records_dir is None:
        return
    for path in _safe_files(records_dir, "*.json"):
        if path.name.endswith("_orders.json") != (kind == "orders"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            values = data.values() if isinstance(data, dict) else data
            for value in values:
                if isinstance(value, dict):
                    yield {"date": path.stem[:10], **value}
        except (OSError, ValueError):
            continue


def json_export_chunks(folder: Path, kind: str) -> Iterator[str]:
    yield "["
    first = True
    for value in export_records(folder, kind):
        if not first:
            yield ","
        first = False
        yield json.dumps(value, ensure_ascii=False, default=str)
    yield "]"


def csv_export_chunks(folder: Path, kind: str) -> Iterator[str]:
    first = True
    for value in export_records(folder, kind):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(value), extrasaction="ignore")
        if first:
            writer.writeheader()
            first = False
        writer.writerow(
            {
                key: json.dumps(item, ensure_ascii=False)
                if isinstance(item, (dict, list))
                else item
                for key, item in value.items()
            }
        )
        yield output.getvalue()
