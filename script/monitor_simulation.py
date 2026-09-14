#!/usr/bin/env python3
"""Read-only terminal monitor for a TwinMarket simulation run."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


CURRENT_DATE_PATTERN = re.compile(r"=== 当前日期: (\d{4}-\d{2}-\d{2}) ===")
CONFIG_DATE_PATTERN = {
    "start": re.compile(r'"start_date":\s*"(\d{4}-\d{2}-\d{2})"'),
    "end": re.compile(r'"end_date":\s*"(\d{4}-\d{2}-\d{2})"'),
}
ERROR_MARKERS = ("Traceback", "[错误]", "发生错误", "失败", "Error:")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", required=True, help="Simulation output directory")
    parser.add_argument("--start-date", help="Expected start date, YYYY-MM-DD")
    parser.add_argument("--end-date", help="Expected end date, YYYY-MM-DD")
    parser.add_argument("--user-db", help="User database path; auto-detected by default")
    parser.add_argument("--forum-db", help="Forum database path; auto-detected by default")
    parser.add_argument("--interval", type=float, default=5.0, help="Refresh seconds")
    parser.add_argument("--tail", type=int, default=12, help="Log lines to display")
    parser.add_argument("--once", action="store_true", help="Print one snapshot and exit")
    parser.add_argument("--json", action="store_true", help="Emit one JSON snapshot")
    return parser.parse_args()


def newest(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def detect_file(log_dir: Path, explicit: str | None, patterns: tuple[str, ...]) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(log_dir.glob(pattern))
    return newest(candidates)


def read_log(log_path: Path | None) -> tuple[str, list[str], int, float | None]:
    if log_path is None:
        return "", [], 0, None
    with log_path.open("rb") as handle:
        head = handle.read(64 * 1024)
        size = handle.seek(0, 2)
        handle.seek(max(0, size - 1024 * 1024))
        tail = handle.read()
    header_text = head.decode("utf-8", errors="replace")
    tail_text = tail.decode("utf-8", errors="replace")
    lines = tail_text.splitlines()
    error_count = sum(any(marker in line for marker in ERROR_MARKERS) for line in lines)
    age = max(0.0, time.time() - log_path.stat().st_mtime)
    return header_text + "\n" + tail_text, lines, error_count, age


def parse_config_date(log_text: str, key: str) -> str | None:
    match = CONFIG_DATE_PATTERN[key].search(log_text)
    return match.group(1) if match else None


def query_one(db_path: Path | None, sql: str, default: Any = None) -> Any:
    if db_path is None:
        return default
    try:
        uri = f"file:{db_path.resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1) as connection:
            row = connection.execute(sql).fetchone()
            return row[0] if row else default
    except (OSError, sqlite3.Error):
        return default


def count_files(path: Path, pattern: str) -> int:
    return sum(1 for item in path.glob(pattern) if item.is_file()) if path.exists() else 0


def trading_days(start: str | None, end: str | None) -> list[str]:
    if not start or not end:
        return []
    calendar_path = Path(__file__).resolve().parents[1] / "data" / "trading_days.csv"
    with calendar_path.open(newline="", encoding="utf-8") as handle:
        return [
            row["cal_date"]
            for row in csv.DictReader(handle)
            if start <= row["cal_date"] <= end and row["is_open"] == "open"
        ]


def progress_bar(done: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = min(width, round(width * done / total))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    log_dir = Path(args.log_dir)
    if not log_dir.is_dir():
        raise FileNotFoundError(f"Log directory does not exist: {log_dir}")

    log_path = newest(list(log_dir.glob("simulation*.log")))
    log_text, log_lines, error_count, log_age = read_log(log_path)
    current_dates = CURRENT_DATE_PATTERN.findall(log_text)
    current_date = current_dates[-1] if current_dates else None
    start_date = args.start_date or parse_config_date(log_text, "start")
    end_date = args.end_date or parse_config_date(log_text, "end")

    user_db = detect_file(log_dir, args.user_db, ("user_*.db", "user.db"))
    forum_db = detect_file(log_dir, args.forum_db, ("forum_*.db", "forum.db"))
    open_days = trading_days(start_date, end_date)
    latest_profile_date = query_one(user_db, "SELECT max(created_at) FROM Profiles")
    completed_date = str(latest_profile_date)[:10] if latest_profile_date else None
    completed_open_days = sum(
        completed_date is not None and item <= completed_date for item in open_days
    )

    return {
        "observed_at": datetime.now().isoformat(timespec="seconds"),
        "log_dir": str(log_dir.resolve()),
        "log_file": str(log_path.resolve()) if log_path else None,
        "log_age_seconds": round(log_age, 1) if log_age is not None else None,
        "start_date": start_date,
        "end_date": end_date,
        "current_date": current_date,
        "completed_through": completed_date,
        "trading_days_completed": completed_open_days,
        "trading_days_total": len(open_days),
        "user_db": str(user_db.resolve()) if user_db else None,
        "forum_db": str(forum_db.resolve()) if forum_db else None,
        "users": query_one(user_db, "SELECT count(DISTINCT user_id) FROM Profiles", 0),
        "profile_snapshots": query_one(user_db, "SELECT count(*) FROM Profiles", 0),
        "trades": query_one(user_db, "SELECT count(*) FROM TradingDetails", 0),
        "latest_trade_date": query_one(user_db, "SELECT max(date_time) FROM TradingDetails"),
        "latest_stock_date": query_one(user_db, "SELECT max(date) FROM StockData"),
        "forum_posts": query_one(forum_db, "SELECT count(*) FROM posts", 0),
        "forum_reactions": query_one(forum_db, "SELECT count(*) FROM reactions", 0),
        "artifacts": {
            "trading_records": count_files(log_dir / "trading_records", "*.json"),
            "reaction_records": count_files(log_dir / "reaction_records", "*.json"),
            "post_records": count_files(log_dir / "post_records", "*.json"),
            "conversation_records": count_files(
                log_dir / "conversation_records", "**/*.json"
            ),
            "graph_snapshots": count_files(log_dir / "graphs", "*.pkl"),
            "simulation_days": sum(
                1
                for item in (log_dir / "simulation_results").glob("*")
                if item.is_dir()
            )
            if (log_dir / "simulation_results").exists()
            else 0,
        },
        "error_lines": error_count,
        "log_tail": log_lines[-max(0, args.tail) :],
    }


def render(snapshot: dict[str, Any]) -> str:
    done = snapshot["trading_days_completed"]
    total = snapshot["trading_days_total"]
    artifacts = snapshot["artifacts"]
    age = snapshot["log_age_seconds"]
    age_text = "unknown" if age is None else f"{age:.1f}s ago"
    lines = [
        f"TwinMarket monitor  {snapshot['observed_at']}",
        f"Run: {snapshot['log_dir']}",
        "",
        f"Range: {snapshot['start_date'] or '?'} -> {snapshot['end_date'] or '?'}",
        f"Current: {snapshot['current_date'] or '?'}  completed through: {snapshot['completed_through'] or '?'}",
        f"Trading days: {progress_bar(done, total)} {done}/{total}",
        f"Log updated: {age_text}  flagged lines (recent 1 MiB): {snapshot['error_lines']}",
        "",
        f"Users: {snapshot['users']}  profile snapshots: {snapshot['profile_snapshots']}",
        f"Trades: {snapshot['trades']}  latest trade: {snapshot['latest_trade_date'] or '?'}",
        f"Stock data through: {snapshot['latest_stock_date'] or '?'}",
        f"Forum posts: {snapshot['forum_posts']}  reactions: {snapshot['forum_reactions']}",
        "",
        "Artifacts: "
        f"trading={artifacts['trading_records']} "
        f"reaction={artifacts['reaction_records']} "
        f"post={artifacts['post_records']} "
        f"conversation={artifacts['conversation_records']} "
        f"graphs={artifacts['graph_snapshots']} "
        f"simulation_days={artifacts['simulation_days']}",
        "",
        "Log tail:",
        *snapshot["log_tail"],
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        raise ValueError("--interval must be greater than zero")
    try:
        while True:
            snapshot = build_snapshot(args)
            if args.json:
                print(json.dumps(snapshot, ensure_ascii=False, indent=2))
                return 0
            if not args.once:
                print("\033[2J\033[H", end="")
            print(render(snapshot), flush=True)
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    except (FileNotFoundError, ValueError) as error:
        print(f"monitor error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
