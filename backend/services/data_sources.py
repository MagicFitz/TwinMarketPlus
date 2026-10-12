"""Credential-safe settings with explicit keep / replace / clear semantics."""
import os
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

from backend.market_data.errors import MarketError
from backend.market_data.providers.tushare import TushareProvider
from backend.market_data.registry import MarketRegistry, now


class DataSourceService:
    def __init__(self, settings):
        self.settings, self.registry = settings, MarketRegistry(settings)
        self.path = settings.project_path("config/data_sources.yaml")

    def _read(self):
        if not self.path.is_file():
            return {}
        try:
            value = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            raise MarketError("DATA_SOURCE_CONFIG_INVALID", "数据源配置格式无效") from None
        if not isinstance(value, dict):
            raise MarketError("DATA_SOURCE_CONFIG_INVALID", "数据源配置格式无效")
        return value

    def token(self):
        return os.environ.get("TUSHARE_TOKEN", "").strip() or str(self._read().get("token") or "").strip()

    def get(self):
        config = self._read()
        probe = self.registry.setting("tushare_capabilities", {})
        configured, enabled = bool(self.token()), bool(config.get("enabled", True))
        states = [item["status"] for item in probe.get("capabilities", {}).values()]
        state = "unconfigured" if not configured else "untested" if not states else (
            "available" if all(s == "available" for s in states) else
            "failed" if any(probe["capabilities"].get(k, {}).get("status") != "available"
                            for k in ("trade_cal", "daily")) else "partial")
        return {"source_id": "tushare", "provider": "tushare", "enabled": enabled,
                "token_configured": configured,
                "credential_source": "environment" if os.environ.get("TUSHARE_TOKEN", "").strip() else "local",
                "status": state, "last_tested_at": probe.get("last_tested_at"),
                "capabilities": probe.get("capabilities", {}),
                "deferred_datasets": ["moneyflow", "news", "sw_daily", "rt_sw_k"]}

    def update(self, changes):
        config = self._read()
        if "token" in changes:
            token = str(changes.get("token") or "").strip()
            if token:
                config["token"] = token
            else:
                config.pop("token", None)
            self.registry.set_setting("tushare_capabilities", {})
        if "enabled" in changes:
            config["enabled"] = bool(changes["enabled"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".data-sources-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                yaml.safe_dump(config, handle)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.get()

    def test(self, provider=None):
        if not self.get()["enabled"]:
            raise MarketError("DATA_SOURCE_DISABLED", "数据源已停用")
        provider = provider or TushareProvider(self.token())
        end = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)).strftime("%Y%m%d")
        start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=14)).strftime("%Y%m%d")
        capabilities = {}
        trading_date = None
        for api in ("trade_cal", "daily", "daily_basic"):
            params = {"exchange": "SSE", "start_date": start, "end_date": end} if api == "trade_cal" else {
                "ts_code": "601919.SH", "start_date": start, "end_date": end}
            if trading_date and api != "trade_cal":
                params = {"ts_code": "601919.SH", "trade_date": trading_date}
            try:
                rows = provider.query(api, params)
                if api == "trade_cal":
                    dates = [str(row["cal_date"]) for row in rows if str(row["is_open"]) == "1"]
                    trading_date = max(dates) if dates else None
                capabilities[api] = {"status": "available", "sample_rows": len(rows), "error_code": None}
            except MarketError as error:
                capabilities[api] = {"status": {
                    "TUSHARE_PERMISSION_DENIED": "permission_denied", "TUSHARE_RATE_LIMITED": "rate_limited"
                }.get(error.code, "failed"), "error_code": error.code, "message": str(error)}
        self.registry.set_setting("tushare_capabilities", {"last_tested_at": now(), "capabilities": capabilities})
        return self.get()
