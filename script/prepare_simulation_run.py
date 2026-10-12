#!/usr/bin/env python3
"""Create a size-matched user database and belief file for a simulation run."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
import shutil
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-db", required=True)
    parser.add_argument("--belief-source", required=True)
    parser.add_argument("--user-count", required=True, type=int)
    parser.add_argument("--user-db", required=True)
    parser.add_argument("--belief-output", required=True)
    parser.add_argument("--market-snapshot")
    parser.add_argument("--start-date")
    return parser.parse_args()


def read_beliefs(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "user_id" not in reader.fieldnames:
            raise ValueError(f"belief 文件缺少 user_id 列: {path}")
        rows = {str(row["user_id"]): row for row in reader}
        return list(reader.fieldnames), rows


def prepare_database(template: Path, output: Path, user_count: int, *, market_snapshot: Path | None = None, start_date: str | None = None) -> list[str]:
    if output.exists():
        raise FileExistsError(f"拒绝覆盖已有数据库: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, output)

    with sqlite3.connect(output) as connection:
        available = connection.execute(
            "SELECT count(DISTINCT user_id) FROM Profiles"
        ).fetchone()[0]
        if not 1 <= user_count <= available:
            raise ValueError(
                f"user_count 必须在 1 到 {available} 之间，当前为 {user_count}"
            )

        user_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT user_id FROM Profiles ORDER BY user_id LIMIT ?",
                (user_count,),
            )
        ]
        connection.execute(
            "CREATE TEMP TABLE keep_users (user_id TEXT PRIMARY KEY)"
        )
        connection.executemany(
            "INSERT INTO keep_users(user_id) VALUES (?)",
            ((user_id,) for user_id in user_ids),
        )
        connection.execute(
            "DELETE FROM Profiles WHERE user_id NOT IN (SELECT user_id FROM keep_users)"
        )
        connection.execute(
            "DELETE FROM Strategy WHERE CAST(user_id AS TEXT) "
            "NOT IN (SELECT user_id FROM keep_users)"
        )
        connection.execute(
            "DELETE FROM TradingDetails WHERE user_id "
            "NOT IN (SELECT user_id FROM keep_users)"
        )
        if market_snapshot is not None:
            inject_market_history(connection, market_snapshot, start_date)
            seed_snapshot_accounts(connection, start_date)
        connection.commit()
        connection.execute("VACUUM")

        profile_count = connection.execute(
            "SELECT count(DISTINCT user_id) FROM Profiles"
        ).fetchone()[0]
        strategy_count = connection.execute(
            "SELECT count(DISTINCT CAST(user_id AS TEXT)) FROM Strategy"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    if profile_count != user_count or strategy_count != user_count:
        raise RuntimeError(
            f"用户子集不完整: Profiles={profile_count}, Strategy={strategy_count}"
        )
    if integrity != "ok":
        raise RuntimeError(f"数据库完整性检查失败: {integrity}")
    return user_ids


STOCK_COLUMNS = ("stock_id", "date", "close_price", "pre_close", "change", "pct_chg", "pe_ttm", "pb",
                 "ps_ttm", "dv_ttm", "vol", "vol_5", "vol_10", "vol_30", "elg_amount_net",
                 "ma_hfq_5", "ma_hfq_10", "ma_hfq_30")


def inject_market_history(connection, snapshot, start_date):
    """Replace only the private StockData, strictly before the first simulation day."""
    import math
    start_date = date.fromisoformat(str(start_date)).isoformat()
    with (snapshot / "stock_data.csv").open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["date"] < start_date]
    if len({row["date"] for row in rows}) < 30:
        raise ValueError("快照没有起始日前至少 30 个交易日的可见历史行情")
    mapping = {"stock_id": "ts_code", "close_price": "close"}

    def value(row, column):
        raw = row.get(mapping.get(column, column))
        if column in {"stock_id", "date"}:
            return raw
        # Legacy stock_data.csv used turnover in the volume position.
        if column == "vol" and not raw:
            raw = row.get("amount")
        if column.startswith("vol_") and not raw:
            raw = row.get(column.replace("vol_", "ma_amount_"))
        if raw in (None, ""):
            return None
        number = float(raw)
        return number if math.isfinite(number) else None

    codes = {row["ts_code"] for row in rows}
    if len(codes) != 10 or len({(row["ts_code"], row["date"]) for row in rows}) != len(rows):
        raise ValueError("快照历史指数缺失或重复")
    connection.execute("DELETE FROM StockData")
    connection.executemany("INSERT INTO StockData (" + ",".join(STOCK_COLUMNS) + ") VALUES (" +
                           ",".join("?" for _ in STOCK_COLUMNS) + ")",
                           [tuple(value(row, column) for column in STOCK_COLUMNS) for row in rows])


def seed_snapshot_accounts(connection, start_date):
    """Seed private accounts on the preceding natural day at observable prices."""
    previous = (date.fromisoformat(start_date) - timedelta(days=1)).isoformat() + " 00:00:00"
    columns = [row[1] for row in connection.execute("PRAGMA table_info(Profiles)")]
    profiles = connection.execute("SELECT * FROM Profiles WHERE created_at < ? ORDER BY created_at", (start_date,)).fetchall()
    selected = {dict(zip(columns, row))["user_id"]: dict(zip(columns, row)) for row in profiles}
    count = connection.execute("SELECT count(DISTINCT user_id) FROM Profiles").fetchone()[0]
    if len(selected) != count:
        raise ValueError("所选起始日前没有用户初始账户")
    prices = dict(connection.execute("SELECT stock_id,close_price FROM StockData WHERE date=(SELECT max(date) FROM StockData)"))
    connection.execute("DELETE FROM Profiles")
    for profile in selected.values():
        profile["created_at"] = previous
        if {"cur_positions", "current_cash", "total_value"}.issubset(columns):
            positions = json.loads(profile["cur_positions"] or "{}")
            for code, position in positions.items():
                if code not in prices:
                    raise ValueError("初始持仓不在快照资产定义中")
                position["current_value"] = float(position["shares"]) * prices[code]
            total = float(profile["current_cash"]) + sum(p["current_value"] for p in positions.values())
            for position in positions.values():
                position["ratio"] = position["current_value"] / total * 100 if total else 0
            profile["cur_positions"] = json.dumps(positions, ensure_ascii=False)
            profile["total_value"] = total
            if {"ini_cash", "total_return", "return_rate"}.issubset(columns):
                initial = float(profile["ini_cash"])
                profile["total_return"] = total - initial
                profile["return_rate"] = (total - initial) / initial * 100 if initial else 0
        connection.execute("INSERT INTO Profiles (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")",
                           [profile[column] for column in columns])


def write_beliefs(
    source: Path, output: Path, selected_user_ids: list[str]
) -> None:
    if output.exists():
        raise FileExistsError(f"拒绝覆盖已有 belief 文件: {output}")
    fieldnames, source_rows = read_beliefs(source)
    missing = [user_id for user_id in selected_user_ids if user_id not in source_rows]
    if missing:
        raise ValueError(
            f"belief 文件缺少 {len(missing)} 个选中用户，示例: {missing[:5]}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(source_rows[user_id] for user_id in selected_user_ids)


def main() -> int:
    args = parse_args()
    template = Path(args.template_db)
    belief_source = Path(args.belief_source)
    user_db = Path(args.user_db)
    belief_output = Path(args.belief_output)

    if not template.is_file():
        raise FileNotFoundError(f"用户数据库模板不存在: {template}")
    if not belief_source.is_file():
        raise FileNotFoundError(f"belief 源文件不存在: {belief_source}")

    if args.market_snapshot and not args.start_date:
        raise ValueError("--market-snapshot 必须同时提供 --start-date")
    selected_user_ids = prepare_database(template, user_db, args.user_count,
        market_snapshot=Path(args.market_snapshot) if args.market_snapshot else None, start_date=args.start_date)
    write_beliefs(belief_source, belief_output, selected_user_ids)
    print(
        f"已准备 {len(selected_user_ids)} 个用户: "
        f"database={user_db}, belief={belief_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
