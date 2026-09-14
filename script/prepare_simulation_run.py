#!/usr/bin/env python3
"""Create a size-matched user database and belief file for a simulation run."""

from __future__ import annotations

import argparse
import csv
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
    return parser.parse_args()


def read_beliefs(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "user_id" not in reader.fieldnames:
            raise ValueError(f"belief 文件缺少 user_id 列: {path}")
        rows = {str(row["user_id"]): row for row in reader}
        return list(reader.fieldnames), rows


def prepare_database(template: Path, output: Path, user_count: int) -> list[str]:
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

    selected_user_ids = prepare_database(template, user_db, args.user_count)
    write_beliefs(belief_source, belief_output, selected_user_ids)
    print(
        f"已准备 {len(selected_user_ids)} 个用户: "
        f"database={user_db}, belief={belief_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
