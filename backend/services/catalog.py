"""Read-only catalog data for the Agent, Market, and Setting views."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.settings import Settings

from .read_only import ReadOnlyStore


class CatalogService:
    """Build the existing catalog DTO from configured local data sources."""

    def __init__(self, settings: Settings, store: ReadOnlyStore | None = None):
        self.settings = settings
        self.store = store or ReadOnlyStore(settings)
        self.project_root = Path(settings.project_root).resolve()
        self.data_dir = Path(settings.data_dir).resolve()

    def catalog(self) -> dict[str, Any]:
        db = self.store.local(self.data_dir / "sys_1000.db")
        users = self.store.scalar(db, "SELECT count(DISTINCT user_id) FROM Profiles")
        distributions = self.store.rows(
            db,
            """SELECT user_type name, count(*) value FROM Profiles
            WHERE created_at = (SELECT max(created_at) FROM Profiles) GROUP BY user_type""",
        )
        market_range = self.store.rows(
            db,
            "SELECT min(date) start, max(date) end, count(*) records FROM StockData",
        )[0]

        inventory: list[dict[str, Any]] = []
        for relative, name in (
            ("stock_data.csv", "行业指数行情"),
            ("trading_days.csv", "交易日历"),
            ("sorted_impact_news.pkl", "每日新闻"),
            ("InformationDB_news_2023/faiss_index.pkl", "新闻向量索引"),
        ):
            path = self.store.local(self.data_dir / relative)
            logical_path = f"data/{relative}"
            inventory.append(
                {
                    "name": name,
                    "path": logical_path,
                    "available": path.is_file(),
                    "bytes": path.stat().st_size if path.is_file() else None,
                }
            )

        connections: list[dict[str, Any]] = []
        for filename, kind, name in (
            ("api.yaml", "language", "语言模型"),
            ("embedding.yaml", "embedding", "向量模型"),
        ):
            path = self.store.local(self.project_root / "config" / filename)
            # Only the model label is public.  Credentials and other config
            # values never leave this service.
            model = None
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    match = re.match(r"^model_name:\s*([\w./-]+)\s*$", line)
                    if match:
                        model = match.group(1)
            connections.append(
                {
                    "kind": kind,
                    "name": name,
                    "model": model,
                    "configured": path.is_file(),
                    "tested": False,
                }
            )

        return {
            "group": {
                "id": "template",
                "name": "基础投资者群体",
                "users": users,
                "distributions": distributions,
                "source": "data/sys_1000.db",
                "status": "本地模板 · 未注册版本",
            },
            "market_range": market_range,
            "inventory": inventory,
            "connections": connections,
        }


def catalog(settings: Settings) -> dict[str, Any]:
    """Return the legacy ``GET /api/catalog`` response structure."""
    return CatalogService(settings).catalog()


get_catalog = catalog
