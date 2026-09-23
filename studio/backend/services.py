"""Run preparation, process control, persisted snapshots and true-result queries."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime import EventStore, RuntimeObserver, RuntimeSnapshotReducer
from runtime.schemas import Scope, redact

from .registry import ConflictError, RunRegistry

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
DEFAULTS = {"user_count": 10, "start_date": "2023-06-15", "end_date": "2023-06-16", "max_workers": 1,
            "activate_prob": 0.2, "prob_of_technical": 0.3, "random_seed": 20260916,
            "template_db": "data/sys_1000.db", "belief_source": "util/belief/belief_1000_0129.csv", "config_path": "config/api.yaml"}


def safe_run_id(value: str) -> str:
    value = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.lower()).strip("-")
    return value[:64] or f"run-{uuid4().hex[:12]}"


def file_fingerprint(path: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def git_revision() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def normalize_config(value: dict[str, Any]) -> dict[str, Any]:
    config = {**DEFAULTS, **{key: value[key] for key in DEFAULTS if key in value}}
    config["user_count"] = int(config["user_count"]); config["max_workers"] = int(config["max_workers"]); config["random_seed"] = int(config["random_seed"])
    config["activate_prob"] = float(config["activate_prob"]); config["prob_of_technical"] = float(config["prob_of_technical"])
    if not 1 <= config["user_count"] <= 1000 or config["max_workers"] < 1 or not 0 <= config["activate_prob"] <= 1 or not 0 <= config["prob_of_technical"] <= 1:
        raise ValueError("用户数、并发数或概率超出允许范围")
    if config["start_date"] > config["end_date"]: raise ValueError("开始日期不能晚于结束日期")
    for key in ("template_db", "belief_source", "config_path"):
        path = (ROOT / config[key]).resolve()
        if not path.is_relative_to(ROOT): raise ValueError("配置路径必须位于项目目录")
        config[key] = str(path.relative_to(ROOT))
    return config


def create_run(registry: RunRegistry, request: dict[str, Any]) -> dict[str, Any]:
    config = normalize_config(request.get("config") or request)
    requested = request.get("run_id") or request.get("name") or f"run-{uuid4().hex[:12]}"
    run_id = safe_run_id(requested)
    output = RUNS / run_id
    RUNS.mkdir(exist_ok=True)
    try: output.mkdir(mode=0o700)
    except FileExistsError as error: raise ConflictError("run_id 已存在，拒绝覆盖运行目录") from error
    try:
        input_paths = {"agent_group_template": ROOT / config["template_db"], "belief_source": ROOT / config["belief_source"], "model_config": ROOT / config["config_path"],
                       "market_stock_data": ROOT / "data/stock_data.csv", "market_trading_days": ROOT / "data/trading_days.csv", "market_news": ROOT / "data/sorted_impact_news.pkl"}
        manifest = {"schema_version": 2, "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(), "code_version": git_revision(),
                    "parameters": redact(config), "inputs": {key: file_fingerprint(path) for key, path in input_paths.items() if path.is_file()},
                    "command_summary": "studio.backend.worker -> simulation.py (arguments stored in Registry config)",
                    "checkpoint_rule": {"resume_date": "必须等于 state.json checkpoint.next_date", "cleanup": "续跑日及之后的数据库记录和按日期产物将被重新生成"}}
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "state.json").write_text(json.dumps({"status": "draft", "checkpoint": {"last_completed_date": None, "next_date": config["start_date"]}}, ensure_ascii=False, indent=2), encoding="utf-8")
        return registry.create(run_id, str(request.get("name") or run_id), str(request.get("description") or ""), config, output)
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def validate_start(run: dict[str, Any], resume: bool = False) -> list[str]:
    config, folder = run["config"], Path(run["output_dir"])
    errors = [f"缺少必要输入: {key}" for key in ("template_db", "belief_source", "config_path") if not (ROOT / config[key]).is_file()]
    if not (ROOT / "data/sorted_impact_news.pkl").is_file() or not (ROOT / "data/trading_days.csv").is_file(): errors.append("缺少市场数据或交易日历")
    if resume:
        next_date = run["checkpoint"].get("next_date")
        if not next_date or next_date > config["end_date"]: errors.append("没有可用 checkpoint 可续跑")
        for path in (folder / f"user_{config['user_count']}.db", folder / f"forum_{config['user_count']}.db", folder / f"belief_{config['user_count']}.csv"):
            if not path.is_file(): errors.append(f"续跑产物缺失: {path.name}")
    return errors


class ProcessManager:
    def __init__(self, registry: RunRegistry, max_concurrency: int = 2): self.registry, self.max_concurrency = registry, max_concurrency
    def start(self, run_id: str, resume: bool = False) -> dict[str, Any]:
        run = self.registry.get(run_id)
        if resume and run["status"] not in {"failed", "cancelled"}:
            raise ConflictError("仅失败或已取消的运行可以从 checkpoint 续跑")
        if run["status"] in {"queued", "running"}: return run  # idempotent
        errors = validate_start(run, resume)
        if errors: raise ValueError("; ".join(errors))
        active, _ = self.registry.list(status="running", limit=1000)
        queued, _ = self.registry.list(status="queued", limit=1000)
        if len(active) + len(queued) >= self.max_concurrency: raise ConflictError("本机运行配额已满")
        run = self.registry.transition(run_id, "queued")
        command = [sys.executable, "-m", "studio.backend.worker", "--run-id", run_id] + (["--resume"] if resume else [])
        process = subprocess.Popen(command, cwd=ROOT, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.registry.update(run_id, pid=process.pid, last_heartbeat=datetime.now(timezone.utc).isoformat())
    def stop(self, run_id: str) -> dict[str, Any]:
        run = self.registry.get(run_id)
        if run["status"] == "cancelled": return run
        if run["status"] not in {"queued", "running", "stopping"}: raise ConflictError("当前状态不能停止")
        if run["status"] != "stopping": run = self.registry.transition(run_id, "stopping")
        RuntimeObserver(run_id, store_for(run), lambda reason: self.registry.update(run_id, health="degraded", failure_reason=reason)).started(Scope.RUN, "stop", message="已请求温和停止")
        if run["pid"]:
            try: os.killpg(os.getpgid(run["pid"]), signal.SIGTERM)
            except ProcessLookupError: pass
            def escalate(pid: int, expected_run: str) -> None:
                time.sleep(10)
                latest = self.registry.get(expected_run)
                if latest["status"] != "stopping": return
                try: os.killpg(os.getpgid(pid), signal.SIGKILL)
                except ProcessLookupError: pass
                self.registry.transition(expected_run, "cancelled", pid=None, failure_reason="用户停止：温和终止超时后升级")
            threading.Thread(target=escalate, args=(int(run["pid"]), run_id), daemon=True).start()
        return run
    def reconcile(self, run_id: str) -> dict[str, Any]:
        run = self.registry.get(run_id)
        if run["status"] in {"queued", "running", "stopping"} and run.get("pid"):
            try: os.kill(int(run["pid"]), 0)
            except ProcessLookupError:
                if run["status"] == "stopping": return self.registry.transition(run_id, "cancelled", pid=None, failure_reason="用户停止")
                return self.registry.transition(run_id, "failed", pid=None, failure_reason="Worker exited without final marker")
        return run


def store_for(run: dict[str, Any]) -> EventStore: return EventStore(Path(run["output_dir"]) / "events.jsonl")
def runtime_snapshot(run: dict[str, Any]) -> dict[str, Any]:
    store = store_for(run); reducer = RuntimeSnapshotReducer(run["run_id"]); reducer.apply_all(store.after(0, 1_000_000)); result = reducer.as_dict()
    result["lifecycle"] = run["status"]; result["health"] = run["health"]; return result


def result_files(folder: Path) -> list[Path]: return sorted(folder.glob("simulation_results/*/daily_summary_*.csv"))
def results_summary(run: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in result_files(Path(run["output_dir"])):
        with path.open(encoding="utf-8", newline="") as handle: rows.extend(csv.DictReader(handle))
    return {"items": rows, "source": "simulation_results/daily_summary_*.csv", "updated_at": datetime.now(timezone.utc).isoformat()}


def paged_json_records(folder: Path, kind: str, page: int, page_size: int, date: str | None = None, asset: str | None = None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for path in sorted((folder / "trading_records").glob("*.json")):
        if path.name.endswith("_orders.json") != (kind == "orders"): continue
        if date and path.stem[:10] != date: continue
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
            values = content.values() if isinstance(content, dict) else content
            for row in values:
                if isinstance(row, dict) and (not asset or asset in json.dumps(row, ensure_ascii=False)): items.append({"date": path.stem[:10], **redact(row)})
        except (OSError, ValueError): continue
    total = len(items); start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "page": page, "page_size": page_size, "total": total, "source": "trading_records JSON"}


def results_agents(run: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    db = Path(run["output_dir"]) / f"user_{run['config']['user_count']}.db"
    if not db.is_file(): return {"items": [], "page": page, "page_size": page_size, "total": 0, "source": "unavailable"}
    with sqlite3.connect(db) as conn:
        total = conn.execute("SELECT count(*) FROM (SELECT DISTINCT user_id FROM Profiles)").fetchone()[0]
        rows = conn.execute("SELECT user_id,current_cash,total_value,return_rate,cur_positions,created_at FROM Profiles WHERE created_at=(SELECT max(created_at) FROM Profiles) ORDER BY user_id LIMIT ? OFFSET ?", (page_size, (page - 1) * page_size)).fetchall()
    return {"items": [{"agent_id": row[0], "cash": row[1], "total_value": row[2], "return_rate": row[3], "positions": row[4], "as_of": row[5]} for row in rows], "page": page, "page_size": page_size, "total": total, "source": "user database latest Profiles snapshot"}
