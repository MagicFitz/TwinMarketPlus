"""Detached simulation worker.  The HTTP server never runs simulation work inline."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from runtime import RuntimeObserver
from runtime.schemas import Scope

from .registry import RunRegistry
from .run_service import market_environment, validate_start
from .runtime_service import runtime_snapshot, store_for
from .settings import Settings, get_settings


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def run_worker(run_id: str, *, resume: bool = False, settings: Settings | None = None) -> int:
    """Execute a registered run and persist its lifecycle marker."""
    settings = settings if settings is not None else get_settings()
    registry = RunRegistry(settings.registry_path)
    run = registry.get(run_id)
    folder, config = Path(run["output_dir"]), run["config"]
    observer = RuntimeObserver(
        run_id,
        store_for(run),
        lambda reason: registry.update(run_id, health="degraded", failure_reason=reason),
    )
    registry.transition(
        run_id,
        "running",
        pid=os.getpid(),
        last_heartbeat=datetime.now(timezone.utc).isoformat(),
    )
    observer.started(Scope.RUN, "run", message="运行 Worker 已启动")
    try:
        preflight = validate_start(run, resume, settings)
        if preflight:
            raise ValueError("; ".join(preflight))
        metadata, market_dir = market_environment(config, settings)
        simulation_env = {**os.environ, **settings.as_environ(), "TWINMARKET_DATA_DIR": str(market_dir)}
        simulation_env.pop("TUSHARE_TOKEN", None)
        simulation_env.pop("TWINMARKET_MARKET_SNAPSHOT_ID", None)
        if metadata:
            simulation_env["TWINMARKET_MARKET_SNAPSHOT_ID"] = metadata["snapshot_id"]
        if not resume:
            observer.started(Scope.RUN, "prepare", message="正在准备独立运行目录")
            subprocess.run(
                [
                    sys.executable,
                    str(settings.project_root / "script" / "prepare_simulation_run.py"),
                    "--template-db",
                    config["template_db"],
                    "--belief-source",
                    config["belief_source"],
                    "--user-count",
                    str(config["user_count"]),
                    "--user-db",
                    str(folder / f"user_{config['user_count']}.db"),
                    "--belief-output",
                    str(folder / f"belief_{config['user_count']}.csv"),
                    *(["--market-snapshot", str(market_dir), "--start-date", config["start_date"]] if metadata else []),
                ],
                cwd=settings.project_root,
                env=simulation_env,
                check=True,
            )
            observer.completed(
                Scope.RUN,
                "prepare",
                message="运行输入已准备",
                output_summary={"users": config["user_count"]},
            )
        forum_db = folder / f"forum_{config['user_count']}.db"
        log = folder / "simulation.log"
        command = [
            sys.executable,
            str(settings.project_root / "simulation.py"),
            "--log_dir",
            str(folder),
            "--forum_db",
            str(forum_db),
            "--user_db",
            str(folder / f"user_{config['user_count']}.db"),
            "--user_graph_save_name",
            f"user_graph_{config['user_count']}",
            "--start_date",
            run["checkpoint"]["next_date"] if resume else config["start_date"],
            "--end_date",
            config["end_date"],
            "--max_workers",
            str(config["max_workers"]),
            "--node",
            str(config["user_count"]),
            "--config_path",
            config["config_path"],
            "--belief_init_path",
            str(folder / f"belief_{config['user_count']}.csv"),
            "--activate_prob",
            str(config["activate_prob"]),
            "--prob_of_technical",
            str(config["prob_of_technical"]),
            "--random_seed",
            str(config["random_seed"]),
            "--checkpoint_state_path",
            str(folder / "state.json"),
            "--runtime-events",
            str(folder / "events.jsonl"),
            "--run-id",
            run_id,
        ]
        if resume:
            command.append("--checkpoint")
        with log.open("a", encoding="utf-8") as handle:
            result = subprocess.run(
                command,
                cwd=settings.project_root,
                env=simulation_env,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        if result.returncode:
            raise RuntimeError(f"simulation exited {result.returncode}")
        # simulation.py has appended events using another EventStore instance;
        # reopen it so this terminal event continues the ordered sequence.
        final_run = registry.get(run_id)
        observer = RuntimeObserver(
            run_id,
            store_for(final_run),
            lambda reason: registry.update(run_id, health="degraded", failure_reason=reason),
        )
        observer.completed(Scope.RUN, "run", message="模拟运行完成")
        state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
        checkpoint = state.get("checkpoint", final_run["checkpoint"])
        health = (
            "degraded"
            if any(
                item.get("event") == "stage_failed" and item.get("scope") == "agent"
                for item in runtime_snapshot(final_run)["diagnostics"]
            )
            else "healthy"
        )
        registry.transition(
            run_id,
            "completed",
            pid=None,
            exit_code=0,
            health=health,
            checkpoint_json=json.dumps(checkpoint),
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
        )
        return 0
    except Exception as error:
        observer.failed(
            Scope.RUN,
            "run",
            message="模拟运行失败",
            error_code=type(error).__name__,
            error_summary=str(error),
        )
        registry.transition(
            run_id,
            "failed",
            pid=None,
            exit_code=1,
            failure_reason=f"{type(error).__name__}: {error}",
        )
        return 1


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    args = _arguments(argv)
    return run_worker(args.run_id, resume=args.resume, settings=settings)


if __name__ == "__main__":
    raise SystemExit(main())
