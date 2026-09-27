"""FastAPI control and query plane for TwinMarket's standalone backend."""
from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.process_manager import ProcessManager
from backend.registry import ConflictError, NotFoundError, RunRegistry
from backend.results import (
    artifact_items,
    csv_export_chunks,
    downloadable_artifact,
    json_export_chunks,
    paged_json_records,
    results_agents,
    results_social,
    results_summary,
)
from backend.run_service import create_run, normalize_config
from backend.runtime_service import runtime_snapshot, store_for
from backend.services.agents import AgentService
from backend.services.catalog import CatalogService
from backend.services.documentation import DocumentationService
from backend.services.logs import LogService
from backend.services.market import MarketService
from backend.services.model_settings import ModelSettingsService
from backend.settings import Settings, get_settings


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    run_id: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)


class LanguageModelUpdate(BaseModel):
    api_type: str = Field(default="openai", max_length=32)
    provider: str = Field(default="", max_length=80)
    model_name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=1000)
    timeout: int | float | None = Field(default=None, ge=0)
    # Omit this field to keep the current secret. Send an empty string to clear it.
    api_key: str | None = Field(default=None, max_length=2000)


class EmbeddingModelUpdate(BaseModel):
    provider: str = Field(default="", max_length=80)
    model_name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=1000)
    endpoint: str = Field(default="", max_length=1000)
    timeout: int | float | None = Field(default=None, ge=0)
    max_retries: int | None = Field(default=None, ge=0)
    # Omit this field to keep the current secret. Send an empty string to clear it.
    api_key: str | None = Field(default=None, max_length=2000)


def _safe_output_dir(run: dict[str, Any], settings: Settings) -> Path:
    """Return a registered run directory only when it stays below RUNS_DIR."""
    folder = Path(run["output_dir"]).resolve()
    runs_dir = settings.runs_dir.resolve()
    if folder.parent != runs_dir:
        raise ValueError("非法运行目录")
    return folder


