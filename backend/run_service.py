"""Run preparation, validation, and immutable input-manifest creation."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.schemas import redact

from .registry import ConflictError, RunRegistry
from .settings import Settings, get_settings


DEFAULTS = {
    "user_count": 10,
    "start_date": "2023-06-15",
    "end_date": "2023-06-16",
    "max_workers": 1,
    "activate_prob": 0.2,
    "prob_of_technical": 0.3,
    "random_seed": 20260916,
    "template_db": "data/sys_1000.db",
    "belief_source": "util/belief/belief_1000_0129.csv",
    "config_path": "config/api.yaml",
}


def _settings(settings: Settings | None) -> Settings:
    return settings if settings is not None else get_settings()


def safe_run_id(value: str) -> str:
    value = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.lower()).strip("-")
    return value[:64] or f"run-{uuid4().hex[:12]}"


def file_fingerprint(path: Path, settings: Settings | None = None) -> dict[str, Any]:
    """Describe a local input without reading it through a framework layer."""
    settings = _settings(settings)
    resolved = path.resolve()
    try:
        display_path = str(resolved.relative_to(settings.project_root))
    except ValueError:
        # A separately configured data directory is allowed.  The manifest still
        # needs a useful, reproducible identifier for that explicit input.
        display_path = str(resolved)
    return {
        "path": display_path,
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "bytes": resolved.stat().st_size,
    }


def git_revision(settings: Settings | None = None) -> str | None:
    settings = _settings(settings)
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=settings.project_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def normalize_config(value: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Apply existing defaults and keep file inputs constrained to the project."""
    settings = _settings(settings)
    config = {**DEFAULTS, **{key: value[key] for key in DEFAULTS if key in value}}
    if "template_db" not in value and settings.data_dir != settings.project_root / "data":
        config["template_db"] = str(settings.data_path("sys_1000.db"))
    config["user_count"] = int(config["user_count"])
    config["max_workers"] = int(config["max_workers"])
    config["random_seed"] = int(config["random_seed"])
    config["activate_prob"] = float(config["activate_prob"])
    config["prob_of_technical"] = float(config["prob_of_technical"])
    if (
        not 1 <= config["user_count"] <= 1000
        or config["max_workers"] < 1
        or not 0 <= config["activate_prob"] <= 1
        or not 0 <= config["prob_of_technical"] <= 1
    ):
        raise ValueError("用户数、并发数或概率超出允许范围")
    if config["start_date"] > config["end_date"]:
        raise ValueError("开始日期不能晚于结束日期")
    for key in ("template_db", "belief_source", "config_path"):
        path = settings.input_path(config[key]) if key == "template_db" else settings.project_path(config[key])
        try:
            config[key] = str(path.relative_to(settings.project_root))
        except ValueError:
            config[key] = str(path)
    return config


def create_run(
    registry: RunRegistry,
    request: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Allocate a private run directory and persist its registry record."""
    settings = _settings(settings)
    config = normalize_config(request.get("config") or request, settings)
    requested = request.get("run_id") or request.get("name") or f"run-{uuid4().hex[:12]}"
    run_id = safe_run_id(requested)
    output = settings.runs_dir / run_id
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    try:
        output.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ConflictError("run_id 已存在，拒绝覆盖运行目录") from error
    try:
        input_paths = {
            "agent_group_template": settings.input_path(config["template_db"]),
            "belief_source": settings.project_path(config["belief_source"]),
            "model_config": settings.project_path(config["config_path"]),
            "market_stock_data": settings.data_path("stock_data.csv"),
            "market_trading_days": settings.data_path("trading_days.csv"),
            "market_news": settings.data_path("sorted_impact_news.pkl"),
        }
        manifest = {
            "schema_version": 2,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "code_version": git_revision(settings),
            "parameters": redact(config),
            "inputs": {
                key: file_fingerprint(path, settings)
                for key, path in input_paths.items()
                if path.is_file()
            },
            "command_summary": "backend.worker -> simulation.py (arguments stored in Registry config)",
            "checkpoint_rule": {
                "resume_date": "必须等于 state.json checkpoint.next_date",
                "cleanup": "续跑日及之后的数据库记录和按日期产物将被重新生成",
            },
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output / "state.json").write_text(
            json.dumps(
                {
                    "status": "draft",
                    "checkpoint": {"last_completed_date": None, "next_date": config["start_date"]},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return registry.create(
            run_id,
            str(request.get("name") or run_id),
            str(request.get("description") or ""),
            config,
            output,
        )
    except Exception:
        # Only remove the directory allocated above; never act on a request path.
        shutil.rmtree(output, ignore_errors=True)
        raise


def validate_start(
    run: dict[str, Any],
    resume: bool = False,
    settings: Settings | None = None,
) -> list[str]:
    """Return user-facing preflight errors without launching the simulation."""
    settings = _settings(settings)
    config, folder = run["config"], Path(run["output_dir"])
    errors: list[str] = []
    for key in ("template_db", "belief_source", "config_path"):
        try:
            resolver = settings.input_path if key == "template_db" else settings.project_path
            valid = resolver(config[key]).is_file()
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            errors.append(f"缺少必要输入: {key}")
    if not settings.data_path("sorted_impact_news.pkl").is_file() or not settings.data_path(
        "trading_days.csv"
    ).is_file():
        errors.append("缺少市场数据或交易日历")
    if resume:
        next_date = run["checkpoint"].get("next_date")
        if not next_date or next_date > config["end_date"]:
            errors.append("没有可用 checkpoint 可续跑")
        for path in (
            folder / f"user_{config['user_count']}.db",
            folder / f"forum_{config['user_count']}.db",
            folder / f"belief_{config['user_count']}.csv",
        ):
            if not path.is_file():
                errors.append(f"续跑产物缺失: {path.name}")
    return errors
