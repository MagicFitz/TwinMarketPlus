#!/usr/bin/env python3
"""Create and validate immutable TwinMarket run directories.

A run is always ``runs/<run_id>``.  ``manifest.json`` is written exactly once;
``state.json`` records the last fully completed simulation day.  A resume must
start at ``state.checkpoint.next_date``: the simulator clears data and artifacts
at and after that date, then regenerates that date.  No other date is safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SENSITIVE_KEYS = {"api_key", "api_keys", "authorization", "token", "password", "secret"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"运行输入不存在: {path}")
    if path.is_file():
        return {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path), "bytes": path.stat().st_size}
    entries = []
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        entries.append((str(child.relative_to(path)), sha256_file(child)))
    digest = hashlib.sha256(json.dumps(entries, ensure_ascii=False).encode()).hexdigest()
    return {"path": str(path.relative_to(ROOT)), "sha256": digest, "files": len(entries)}


def sanitize(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS or any(word in key.lower() for word in SENSITIVE_KEYS):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {str(name): sanitize(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item, key) for item in value]
    return value


def read_config_snapshot(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"模型配置必须是 YAML 对象: {path}")
    return sanitize(loaded)


def git_revision() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_dir_for(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id 只能包含字母、数字、.、_、-，且最长 128 个字符")
    return RUNS_DIR / run_id


def clear_date_scoped_artifacts(run_dir: Path, resume_date: str) -> None:
    """Remove date-scoped outputs at/after resume_date, preserving prior days."""
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    for parent_name in ("conversation_records", "trading_records", "reaction_records",
                        "post_records", "simulation_results", "graphs"):
        parent = run_dir / parent_name
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            match = date_pattern.search(child.name)
            if match and match.group() >= resume_date:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()


def create_run(args: argparse.Namespace) -> Path:
    run_dir = run_dir_for(args.run_id)
    RUNS_DIR.mkdir(exist_ok=True)
    try:
        run_dir.mkdir()
    except FileExistsError as error:
        raise FileExistsError(f"run_id 已存在，拒绝覆盖: {args.run_id}") from error

    try:
        config_path = Path(args.config_path).resolve()
        inputs = {
            "agent_group_template": fingerprint(Path(args.template_db).resolve()),
            "belief_source": fingerprint(Path(args.belief_source).resolve()),
            "market_stock_data": fingerprint(ROOT / "data/stock_data.csv"),
            "market_trading_days": fingerprint(ROOT / "data/trading_days.csv"),
            "market_news": fingerprint(ROOT / "data/sorted_impact_news.pkl"),
            "model_config": fingerprint(config_path),
        }
        manifest = {
        "schema_version": 1,
        "run_id": args.run_id,
        "created_at": utc_now(),
        "code_version": git_revision(),
        "random_seed": args.random_seed,
        "command_summary": args.command_summary,
        "parameters": {"user_count": args.user_count, "start_date": args.start_date,
                       "end_date": args.end_date, "max_workers": args.max_workers,
                       "activate_prob": args.activate_prob,
                       "prob_of_technical": args.prob_of_technical},
        "inputs": inputs,
        "model_config_snapshot": read_config_snapshot(config_path),
        "checkpoint_rule": {
            "resume_date": "must equal state.checkpoint.next_date",
            "cleanup": "all database rows and date-scoped artifacts at or after resume_date are regenerated",
            "required_artifacts": ["user_<count>.db", "forum_<count>.db", "belief_<count>.csv", "state.json"],
        },
        }
        atomic_json_write(run_dir / "manifest.json", manifest)
        atomic_json_write(run_dir / "state.json", {
        "schema_version": 1, "status": "prepared", "checkpoint": {
            "last_completed_date": None, "next_date": args.start_date,
        }, "updated_at": utc_now(),
        })
    except Exception:
        shutil.rmtree(run_dir)
        raise
    return run_dir


def validate_resume(run_dir: Path, resume_date: str, user_count: int) -> None:
    manifest_path, state_path = run_dir / "manifest.json", run_dir / "state.json"
    if not manifest_path.is_file() or not state_path.is_file():
        raise ValueError("续跑目录缺少 manifest.json 或 state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    expected = state.get("checkpoint", {}).get("next_date")
    if expected != resume_date:
        raise ValueError(f"续跑日期必须是 checkpoint.next_date ({expected})，收到 {resume_date}")
    required = [run_dir / f"user_{user_count}.db", run_dir / f"forum_{user_count}.db",
                run_dir / f"belief_{user_count}.csv"]
    missing = [str(path.name) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"续跑目录缺少必需产物: {', '.join(missing)}")


def record_prepared_artifacts(run_dir: Path, user_db: Path, belief_file: Path) -> None:
    """Attach the deterministic, selected Agent Group fingerprints to manifest."""
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["prepared_agent_group"] = {
        "user_database": fingerprint(user_db),
        "belief_file": fingerprint(belief_file),
    }
    atomic_json_write(manifest_path, manifest)


class RunLock:
    """An O_EXCL lock kept for the complete child-process lifetime."""

    def __init__(self, run_dir: Path):
        self.path = run_dir / "run.lock"

    def __enter__(self):
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise RuntimeError(f"运行目录正在被另一个进程写入: {self.path}") from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "started_at": utc_now()}, handle)
        return self

    def __exit__(self, *_exc):
        self.path.unlink(missing_ok=True)


def launch(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if run_dir.parent != RUNS_DIR.resolve():
        raise ValueError("run_dir 必须直接位于 ./runs 下")
    if args.resume_date:
        validate_resume(run_dir, args.resume_date, args.user_count)
        if "--checkpoint" not in args.command:
            args.command.append("--checkpoint")
    state_path = run_dir / "state.json"
    with RunLock(run_dir):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"status": "running", "pid": os.getpid(), "updated_at": utc_now()})
        atomic_json_write(state_path, state)
        if args.log_file:
            with Path(args.log_file).open("w", encoding="utf-8") as log_handle:
                process = subprocess.Popen(args.command, cwd=ROOT, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True)
                assert process.stdout is not None
                for line in process.stdout:
                    sys.stdout.write(line)
                    log_handle.write(line)
                result = SimpleNamespace(returncode=process.wait())
        else:
            result = subprocess.run(args.command, cwd=ROOT)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"status": "completed" if result.returncode == 0 else "failed",
                      "exit_code": result.returncode, "updated_at": utc_now()})
        state.pop("pid", None)
        atomic_json_write(state_path, state)
        return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--run-id", required=True)
    create.add_argument("--template-db", required=True)
    create.add_argument("--belief-source", required=True)
    create.add_argument("--config-path", required=True)
    create.add_argument("--user-count", type=int, required=True)
    create.add_argument("--start-date", required=True)
    create.add_argument("--end-date", required=True)
    create.add_argument("--max-workers", type=int, required=True)
    create.add_argument("--activate-prob", type=float, required=True)
    create.add_argument("--prob-of-technical", type=float, required=True)
    create.add_argument("--random-seed", type=int, required=True)
    create.add_argument("--command-summary", required=True)
    launch_parser = actions.add_parser("launch")
    launch_parser.add_argument("--run-dir", required=True)
    launch_parser.add_argument("--user-count", type=int, required=True)
    launch_parser.add_argument("--resume-date")
    launch_parser.add_argument("--log-file")
    launch_parser.add_argument("command", nargs=argparse.REMAINDER)
    prepared = actions.add_parser("record-prepared")
    prepared.add_argument("--run-dir", required=True)
    prepared.add_argument("--user-db", required=True)
    prepared.add_argument("--belief-file", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.action == "create":
        print(create_run(args))
        return 0
    if args.action == "record-prepared":
        record_prepared_artifacts(Path(args.run_dir).resolve(), Path(args.user_db).resolve(),
                                  Path(args.belief_file).resolve())
        return 0
    if not args.command or args.command[0] != "--":
        raise ValueError("launch 命令必须用 -- 分隔，例如 launch ... -- python simulation.py")
    args.command = args.command[1:]
    return launch(args)


if __name__ == "__main__":
    raise SystemExit(main())
