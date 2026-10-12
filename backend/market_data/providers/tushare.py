"""Fixed-endpoint Tushare HTTP adapter; supplier errors never leave this layer."""
from __future__ import annotations

import random
import time
from typing import Callable

import requests

from backend.market_data.errors import MarketError

API_URL = "https://api.tushare.pro"
FIELDS = {
    "trade_cal": "cal_date,is_open,pretrade_date",
    "daily": "ts_code,trade_date,close,pre_close,pct_chg,vol,amount",
    "daily_basic": "ts_code,trade_date,pe_ttm,pb,ps_ttm,dv_ttm",
}


class TushareProvider:
    def __init__(self, token: str, *, post=None, sleep=None, interval: float = .65,
                 check: Callable = lambda: None, on_retry: Callable = lambda code, delay: None):
        if not token:
            raise MarketError("TUSHARE_AUTH_FAILED", "请先配置 Tushare Token")
        self._token = token
        self._post = post or requests.post
        self._sleep = sleep or time.sleep
        self.interval, self.check, self.on_retry = interval, check, on_retry
        self._last_call = 0.0

    def _pause(self, duration):
        # Short slices make cancellation responsive during backoff.
        while duration > 0:
            self.check()
            step = min(duration, .5)
            self._sleep(step)
            duration -= step

    def query(self, api_name: str, params: dict) -> list[dict]:
        fields = FIELDS[api_name]
        for attempt in range(4):
            self.check()
            self._pause(max(0, self.interval - (time.monotonic() - self._last_call)))
            self._last_call = time.monotonic()
            try:
                response = self._post(API_URL, json={"api_name": api_name, "token": self._token,
                    "params": params, "fields": fields}, timeout=(10, 30), allow_redirects=False)
                if response.status_code == 429 or response.status_code >= 500:
                    raise MarketError("TUSHARE_RATE_LIMITED" if response.status_code == 429 else
                                      "TUSHARE_UNAVAILABLE", "Tushare 暂不可用，请稍后重试", 503)
                if response.status_code != 200:
                    raise MarketError("TUSHARE_UNAVAILABLE", "Tushare 返回异常 HTTP 状态", 503)
                payload = response.json()
                if not isinstance(payload, dict) or "code" not in payload:
                    raise MarketError("TUSHARE_INVALID_RESPONSE", "Tushare 返回格式不完整", 502)
                if payload["code"] != 0:
                    # Only use the message for classification, never return or log it.
                    message = str(payload.get("msg", "")).lower()
                    if "token" in message or "令牌" in message:
                        raise MarketError("TUSHARE_AUTH_FAILED", "Tushare Token 无效", 401)
                    if any(word in message for word in ("频率", "每分钟", "每小时", "每天", "rate limit")):
                        raise MarketError("TUSHARE_RATE_LIMITED", "Tushare 调用频率受限", 429)
                    if payload["code"] == 2002 or "权限" in message or "积分" in message:
                        raise MarketError("TUSHARE_PERMISSION_DENIED", "账户没有此接口权限", 403)
                    raise MarketError("TUSHARE_REQUEST_FAILED", "Tushare 拒绝了数据请求", 502)
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise MarketError("TUSHARE_INVALID_RESPONSE", "Tushare 缺少数据容器", 502)
                names, items = data.get("fields"), data.get("items")
                if (not isinstance(names, list) or not isinstance(items, list) or
                    not all(isinstance(name, str) for name in names) or len(names) != len(set(names)) or
                    not set(fields.split(",")).issubset(names) or
                    any(not isinstance(row, list) or len(row) != len(names) for row in items)):
                    raise MarketError("TUSHARE_INVALID_RESPONSE", "Tushare 字段或行格式不完整", 502)
                return [{key: value for key, value in zip(names, row) if key in fields.split(",")} for row in items]
            except (requests.RequestException, ValueError) as error:
                if isinstance(error, MarketError):
                    safe_error = error
                elif isinstance(error, requests.RequestException):
                    safe_error = MarketError("TUSHARE_UNAVAILABLE", "Tushare 网络连接失败", 503)
                else:
                    safe_error = MarketError("TUSHARE_INVALID_RESPONSE", "Tushare 返回无效 JSON", 502)
                if safe_error.code not in {"TUSHARE_UNAVAILABLE", "TUSHARE_RATE_LIMITED"} or attempt == 3:
                    raise safe_error from None
                delay = min(30, 2 ** (attempt + 1) + random.random())
                self.on_retry(safe_error.code, delay)
                self._pause(delay)
        raise AssertionError("unreachable")

    def fetch(self, api_name: str, params: dict, *, record=lambda *args: None) -> list[dict]:
        rows, seen = [], set()
        offset = 0
        while True:
            page_params = {**params, "limit": 6000, "offset": offset}
            page = self.query(api_name, page_params)
            record(api_name, page_params, page)
            # Refuse silent truncation / a supplier ignoring offset.
            for row in page:
                key = (row.get("ts_code"), row.get("trade_date", row.get("cal_date")))
                if key in seen:
                    raise MarketError("DATA_DUPLICATE_ROWS", "接口返回重复数据，拒绝发布快照")
                seen.add(key)
            rows.extend(page)
            if len(page) < 6000:
                return rows
            offset += len(page)
