"""Daily synchronization orchestrator shared by HTTP, CLI and detached worker."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from backend.market_data.assets import load_assets
from backend.market_data.errors import Cancelled, MarketError
from backend.market_data.indices import TRANSFORM_VERSION, build_indices
from backend.market_data.normalize import normalize_constituents
from backend.market_data.providers.tushare import FIELDS, TushareProvider
from backend.market_data.registry import MarketRegistry, now
from backend.market_data.snapshots import fingerprint, resolve_snapshot, snapshot_path
from backend.services.data_sources import DataSourceService


def iso_date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise MarketError("INVALID_DATE_RANGE", "日期必须使用 YYYY-MM-DD 格式") from None


def supplier_date(value):
    try:
        return datetime.strptime(str(value), "%Y%m%d").date().isoformat()
    except ValueError:
        raise MarketError("TUSHARE_INVALID_RESPONSE", "供应商日期格式无效") from None


def latest_closed_date():
    current = datetime.now(ZoneInfo("Asia/Shanghai"))
    # Conservatively wait until 18:45 for post-close data to settle.
    return (current.date() if (current.hour, current.minute) >= (18, 45)
            else current.date() - timedelta(days=1)).isoformat()


class MarketSyncService:
    def __init__(self, settings):
        self.settings, self.registry = settings, MarketRegistry(settings)
        self.source = DataSourceService(settings)

    def _baseline(self):
        snapshots = self.registry.snapshots()
        # Revisions extend the latest produced snapshot, independently of activation.
        if snapshots:
            newest = max(snapshots, key=lambda item: (item["effective_through"], item["as_of"]))
            metadata, path = resolve_snapshot(self.settings, newest["snapshot_id"], allow_missing_news=True)
            return path, metadata
        return self.settings.data_dir, None

    def overview(self):
        snapshots = self.registry.snapshots()
        active = next((item for item in snapshots if item["active"]), None)
        assets, asset_hash = load_assets(self.settings.data_path("market_assets.yaml"))
        baseline, _ = self._baseline()
        stock_file = baseline / "stock_data.csv"
        dates = pd.read_csv(stock_file, usecols=["date"])["date"] if stock_file.is_file() else []
        latest = max(dates) if len(dates) else None
        return {"active_snapshot": active, "snapshots": snapshots, "jobs": self.jobs(),
                "source": self.source.get(), "assets": assets, "asset_definition_sha256": asset_hash,
                "baseline_through": latest, "latest_closed_date": latest_closed_date(),
                "suggested_start_date": sorted(set(dates))[-3] if len(set(dates)) >= 3 else latest}

    def jobs(self):
        jobs = self.registry.jobs()
        for job in jobs:
            if (job["status"] == "queued" and not job["pid"] and
                    (datetime.now(timezone.utc) - datetime.fromisoformat(job["updated_at"])).total_seconds() > 30):
                job.update(self.registry.update_job(job["job_id"], status="failed", error_code="SYNC_WORKER_START_FAILED",
                                                   error="排队任务未启动，可重新同步"))
            if job["status"] in {"queued", "running"} and job["pid"]:
                try:
                    os.kill(job["pid"], 0)
                except ProcessLookupError:
                    job.update(self.registry.update_job(job["job_id"], status="cancelled" if job["cancel_requested"] else "failed",
                        error_code="SYNC_WORKER_EXITED", error="同步进程意外退出，可重新同步", pid=None))
        return jobs

    def create(self, request, *, launch=True):
        self.jobs()  # Recover stale workers before admitting another writer.
        source = self.source.get()
        if not source["enabled"] or not source["token_configured"]:
            raise MarketError("DATA_SOURCE_UNAVAILABLE", "请在 Setting 配置并启用 Tushare")
        if request.get("source_id", "tushare") != "tushare":
            raise MarketError("DATA_SOURCE_UNSUPPORTED", "目前仅支持 Tushare")
        if not request.get("allow_missing_news", False):
            raise MarketError("NEWS_MISSING_NOT_ALLOWED", "本期尚未接入新闻，请明确允许无新闻模式")
        mode = request.get("mode", "incremental")
        if mode not in {"incremental", "backfill"}:
            raise MarketError("INVALID_SYNC_MODE", "请选择增量更新或日期回补")
        end = iso_date(request.get("end_date") or latest_closed_date())
        if end > latest_closed_date():
            raise MarketError("MARKET_NOT_CLOSED", "仅允许同步已收盘且入库的日期")
        baseline, metadata = self._baseline()
        try:
            history = pd.read_csv(baseline / "stock_data.csv")
        except OSError:
            raise MarketError("DATA_BRIDGE_MISSING", "缺少可桥接的本地历史行情") from None
        dates = sorted(set(history["date"]))
        if len(dates) < 2:
            raise MarketError("DATA_BRIDGE_MISSING", "本地历史行情为空")
        # Re-fetch three recent trading days so revisions become a new snapshot.
        start = iso_date(request.get("start_date") if mode == "backfill" else dates[max(1, len(dates) - 3)])
        if start > end or start <= dates[0]:
            raise MarketError("INVALID_DATE_RANGE", "同步范围须有桥接历史且不能跳过未同步日期")
        datasets = request.get("datasets") or ["trade_cal", "daily", "daily_basic"]
        if not {"trade_cal", "daily"}.issubset(datasets) or set(datasets) - set(FIELDS):
            raise MarketError("DATASET_UNSUPPORTED", "交易日历和日线必选；本期可选每日估值")
        job = self.registry.create_job({"source_id": "tushare", "mode": mode, "start_date": start,
            "end_date": end, "datasets": sorted(set(datasets)), "allow_missing_news": True,
            "baseline_snapshot_id": metadata["snapshot_id"] if metadata else None})
        if launch:
            env = {**os.environ, **self.settings.as_environ()}
            try:
                process = subprocess.Popen([sys.executable, "-m", "backend.market_worker", "--job-id", job["job_id"]],
                    cwd=self.settings.project_root, env=env, start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Do not overwrite terminal state if the worker finishes immediately.
                with self.registry.connection() as db:
                    db.execute("UPDATE sync_jobs SET pid=? WHERE job_id=? AND status IN ('queued','running')",
                               (process.pid, job["job_id"]))
            except OSError:
                return self.registry.update_job(job["job_id"], status="failed", error_code="SYNC_WORKER_START_FAILED",
                                                error="无法启动同步进程")
        return self.registry.job(job["job_id"])

    def activate(self, snapshot_id):
        metadata, _ = resolve_snapshot(self.settings, snapshot_id, allow_missing_news=True)
        self.registry.set_setting("active_snapshot_id", snapshot_id)
        return {**metadata, "active": True}

    def execute(self, job_id, provider=None):
        if not self.registry.claim(job_id, os.getpid()):
            return self.registry.job(job_id)
        job = self.registry.job(job_id)
        request = job["request"]
        stage = self.settings.data_path("market_staging", job_id)
        published = None

        def check():
            if self.registry.job(job_id)["cancel_requested"]:
                raise Cancelled()

        def progress(phase, value):
            check()
            self.registry.update_job(job_id, stage=phase, progress=value)

        def retry(code, delay):
            self.registry.update_job(job_id, stage="rate_limit_wait" if code == "TUSHARE_RATE_LIMITED" else "retry_wait")

        try:
            stage.mkdir(parents=True, exist_ok=False)
            (stage / "raw").mkdir()
            (stage / "normalized").mkdir()
            provider = provider or TushareProvider(self.source.token(), check=check, on_retry=retry)
            assets_document, asset_hash = load_assets(self.settings.data_path("market_assets.yaml"))
            assets = assets_document["assets"]
            if request["start_date"] < assets_document["effective_from"]:
                raise MarketError("ASSET_DEFINITION_INVALID", "同步日期早于资产定义生效日期")
            codes = {c["ts_code"] for asset in assets.values() for c in asset["constituents"]}
            if request["baseline_snapshot_id"]:
                _, baseline = resolve_snapshot(self.settings, request["baseline_snapshot_id"], allow_missing_news=True)
            else:
                baseline = self.settings.data_dir
            history = pd.read_csv(baseline / "stock_data.csv")
            history = history[history["date"] < request["start_date"]].copy()
            if set(history.ts_code.unique()) != set(assets):
                raise MarketError("DATA_BRIDGE_MISSING", "桥接历史必须包含 10 个行业指数")
            bridge_date = history["date"].max()
            if any(frame["date"].max() != bridge_date for _, frame in history.groupby("ts_code")):
                raise MarketError("DATA_BRIDGE_MISSING", "各指数的桥接日期不一致")
            start, end = request["start_date"], request["end_date"]
            calendar_start = str(history["date"].min())
            warnings = ["本期快照未接入新闻及新闻检索索引；无新闻模式已明确允许", "资金流未接入，新增日期写入空值"]

            def record(api, params, rows):
                # Persist successful data only. No token, exception or supplier error text.
                filtered = [row for row in rows if api == "trade_cal" or row.get("ts_code") in codes]
                blob = json.dumps(filtered, ensure_ascii=False, sort_keys=True).encode()
                digest = hashlib.sha256(blob).hexdigest()
                with gzip.open(stage / "raw" / (api + ".jsonl.gz"), "ab") as handle:
                    handle.write(blob + b"\n")
                with (stage / "raw" / "request_manifest.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"provider": "tushare", "api_name": api, "params": params,
                        "parameters_sha256": hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest(),
                        "fields": FIELDS[api], "response_rows": len(rows), "saved_rows": len(filtered),
                        "response_sha256": digest}) + "\n")

            progress("calendar", .05)
            calendar_rows = provider.fetch("trade_cal", {"exchange": "SSE", "start_date": calendar_start.replace("-", ""),
                                           "end_date": end.replace("-", "")}, record=record)
            calendar = pd.DataFrame(calendar_rows)
            if calendar.empty:
                raise MarketError("DATA_COVERAGE_INCOMPLETE", "交易日历为空")
            calendar["cal_date"] = calendar["cal_date"].map(supplier_date)
            calendar["pretrade_date"] = calendar["pretrade_date"].map(supplier_date)
            if not calendar["is_open"].astype(str).isin(["0", "1"]).all():
                raise MarketError("SNAPSHOT_VALIDATION_FAILED", "交易日历开市标记无效")
            calendar["is_open"] = calendar["is_open"].astype(str).map({"0": "close", "1": "open"})
            calendar = calendar.sort_values("cal_date")
            expected = pd.date_range(calendar_start, end).strftime("%Y-%m-%d").tolist()
            if calendar["cal_date"].tolist() != expected:
                raise MarketError("DATA_COVERAGE_INCOMPLETE", "交易日历存在缺口、重复或越界日期")
            opened = calendar[calendar.is_open == "open"]["cal_date"].tolist()
            prefix = calendar[(calendar.cal_date < start) & (calendar.is_open == "open")]["cal_date"].tolist()
            expected_keys = {(code, day) for code in assets for day in prefix}
            if set(zip(history.ts_code, history.date)) != expected_keys or history.duplicated(["ts_code", "date"]).any():
                raise MarketError("DATA_COVERAGE_INCOMPLETE", "桥接历史缺少交易日行情或含重复数据")
            if len(opened) < 30:
                raise MarketError("DATA_COVERAGE_INCOMPLETE", "快照历史少于 30 个交易日，无法支持 MA30")
            trading_dates = [day for day in opened if day >= start]
            if not trading_dates:
                raise MarketError("DATA_COVERAGE_INCOMPLETE", "同步范围内没有交易日")
            daily, basics = {}, {}
            optional_available = "daily_basic" in request["datasets"]
            for index, day in enumerate(trading_dates):
                progress("fetching", .1 + .55 * index / len(trading_dates))
                params = {"trade_date": day.replace("-", "")}
                rows = provider.fetch("daily", params, record=record)
                daily[day] = self._rows_by_code(rows, codes, day)
                if optional_available:
                    try:
                        rows = provider.fetch("daily_basic", params, record=record)
                        basics[day] = self._rows_by_code(rows, codes, day)
                    except MarketError as error:
                        if error.code != "TUSHARE_PERMISSION_DENIED":
                            raise
                        optional_available = False
                        warnings.append("每日估值无权限，新增估值字段保留空值")
            progress("aggregating", .7)
            output, aggregation_warnings, coverage = build_indices(assets, history, daily, basics, trading_dates)
            warnings.extend(aggregation_warnings)
            progress("validating", .8)
            new_rows = output[output.date >= start]
            if len(new_rows) != len(trading_dates) * 10 or output.duplicated(["ts_code", "date"]).any():
                raise MarketError("SNAPSHOT_VALIDATION_FAILED", "指数主键或交易日覆盖无效")
            if not (output["close"].gt(0) & output["pre_close"].gt(0)).all():
                raise MarketError("SNAPSHOT_VALIDATION_FAILED", "指数历史存在无效价格")
            # Only prior trading days are observed by a run; retain the full local history.
            output.to_csv(stage / "stock_data.csv", index=False)
            calendar.to_csv(stage / "trading_days.csv", index=False)
            news_dates = pd.date_range(calendar_start, end).strftime("%Y-%m-%d").tolist()
            # This MVP deliberately uses a wholly empty news environment, including retrieval.
            pd.DataFrame({"cal_date": news_dates, "news": [[] for _ in news_dates]}).to_pickle(stage / "sorted_impact_news.pkl")
            shutil.copyfile(self.settings.data_path("market_assets.yaml"), stage / "market_assets.yaml")
            shutil.copyfile(baseline / "stock_profile.csv", stage / "stock_profile.csv")
            for name, rows in (("calendar", calendar.to_dict("records")), ("custom_indices", new_rows.to_dict("records")),
                               ("constituents", normalize_constituents([row for group in daily.values() for row in group.values()])),
                               ("news", [{"cal_date": day, "news": []} for day in news_dates])):
                with gzip.open(stage / "normalized" / (name + ".jsonl.gz"), "wt", encoding="utf-8") as handle:
                    for row in rows:
                        handle.write(json.dumps({k: (None if isinstance(v, float) and pd.isna(v) else v)
                                                 for k, v in row.items()}, ensure_ascii=False, allow_nan=False) + "\n")
            snapshot_id = "market-" + end.replace("-", "") + "-" + job_id.removeprefix("sync-")
            metadata = {"schema_version": 1, "snapshot_id": snapshot_id, "provider": "tushare",
                "as_of": now(), "start_date": calendar_start, "effective_through": opened[-1], "calendar_through": end,
                "earliest_run_date": (date.fromisoformat(opened[29]) + timedelta(days=1)).isoformat(),
                "status": "ready_with_warnings", "created_by_job_id": job_id, "transform_version": TRANSFORM_VERSION,
                "asset_definition_sha256": asset_hash, "asset_definition_version": assets_document["schema_version"],
                "source_range": {"start_date": start, "end_date": end},
                "baseline_snapshot_id": request["baseline_snapshot_id"],
                "datasets": {"daily": {"status": "available", "through": opened[-1]},
                    "trade_cal": {"status": "available", "through": end},
                    "daily_basic": {"status": "available" if optional_available and basics else "missing"},
                    "moneyflow": {"status": "missing"}, "news": {"status": "missing", "ranking_method": "empty-v1"}},
                "units": {"close": "CNY index point", "vol": "shares (new rows); legacy volume unknown",
                          "amount": "CNY (new rows); legacy units unchanged", "elg_amount_net": "10000 CNY", "dv_ttm": "percent"},
                "quality": {"errors": [], "warnings": warnings, "constituent_coverage": coverage,
                            "minimum_weight_coverage": min(item["weight"] for item in coverage),
                            "news_missing_days": len(news_dates), "valuation_missing_values": int(new_rows[["pe_ttm", "pb", "ps_ttm", "dv_ttm"]].isna().sum().sum())},
                "files": {str(file.relative_to(stage)): fingerprint(file) for file in sorted(stage.rglob("*")) if file.is_file()}}
            (stage / "snapshot.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            for file in stage.rglob("*"):
                if file.is_file():
                    file.chmod(0o444)
            progress("publishing", .95)
            destination = snapshot_path(self.settings, snapshot_id)
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Cancellation and registry publication share a writer lock. No default activation.
            with self.registry.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT cancel_requested FROM sync_jobs WHERE job_id=?", (job_id,)).fetchone()[0]:
                    raise Cancelled()
                os.rename(stage, destination)
                published = destination
                db.execute("INSERT INTO market_snapshots VALUES (?,?)", (snapshot_id, json.dumps(metadata)))
                db.execute("UPDATE sync_jobs SET status='completed',stage='completed',progress=1,snapshot_id=?,pid=NULL,updated_at=? WHERE job_id=?",
                           (snapshot_id, now(), job_id))
            published = None
            return self.registry.job(job_id)
        except Cancelled:
            return self.registry.update_job(job_id, status="cancelled", stage="cancelled", pid=None)
        except Exception as error:
            # Do not serialize exception objects from HTTP / pandas / subprocess layers.
            code = error.code if isinstance(error, MarketError) else "SYNC_FAILED"
            message = str(error) if isinstance(error, MarketError) else "同步失败，旧快照已保留；可重新同步"
            return self.registry.update_job(job_id, status="failed", stage="failed", error_code=code, error=message, pid=None)
        finally:
            if published is not None and not any(item["snapshot_id"] == published.name for item in self.registry.snapshots()):
                shutil.rmtree(published, ignore_errors=True)

    @staticmethod
    def _rows_by_code(rows, codes, day):
        selected = {}
        for row in rows:
            code = row.get("ts_code")
            if code not in codes:
                continue
            if supplier_date(row.get("trade_date")) != day or code in selected:
                raise MarketError("SNAPSHOT_VALIDATION_FAILED", "响应含越界或重复成分股数据")
            selected[code] = row
        return selected
