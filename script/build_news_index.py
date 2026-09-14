#!/usr/bin/env python3
"""Build TwinMarket's FAISS news index from the bundled daily news pickle."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from util.InformationDB import InformationDB


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="data/sorted_impact_news.pkl",
        help="Daily news pickle containing cal_date and news columns",
    )
    parser.add_argument(
        "--output",
        default="data/InformationDB_news_2023",
        help="Directory for faiss_index.pkl and metadata.pkl",
    )
    parser.add_argument(
        "--config", default="config/embedding.yaml", help="Embedding YAML config"
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--force", action="store_true", help="Replace an existing index")
    return parser.parse_args()


def main():
    args = parse_args()
    database = InformationDB(
        config_path=args.config,
        database_dir=args.output,
    )
    database.build_from_daily_news_pickle(
        pickle_path=args.source,
        batch_size=args.batch_size,
        force=args.force,
    )


if __name__ == "__main__":
    main()
