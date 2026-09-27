"""Deprecated Studio launcher kept for local command compatibility.

The implementation moved to :mod:`backend.app.main`. Studio is now a
frontend-only package; the standalone backend serves every API route.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the standalone TwinMarket backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        app_dir=str(Path(__file__).resolve().parents[1]),
    )


if __name__ == "__main__":
    main()
