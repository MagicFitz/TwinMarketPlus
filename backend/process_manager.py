"""Detached Worker lifecycle management for registered simulation runs."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from runtime import RuntimeObserver
from runtime.schemas import Scope

from .registry import ConflictError, RunRegistry
from .run_service import validate_start
from .runtime_service import store_for
from .settings import Settings, get_settings


class ProcessManager:
    def __init__(
        self,
        registry: RunRegistry,
        settings: Settings | int | None = None,
        max_concurrency: int = 2,
    ):
        # Accept the former positional ``ProcessManager(registry, 2)`` shape
        # while making the standalone Settings dependency the normal second
        # argument.
        if isinstance(settings, int):
            max_concurrency, settings = settings, None
        self.registry = registry
        self.max_concurrency = max_concurrency
        self.settings = settings if settings is not None else get_settings()

    def start(self, run_id: str, resume: bool = False) -> dict:
        run = self.registry.get(run_id)
        if resume and run["status"] not in {"failed", "cancelled"}:
            raise ConflictError("仅失败或已取消的运行可以从 checkpoint 续跑")
        if run["status"] in {"queued", "running"}:
            return run  # idempotent
        errors = validate_start(run, resume, self.settings)
        if errors:
            raise ValueError("; ".join(errors))
        active, _ = self.registry.list(status="running", limit=1000)
        queued, _ = self.registry.list(status="queued", limit=1000)
        if len(active) + len(queued) >= self.max_concurrency:
            raise ConflictError("本机运行配额已满")
        run = self.registry.transition(run_id, "queued")
        command = [sys.executable, "-m", "backend.worker", "--run-id", run_id]
        if resume:
            command.append("--resume")
        worker_environment = os.environ.copy()
        worker_environment.update(self.settings.as_environ())
        process = subprocess.Popen(
            command,
            cwd=self.settings.project_root,
            env=worker_environment,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return self.registry.update(
            run_id,
            pid=process.pid,
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
        )

    def stop(self, run_id: str) -> dict:
        run = self.registry.get(run_id)
        if run["status"] == "cancelled":
            return run
        if run["status"] not in {"queued", "running", "stopping"}:
            raise ConflictError("当前状态不能停止")
        if run["status"] != "stopping":
            run = self.registry.transition(run_id, "stopping")
        RuntimeObserver(
            run_id,
            store_for(run),
            lambda reason: self.registry.update(run_id, health="degraded", failure_reason=reason),
        ).started(Scope.RUN, "stop", message="已请求温和停止")
        if run["pid"]:
            try:
                os.killpg(os.getpgid(run["pid"]), signal.SIGTERM)
            except ProcessLookupError:
                pass

            def escalate(pid: int, expected_run: str) -> None:
                time.sleep(10)
                latest = self.registry.get(expected_run)
                if latest["status"] != "stopping":
                    return
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.registry.transition(
                    expected_run,
                    "cancelled",
                    pid=None,
                    failure_reason="用户停止：温和终止超时后升级",
                )

            threading.Thread(
                target=escalate,
                args=(int(run["pid"]), run_id),
                daemon=True,
            ).start()
        return run

    def reconcile(self, run_id: str) -> dict:
        run = self.registry.get(run_id)
        if run["status"] in {"queued", "running", "stopping"} and run.get("pid"):
            try:
                os.kill(int(run["pid"]), 0)
            except ProcessLookupError:
                if run["status"] == "stopping":
                    return self.registry.transition(
                        run_id,
                        "cancelled",
                        pid=None,
                        failure_reason="用户停止",
                    )
                return self.registry.transition(
                    run_id,
                    "failed",
                    pid=None,
                    failure_reason="Worker exited without final marker",
                )
        return run
