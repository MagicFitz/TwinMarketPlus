#!/usr/bin/env python3
"""Manually synchronize a local Tushare snapshot; activation is explicit."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.market_data.errors import MarketError
from backend.services.market_sync import MarketSyncService
from backend.settings import get_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", help="Explicit backfill date; omitted means incremental with three-day revision overlap")
    parser.add_argument("--end-date")
    parser.add_argument("--allow-missing-news", action="store_true", required=True)
    parser.add_argument("--without-valuations", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    service = MarketSyncService(get_settings())
    try:
        job = service.create({"mode": "backfill" if args.start_date else "incremental", "start_date": args.start_date,
            "end_date": args.end_date, "allow_missing_news": args.allow_missing_news,
            "datasets": ["trade_cal", "daily"] + ([] if args.without_valuations else ["daily_basic"])}, launch=False)
        result = service.execute(job["job_id"])
        if result["status"] == "completed" and args.activate:
            service.activate(result["snapshot_id"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 1
    except MarketError as error:
        print(json.dumps({"code": error.code, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
