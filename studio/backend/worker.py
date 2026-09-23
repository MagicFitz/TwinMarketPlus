"""Detached simulation worker. The HTTP server never runs simulation work inline."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime import RuntimeObserver
from runtime.schemas import Scope
from .registry import RunRegistry
from .services import ROOT, runtime_snapshot, store_for


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run-id", required=True); parser.add_argument("--resume", action="store_true"); args = parser.parse_args()
    registry = RunRegistry(ROOT / "studio" / "backend" / "data" / "runs.sqlite3")
    run = registry.get(args.run_id); folder, config = Path(run["output_dir"]), run["config"]
    observer = RuntimeObserver(args.run_id, store_for(run), lambda reason: registry.update(args.run_id, health="degraded", failure_reason=reason))
    registry.transition(args.run_id, "running", pid=os.getpid(), last_heartbeat=datetime.now(timezone.utc).isoformat())
    observer.started(Scope.RUN, "run", message="运行 Worker 已启动")
    try:
        if not args.resume:
            observer.started(Scope.RUN, "prepare", message="正在准备独立运行目录")
            subprocess.run([sys.executable, "script/prepare_simulation_run.py", "--template-db", config["template_db"], "--belief-source", config["belief_source"], "--user-count", str(config["user_count"]), "--user-db", str(folder / f"user_{config['user_count']}.db"), "--belief-output", str(folder / f"belief_{config['user_count']}.csv")], cwd=ROOT, check=True)
            observer.completed(Scope.RUN, "prepare", message="运行输入已准备", output_summary={"users": config["user_count"]})
        forum_db = folder / f"forum_{config['user_count']}.db"; log = folder / "simulation.log"
        command = [sys.executable, "simulation.py", "--log_dir", str(folder), "--forum_db", str(forum_db), "--user_db", str(folder / f"user_{config['user_count']}.db"), "--user_graph_save_name", f"user_graph_{config['user_count']}", "--start_date", run["checkpoint"]["next_date"] if args.resume else config["start_date"], "--end_date", config["end_date"], "--max_workers", str(config["max_workers"]), "--node", str(config["user_count"]), "--config_path", config["config_path"], "--belief_init_path", str(folder / f"belief_{config['user_count']}.csv"), "--activate_prob", str(config["activate_prob"]), "--prob_of_technical", str(config["prob_of_technical"]), "--random_seed", str(config["random_seed"]), "--checkpoint_state_path", str(folder / "state.json"), "--runtime-events", str(folder / "events.jsonl"), "--run-id", args.run_id]
        with log.open("a", encoding="utf-8") as handle:
            result = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        if result.returncode: raise RuntimeError(f"simulation exited {result.returncode}")
        # simulation.py has appended events using another EventStore instance; reopen it
        # so this terminal event continues the strictly ordered sequence.
        final_run = registry.get(args.run_id)
        observer = RuntimeObserver(args.run_id, store_for(final_run), lambda reason: registry.update(args.run_id, health="degraded", failure_reason=reason))
        observer.completed(Scope.RUN, "run", message="模拟运行完成")
        state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
        checkpoint = state.get("checkpoint", final_run["checkpoint"])
        health = "degraded" if any(item.get("event") == "stage_failed" and item.get("scope") == "agent" for item in runtime_snapshot(final_run)["diagnostics"]) else "healthy"
        registry.transition(args.run_id, "completed", pid=None, exit_code=0, health=health, checkpoint_json=json.dumps(checkpoint), last_heartbeat=datetime.now(timezone.utc).isoformat())
        return 0
    except Exception as error:
        observer.failed(Scope.RUN, "run", message="模拟运行失败", error_code=type(error).__name__, error_summary=str(error))
        registry.transition(args.run_id, "failed", pid=None, exit_code=1, failure_reason=f"{type(error).__name__}: {error}")
        return 1

if __name__ == "__main__": raise SystemExit(main())