def _safe_run(run: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Validate a Registry row before passing it to an artifact reader."""
    _safe_output_dir(run, settings)
    return run


def create_app(
    settings: Settings | None = None,
    *,
    registry: RunRegistry | None = None,
    manager: ProcessManager | None = None,
) -> FastAPI:
    """Build an injectable app while preserving the established HTTP contract."""
    settings = settings or get_settings()
    registry = registry or RunRegistry(settings.registry_path)
    manager = manager or ProcessManager(registry, settings)
    catalog_service = CatalogService(settings)
    model_settings_service = ModelSettingsService(settings)
    documentation_service = DocumentationService(settings)
    agent_service = AgentService(settings)
    market_service = MarketService(settings)
    log_service = LogService(settings)

    app = FastAPI(title="TwinMarket Control API", version="1.0")
    app.state.settings = settings
    app.state.registry = registry
    app.state.manager = manager

    # The Vite proxy needs no CORS exchange, but standalone deployments do.
    # Origins are deliberately explicit and environment-configured rather than
    # accepting arbitrary browsers on this unauthenticated local control plane.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def not_found(_, __):
        return JSONResponse(status_code=404, content={"error": "找不到运行实例"})

    @app.exception_handler(ConflictError)
    async def conflict(_, error):
        return JSONResponse(status_code=409, content={"error": str(error)})

    @app.exception_handler(ValueError)
    async def invalid(_, error):
        return JSONResponse(status_code=422, content={"error": str(error)})

    @app.exception_handler(KeyError)
    async def legacy_not_found(_, __):
        return JSONResponse(status_code=404, content={"error": "找不到该资源"})

    @app.exception_handler(OSError)
    async def unavailable_os(_, __):
        return JSONResponse(status_code=503, content={"error": "数据暂不可用，请稍后刷新；现有数据已保留"})

    @app.exception_handler(sqlite3.Error)
    async def unavailable_sqlite(_, __):
        return JSONResponse(status_code=503, content={"error": "数据暂不可用，请稍后刷新；现有数据已保留"})

    def registered_output_dir(run_id: str) -> Path | None:
        """Use Registry outputs when available, then preserve legacy logs access."""
        try:
            return _safe_output_dir(registry.get(run_id), settings)
        except NotFoundError:
            return None

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        # Deliberately avoids a model invocation.
        return {
            "status": "ready",
            "registry": registry.path.is_file(),
            "market_data": settings.data_path("trading_days.csv").is_file(),
        }

    @app.get("/api/catalog")
    def catalog():
        return catalog_service.catalog()

    @app.get("/api/settings/models")
    def model_settings():
        return model_settings_service.get_all()

    @app.put("/api/settings/models/language")
    def update_language_model(body: LanguageModelUpdate):
        return model_settings_service.update(
            "language", body.model_dump(exclude_unset=True), api_key_provided="api_key" in body.model_fields_set
        )

    @app.put("/api/settings/models/embedding")
    def update_embedding_model(body: EmbeddingModelUpdate):
        return model_settings_service.update(
            "embedding", body.model_dump(exclude_unset=True), api_key_provided="api_key" in body.model_fields_set
        )

    @app.get("/api/documentation")
    def documentation(path: str | None = None):
        return documentation_service.documentation(path)

    @app.get("/api/runs/{run_id}/agents")
    def legacy_agents(run_id: str, q: str = "", page: int = Query(1, ge=1)):
        return agent_service.members(run_id, q, page, registered_output_dir(run_id))

    @app.get("/api/runs/{run_id}/agents/{agent_id}")
    def legacy_agent_detail(run_id: str, agent_id: str):
        return agent_service.member_detail(run_id, agent_id, registered_output_dir(run_id))

    @app.get("/api/runs/{run_id}/market")
    def legacy_market(run_id: str, asset: str | None = None):
        return market_service.market(run_id, asset, registered_output_dir(run_id))

    @app.post("/api/runs", status_code=201)
    def post_run(body: RunCreate):
        return create_run(registry, body.model_dump(), settings)

    @app.get("/api/runs")
    def get_runs(
        status: str | None = None,
        archived: bool = False,
        page: int = Query(1, ge=1),
        page_size: int = Query(30, ge=1, le=100),
    ):
        items, total = registry.list(
            status=status,
            archived=archived,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return manager.reconcile(run_id)

    @app.patch("/api/runs/{run_id}")
    def edit_draft(run_id: str, body: RunCreate):
        run = registry.get(run_id)
        if run["status"] != "draft":
            raise ConflictError("已启动运行的配置不可原地修改；请复制为新实例")
        # Reuse create-time normalization without allocating a directory.
        config = normalize_config(body.config, settings)
        return registry.update(
            run_id,
            name=body.name,
            description=body.description,
            config_json=json.dumps(config),
        )

    @app.post("/api/runs/{run_id}/copy", status_code=201)
    def copy_run(run_id: str):
        source = registry.get(run_id)
        return create_run(
            registry,
            {
                "name": f"{source['name']} 副本",
                "description": source["description"],
                "config": source["config"],
            },
            settings,
        )

    @app.post("/api/runs/{run_id}/start")
    def start(run_id: str):
        return manager.start(run_id)

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str):
        return manager.stop(run_id)

    @app.post("/api/runs/{run_id}/resume")
    def resume(run_id: str):
        return manager.start(run_id, resume=True)

    @app.post("/api/runs/{run_id}/archive")
    def archive(run_id: str):
        run = registry.get(run_id)
        if run["status"] in {"running", "queued", "stopping"}:
            raise ConflictError("活动运行不能归档")
        return registry.update(run_id, archived=True)

    @app.delete("/api/runs/{run_id}", status_code=204)
    def delete(run_id: str):
        run = registry.get(run_id)
        if run["status"] != "draft":
            raise ConflictError("仅未运行草稿允许安全删除")
        shutil.rmtree(_safe_output_dir(run, settings))
        with registry.connection() as connection:
            connection.execute("DELETE FROM runs WHERE run_id=?", (run_id,))

    @app.get("/api/runs/{run_id}/runtime")
    def runtime(run_id: str):
        run = manager.reconcile(run_id)
        snapshot = runtime_snapshot(run)
        registry.update(run_id, last_event_id=snapshot["last_event_id"])
        return snapshot

    @app.get("/api/runs/{run_id}/agents/{agent_id}/runtime")
    def agent_runtime(run_id: str, agent_id: str):
        snapshot = runtime_snapshot(manager.reconcile(run_id))
        for agent in snapshot["agents"]:
            if agent["agent_id"] == agent_id:
                return agent
        raise HTTPException(404, "当前事件中没有此 Agent")

    @app.get("/api/runs/{run_id}/diagnostics")
    def diagnostics(run_id: str):
        run = manager.reconcile(run_id)
        snapshot = runtime_snapshot(run)
        return {
            "run_id": run_id,
            "health": run["health"],
            "pid": run["pid"],
            "exit_code": run["exit_code"],
            "failure_reason": run["failure_reason"],
            "events": snapshot["diagnostics"],
        }

    @app.get("/api/runs/{run_id}/events")
    async def events(
        run_id: str,
        last_event_id: int = Query(0, ge=0),
        last_event_header: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        run = manager.reconcile(run_id)
        store = store_for(run)
        try:
            cursor = max(last_event_id, int(last_event_header or 0))
        except ValueError:
            cursor = last_event_id

        async def generate():
            nonlocal cursor
            while True:
                batch = store.after(cursor, 200)
                if batch:
                    for item in batch:
                        cursor = item.event_id
                        yield f"id: {cursor}\nevent: runtime\ndata: {json.dumps(item.as_dict(), ensure_ascii=False)}\n\n"
                else:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(1)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/results/summary")
    def summary(run_id: str):
        return results_summary(_safe_run(registry.get(run_id), settings))

    @app.get("/api/runs/{run_id}/results/trades")
    def trades(
        run_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        date: str | None = None,
        asset: str | None = None,
    ):
        run = registry.get(run_id)
        return paged_json_records(_safe_output_dir(run, settings), "trades", page, page_size, date, asset)

    @app.get("/api/runs/{run_id}/results/orders")
    def orders(
        run_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        date: str | None = None,
        asset: str | None = None,
    ):
        run = registry.get(run_id)
        return paged_json_records(_safe_output_dir(run, settings), "orders", page, page_size, date, asset)

    @app.get("/api/runs/{run_id}/results/agents")
    def agents(
        run_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ):
        return results_agents(_safe_run(registry.get(run_id), settings), page, page_size)

    @app.get("/api/runs/{run_id}/results/social")
    def social(run_id: str):
        return results_social(_safe_run(registry.get(run_id), settings))

    @app.get("/api/runs/{run_id}/results/{kind}/export")
    def export_results(
        run_id: str,
        kind: str,
        format: str = Query("json", pattern="^(json|csv)$"),
    ):
        if kind not in {"trades", "orders"}:
            raise HTTPException(404, "不支持导出的结果类型")
        folder = _safe_output_dir(registry.get(run_id), settings)
        if format == "json":
            return StreamingResponse(
                json_export_chunks(folder, kind),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{run_id}-{kind}.json"'},
            )
        return StreamingResponse(
            csv_export_chunks(folder, kind),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{run_id}-{kind}.csv"'},
        )

    @app.get("/api/runs/{run_id}/artifacts")
    def artifacts(run_id: str):
        return artifact_items(_safe_run(registry.get(run_id), settings))

    @app.get("/api/runs/{run_id}/artifacts/{artifact_path:path}")
    def artifact_download(run_id: str, artifact_path: str):
        target = downloadable_artifact(_safe_run(registry.get(run_id), settings), artifact_path)
        if target is None:
            raise HTTPException(404, "产物不可下载")
        return FileResponse(target, filename=target.name)

    @app.get("/api/runs/{run_id}/logs")
    def logs(
        run_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=500),
    ):
        run = registry.get(run_id)
        return log_service.read_logs(_safe_output_dir(run, settings), page, page_size)

    return app


app = create_app()
# Convenient module attributes for integrations that used the former module's
# singleton names.  Route closures deliberately keep the matching injected
# instances on ``app.state``.
REGISTRY: RunRegistry = app.state.registry
MANAGER: ProcessManager = app.state.manager
SETTINGS: Settings = app.state.settings
