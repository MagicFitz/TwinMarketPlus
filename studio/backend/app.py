"""FastAPI control/query plane for the local Runtime Observatory."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .registry import ConflictError, NotFoundError, RunRegistry
from .services import (ROOT, ProcessManager, create_run, paged_json_records, results_agents,
                       results_summary, runtime_snapshot, store_for)

REGISTRY = RunRegistry(ROOT / "studio" / "backend" / "data" / "runs.sqlite3")
MANAGER = ProcessManager(REGISTRY)
app = FastAPI(title="TwinMarket Control API", version="1.0")


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    run_id: str | None = Field(default=None, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)


@app.exception_handler(NotFoundError)
async def not_found(_, __): return __import__("fastapi").responses.JSONResponse(status_code=404, content={"error": "找不到运行实例"})

@app.exception_handler(ConflictError)
async def conflict(_, error): return __import__("fastapi").responses.JSONResponse(status_code=409, content={"error": str(error)})

@app.exception_handler(ValueError)
async def invalid(_, error): return __import__("fastapi").responses.JSONResponse(status_code=422, content={"error": str(error)})


@app.get("/health/live")
def live(): return {"status": "ok"}


@app.get("/health/ready")
def ready():
    # Deliberately avoids any model invocation.
    return {"status": "ready", "registry": REGISTRY.path.is_file(), "market_data": (ROOT / "data/trading_days.csv").is_file()}


# Existing resource pages remain a read-only migration boundary. They continue to
# use server.py's mode=ro/query_only helpers and are deliberately separate from
# the Run Registry write API.
@app.get("/api/catalog")
def catalog():
    from studio.server import catalog as legacy_catalog
    return legacy_catalog()


@app.get("/api/documentation")
def documentation(path: str | None = None):
    from studio.server import documentation as legacy_documentation
    return legacy_documentation({} if path is None else {"path": [path]})


@app.get("/api/runs/{run_id}/agents")
def legacy_agents(run_id: str, q: str = "", page: int = Query(1, ge=1)):
    from studio.server import get_db, members
    get_db(run_id)  # validates the known read-only run/template boundary
    return members(run_id, {"q": [q], "page": [str(page)]})


@app.get("/api/runs/{run_id}/agents/{agent_id}")
def legacy_agent_detail(run_id: str, agent_id: str):
    from studio.server import member_detail
    return member_detail(run_id, agent_id)


@app.get("/api/runs/{run_id}/market")
def legacy_market(run_id: str, asset: str | None = None):
    from studio.server import market
    return market(run_id, asset)


@app.post("/api/runs", status_code=201)
def post_run(body: RunCreate): return create_run(REGISTRY, body.model_dump())


@app.get("/api/runs")
def get_runs(status: str | None = None, archived: bool = False, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    items, total = REGISTRY.list(status=status, archived=archived, offset=(page - 1) * page_size, limit=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str): return MANAGER.reconcile(run_id)


@app.patch("/api/runs/{run_id}")
def edit_draft(run_id: str, body: RunCreate):
    run = REGISTRY.get(run_id)
    if run["status"] != "draft": raise ConflictError("已启动运行的配置不可原地修改；请复制为新实例")
    # create_run's normalization is intentionally reused without allocating a directory.
    from .services import normalize_config
    config = normalize_config(body.config)
    return REGISTRY.update(run_id, name=body.name, description=body.description, config_json=__import__("json").dumps(config))


@app.post("/api/runs/{run_id}/copy", status_code=201)
def copy_run(run_id: str):
    source = REGISTRY.get(run_id)
    return create_run(REGISTRY, {"name": f"{source['name']} 副本", "description": source["description"], "config": source["config"]})


@app.post("/api/runs/{run_id}/start")
def start(run_id: str): return MANAGER.start(run_id)


@app.post("/api/runs/{run_id}/stop")
def stop(run_id: str): return MANAGER.stop(run_id)


@app.post("/api/runs/{run_id}/resume")
def resume(run_id: str): return MANAGER.start(run_id, resume=True)


@app.post("/api/runs/{run_id}/archive")
def archive(run_id: str):
    run = REGISTRY.get(run_id)
    if run["status"] in {"running", "queued", "stopping"}: raise ConflictError("活动运行不能归档")
    return REGISTRY.update(run_id, archived=True)


@app.delete("/api/runs/{run_id}", status_code=204)
def delete(run_id: str):
    run = REGISTRY.get(run_id)
    if run["status"] != "draft": raise ConflictError("仅未运行草稿允许安全删除")
    folder = Path(run["output_dir"])
    if folder.parent.resolve() != (ROOT / "runs").resolve(): raise ValueError("非法运行目录")
    shutil.rmtree(folder)
    with REGISTRY.connection() as conn: conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))


@app.get("/api/runs/{run_id}/runtime")
def runtime(run_id: str):
    run = MANAGER.reconcile(run_id); snapshot = runtime_snapshot(run)
    REGISTRY.update(run_id, last_event_id=snapshot["last_event_id"])
    return snapshot


@app.get("/api/runs/{run_id}/agents/{agent_id}/runtime")
def agent_runtime(run_id: str, agent_id: str):
    snapshot = runtime_snapshot(MANAGER.reconcile(run_id))
    for agent in snapshot["agents"]:
        if agent["agent_id"] == agent_id: return agent
    raise HTTPException(404, "当前事件中没有此 Agent")


@app.get("/api/runs/{run_id}/diagnostics")
def diagnostics(run_id: str):
    run = MANAGER.reconcile(run_id); snapshot = runtime_snapshot(run)
    return {"run_id": run_id, "health": run["health"], "pid": run["pid"], "exit_code": run["exit_code"], "failure_reason": run["failure_reason"], "events": snapshot["diagnostics"]}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, last_event_id: int = Query(0, ge=0), last_event_header: str | None = Header(default=None, alias="Last-Event-ID")):
    run = MANAGER.reconcile(run_id); store = store_for(run)
    try: cursor = max(last_event_id, int(last_event_header or 0))
    except ValueError: cursor = last_event_id
    async def generate():
        nonlocal cursor
        while True:
            batch = store.after(cursor, 200)
            if batch:
                for item in batch:
                    cursor = item.event_id
                    import json
                    yield f"id: {cursor}\nevent: runtime\ndata: {json.dumps(item.as_dict(), ensure_ascii=False)}\n\n"
            else:
                yield ": keepalive\n\n"
                await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/runs/{run_id}/results/summary")
def summary(run_id: str): return results_summary(REGISTRY.get(run_id))


@app.get("/api/runs/{run_id}/results/trades")
def trades(run_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), date: str | None = None, asset: str | None = None):
    return paged_json_records(Path(REGISTRY.get(run_id)["output_dir"]), "trades", page, page_size, date, asset)


@app.get("/api/runs/{run_id}/results/orders")
def orders(run_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), date: str | None = None, asset: str | None = None):
    return paged_json_records(Path(REGISTRY.get(run_id)["output_dir"]), "orders", page, page_size, date, asset)


@app.get("/api/runs/{run_id}/results/agents")
def agents(run_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)): return results_agents(REGISTRY.get(run_id), page, page_size)


@app.get("/api/runs/{run_id}/results/social")
def social(run_id: str):
    folder = Path(REGISTRY.get(run_id)["output_dir"])
    return {name: len(list((folder / name).glob("*.json"))) for name in ("post_records", "reaction_records")}


@app.get("/api/runs/{run_id}/results/{kind}/export")
def export_results(run_id: str, kind: str, format: str = Query("json", pattern="^(json|csv)$")):
    if kind not in {"trades", "orders"}: raise HTTPException(404, "不支持导出的结果类型")
    folder = Path(REGISTRY.get(run_id)["output_dir"]) / "trading_records"
    files = [path for path in sorted(folder.glob("*.json")) if path.name.endswith("_orders.json") == (kind == "orders")]
    def records():
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8")); values = data.values() if isinstance(data, dict) else data
                for value in values:
                    if isinstance(value, dict): yield {"date": path.stem[:10], **value}
            except (OSError, ValueError): continue
    if format == "json":
        def json_stream():
            yield "["; first = True
            for value in records():
                if not first: yield ","
                first = False; yield json.dumps(value, ensure_ascii=False, default=str)
            yield "]"
        return StreamingResponse(json_stream(), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{run_id}-{kind}.json"'})
    def csv_stream():
        first = True
        for value in records():
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(value), extrasaction="ignore")
            if first: writer.writeheader(); first = False
            writer.writerow({key: json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else item for key, item in value.items()})
            yield output.getvalue()
    return StreamingResponse(csv_stream(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{run_id}-{kind}.csv"'})


@app.get("/api/runs/{run_id}/artifacts")
def artifacts(run_id: str):
    folder = Path(REGISTRY.get(run_id)["output_dir"])
    items = [{"path": path.relative_to(folder).as_posix(), "bytes": path.stat().st_size} for path in folder.rglob("*") if path.is_file() and path.name not in {"run.lock"}]
    return {"items": items}


@app.get("/api/runs/{run_id}/artifacts/{artifact_path:path}")
def artifact_download(run_id: str, artifact_path: str):
    folder = Path(REGISTRY.get(run_id)["output_dir"]).resolve(); target = (folder / artifact_path).resolve()
    if not target.is_relative_to(folder) or not target.is_file() or target.suffix not in {".csv", ".json", ".txt"}: raise HTTPException(404, "产物不可下载")
    return FileResponse(target, filename=target.name)


@app.get("/api/runs/{run_id}/logs")
def logs(run_id: str, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500)):
    # Product state comes from RuntimeEvent. This endpoint exposes only the existing
    # strict safe operational-log allowlist, never model output or credentials.
    from studio.server import clean_log
    path = Path(REGISTRY.get(run_id)["output_dir"]) / "simulation.log"
    if not path.is_file(): return {"items": [], "page": page, "page_size": page_size, "total": 0}
    lines = clean_log(path.read_text(encoding="utf-8", errors="replace"))
    start = (page - 1) * page_size
    return {"items": lines[start:start + page_size], "page": page, "page_size": page_size, "total": len(lines)}
