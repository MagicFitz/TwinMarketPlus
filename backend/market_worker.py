"""Detached market synchronization, independent of simulation workers."""
import argparse

from backend.services.market_sync import MarketSyncService
from backend.settings import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    result = MarketSyncService(get_settings()).execute(args.job_id)
    return 0 if result["status"] in {"completed", "cancelled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
