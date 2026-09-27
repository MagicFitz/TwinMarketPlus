"""Safe operational-log extraction for Runtime diagnostics."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.settings import Settings

from .read_only import ReadOnlyStore, WorkspacePathError


SAFE_CONFIG = (
    "start_date",
    "end_date",
    "node",
    "max_workers",
    "activate_prob",
    "prob_of_technical",
    "similarity_threshold",
    "time_decay_factor",
)


def config_from_log(head: str) -> dict[str, Any]:
    """Extract only the historical, non-sensitive simulation config allowlist."""
    match = re.search(r"=== 模拟配置参数 ===\s*(\{.*?\})", head, re.S)
    try:
        config = json.loads(match.group(1)) if match else {}
    except ValueError:
        config = {}
    return {key: config[key] for key in SAFE_CONFIG if key in config}


def clean_log(tail: str) -> list[str]:
    """Return the strict public allowlist of operational log events.

    Raw model responses, prompts, credentials, HTTP request lines, and arbitrary
    application log text are deliberately excluded.
    """
    allowed = (
        r"=== 当前日期: \d{4}-\d{2}-\d{2} ===",
        r"交易日: (?:True|False)",
        r"用户关系图属性: \d+ 个节点, \d+ 条边",
        r"开始处理 \d+ 个用户，使用 \d+ 个工作线程",
        r"成功处理 \d+ 个用户",
        r"=== 模拟系统运行完成 ===",
        r"处理输入 \d{4}-\d{2}-\d{2}:\s*\d+%",
    )
    output: list[str] = []
    for line in tail.replace("\r", "\n").splitlines():
        line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()
        for pattern in allowed:
            match = re.match(pattern, line)
            if match:
                event = match.group(0)
                if not output or event != output[-1]:
                    output.append(event)
                break
    return output[-16:]


class LogService:
    """Read logs only from configured run output folders."""

    def __init__(self, settings: Settings, store: ReadOnlyStore | None = None):
        self.settings = settings
        self.store = store or ReadOnlyStore(settings)
        self.project_root = Path(settings.project_root).resolve()
        self.runs_dir = Path(settings.runs_dir).resolve()

    def _registry_folder(self, output_dir: Path | str) -> Path:
        folder = self.store.local(output_dir)
        if not folder.is_relative_to(self.runs_dir) or folder == self.runs_dir or not folder.is_dir():
            raise WorkspacePathError("Run output is outside the configured runs directory")
        return folder

    def log_data(self, folder: Path | str) -> tuple[str, str, float | None]:
        """Read the bounded head/tail of the latest legacy ``simulation*.log`` file."""
        resolved_folder = self.store.local(folder)
        paths = [self.store.local(path) for path in resolved_folder.glob("simulation*.log")]
        if not paths:
            return "", "", None
        path = max(paths, key=lambda item: item.stat().st_mtime)
        with path.open("rb") as handle:
            head = handle.read(65536).decode("utf-8", errors="replace")
            size = handle.seek(0, 2)
            handle.seek(max(0, size - 131072))
            tail = handle.read().decode("utf-8", errors="replace")
        return head, tail, max(0, datetime.now().timestamp() - path.stat().st_mtime)

    def read_logs(self, output_dir: Path | str, page: int = 1, page_size: int = 100) -> dict[str, Any]:
        """Return the current FastAPI log DTO for a Registry-owned run folder."""
        folder = self._registry_folder(output_dir)
        path = (folder / "simulation.log").resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            return {"items": [], "page": page, "page_size": page_size, "total": 0}
        lines = clean_log(path.read_text(encoding="utf-8", errors="replace"))
        start = (page - 1) * page_size
        return {
            "items": lines[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(lines),
        }

    def read_run_logs(
        self,
        run_id: str,
        output_dir: Path | str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Read a registered/current/legacy run log through the safe run resolver."""
        folder = self.store.resolve_run_folder(run_id, output_dir)
        path = (folder / "simulation.log").resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            return {"items": [], "page": page, "page_size": page_size, "total": 0}
        lines = clean_log(path.read_text(encoding="utf-8", errors="replace"))
        start = (page - 1) * page_size
        return {
            "items": lines[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(lines),
        }


def log_data(settings: Settings, folder: Path | str) -> tuple[str, str, float | None]:
    return LogService(settings).log_data(folder)


def read_logs(settings: Settings, output_dir: Path | str, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    return LogService(settings).read_logs(output_dir, page, page_size)


def read_run_logs(
    settings: Settings,
    run_id: str,
    output_dir: Path | str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    return LogService(settings).read_run_logs(run_id, output_dir, page, page_size)
