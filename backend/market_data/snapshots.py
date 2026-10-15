"""Fingerprinted local snapshots and run-time integrity checks."""
import hashlib
import json
import re
from pathlib import Path

from .errors import MarketError
from .registry import MarketRegistry

COMPATIBILITY_FILES = ("stock_data.csv", "trading_days.csv", "sorted_impact_news.pkl", "stock_profile.csv", "market_assets.yaml")


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def snapshot_path(settings, snapshot_id):
    if not isinstance(snapshot_id, str) or not re.fullmatch(r"market-[a-z0-9-]{1,80}", snapshot_id):
        raise MarketError("SNAPSHOT_NOT_FOUND", "市场快照标识无效", 404)
    return settings.data_path("market_snapshots", snapshot_id)


def resolve_snapshot(settings, snapshot_id, *, start_date=None, end_date=None, allow_missing_news=False):
    metadata = MarketRegistry(settings).snapshot(snapshot_id)
    path = snapshot_path(settings, snapshot_id)
    if metadata["status"] not in {"ready", "ready_with_warnings"}:
        raise MarketError("SNAPSHOT_NOT_READY", "快照尚未通过质量校验")
    if start_date and (start_date < metadata["earliest_run_date"] or end_date > metadata["effective_through"]):
        raise MarketError("SNAPSHOT_RANGE_UNCOVERED", "快照未覆盖所选模拟日期，请前往 Market 更新数据")
    if metadata["datasets"]["news"]["status"] == "missing" and not allow_missing_news:
        raise MarketError("NEWS_MISSING_NOT_ALLOWED", "此快照缺少新闻，请明确允许无新闻模式")
    try:
        disk_metadata = json.loads((path / "snapshot.json").read_text(encoding="utf-8"))
        if metadata != disk_metadata:
            raise MarketError("SNAPSHOT_INTEGRITY_FAILED", "快照元数据校验失败")
        for name, expected in metadata["files"].items():
            target = (path / name).resolve()
            if not target.is_relative_to(path) or fingerprint(target) != expected:
                raise MarketError("SNAPSHOT_INTEGRITY_FAILED", "快照文件指纹不匹配")
    except (OSError, ValueError) as error:
        if isinstance(error, MarketError):
            raise
        raise MarketError("SNAPSHOT_INTEGRITY_FAILED", "快照文件缺失或损坏") from None
    return metadata, path
