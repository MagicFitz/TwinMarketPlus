"""Read-only market-data queries for template and run databases."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.settings import Settings

from .read_only import ReadOnlyStore


class MarketService:
    """Return the existing Market view DTO without mutating SQLite state."""

    def __init__(self, settings: Settings, store: ReadOnlyStore | None = None):
        self.settings = settings
        self.store = store or ReadOnlyStore(settings)
        self.data_dir = Path(settings.data_dir).resolve()

    def get_db(self, run_id: str, output_dir: Path | str | None = None) -> Path | None:
        if run_id == "template":
            return self.store.local(self.data_dir / "sys_1000.db")
        folder = self.store.resolve_run_folder(run_id, output_dir)
        return self.store.database(folder, "user*.db")

    def market(
        self,
        run_id: str,
        asset: str | None = None,
        output_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        db = self.get_db(run_id, output_dir)
        assets = self.store.rows(
            db,
            "SELECT stock_id, name, industry, weight, description FROM StockProfile ORDER BY weight DESC",
        )
        selected = asset or (assets[0]["stock_id"] if assets else "")
        prices = self.store.rows(
            db,
            """SELECT date, close_price, pct_chg, vol FROM StockData
            WHERE stock_id = ? ORDER BY date DESC LIMIT 180""",
            (selected,),
        )[::-1]
        return {
            "assets": assets,
            "selected": selected,
            "prices": prices,
            "source": "初始化模板历史行情" if run_id == "template" else "实验数据库（含初始化历史）",
        }


def market(
    settings: Settings,
    run_id: str,
    asset: str | None = None,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Return the legacy ``GET /api/runs/{run_id}/market`` response structure."""
    return MarketService(settings).market(run_id, asset, output_dir)


get_market = market
