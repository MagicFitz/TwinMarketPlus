"""Read-only Agent snapshot queries compatible with the Studio resource views."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.settings import Settings

from .read_only import ReadOnlyStore


class AgentService:
    """Query template and run-specific investor profiles without database writes."""

    def __init__(self, settings: Settings, store: ReadOnlyStore | None = None):
        self.settings = settings
        self.store = store or ReadOnlyStore(settings)
        self.data_dir = Path(settings.data_dir).resolve()

    def get_db(self, run_id: str, output_dir: Path | str | None = None) -> Path | None:
        """Return the template DB or the first user DB in a safely resolved run folder."""
        if run_id == "template":
            return self.store.local(self.data_dir / "sys_1000.db")
        folder = self.store.resolve_run_folder(run_id, output_dir)
        return self.store.database(folder, "user*.db")

    def members(
        self,
        run_id: str,
        q: str = "",
        page: int = 1,
        output_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        db = self.get_db(run_id, output_dir)
        search = q[:100]
        current_page = min(1_000_000, max(1, int(page)))
        where = (
            "created_at = (SELECT max(created_at) FROM Profiles) "
            "AND (user_id LIKE ? OR user_type LIKE ? OR location LIKE ?)"
        )
        params = (f"%{search}%",) * 3
        total = self.store.scalar(db, f"SELECT count(*) FROM Profiles WHERE {where}", params)
        items = self.store.rows(
            db,
            f"""SELECT user_id, user_type, location,
            bh_disposition_effect_category disposition, bh_lottery_preference_category lottery,
            current_cash, total_value, return_rate, created_at
            FROM Profiles WHERE {where} ORDER BY user_id LIMIT 20 OFFSET ?""",
            (*params, (current_page - 1) * 20),
        )
        return {"items": items, "total": total, "page": current_page}

    def member_detail(
        self,
        run_id: str,
        user_id: str,
        output_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        db = self.get_db(run_id, output_dir)
        result = self.store.rows(
            db,
            """SELECT user_id, user_type, location, gender,
            bh_disposition_effect_category disposition, bh_lottery_preference_category lottery,
            bh_underdiversification_category diversification,
            current_cash, total_value, return_rate, cur_positions, created_at
            FROM Profiles WHERE user_id = ? ORDER BY created_at DESC LIMIT 1""",
            (user_id,),
        )
        if not result:
            raise KeyError("Unknown member")
        item = result[0]
        try:
            item["positions"] = json.loads(item.pop("cur_positions") or "{}")
        except ValueError:
            item["positions"] = {}
        strategies = self.store.rows(
            db,
            "SELECT strategy FROM Strategy WHERE CAST(user_id AS TEXT) = ? LIMIT 1",
            (user_id,),
        )
        item["strategy"] = strategies[0]["strategy"] if strategies else None
        return item


def get_db(settings: Settings, run_id: str, output_dir: Path | str | None = None) -> Path | None:
    return AgentService(settings).get_db(run_id, output_dir)


def members(
    settings: Settings,
    run_id: str,
    q: str = "",
    page: int = 1,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Return the legacy ``GET /api/runs/{run_id}/agents`` response DTO."""
    return AgentService(settings).members(run_id, q, page, output_dir)


def member_detail(
    settings: Settings,
    run_id: str,
    user_id: str,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Return the legacy Agent detail DTO, including decoded positions and strategy."""
    return AgentService(settings).member_detail(run_id, user_id, output_dir)


list_members = members
agent_detail = member_detail
