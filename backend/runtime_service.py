"""Framework-neutral queries over persisted RuntimeEvent streams."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime import EventStore, RuntimeSnapshotReducer


def store_for(run: dict[str, Any]) -> EventStore:
    return EventStore(Path(run["output_dir"]) / "events.jsonl")


def runtime_snapshot(run: dict[str, Any]) -> dict[str, Any]:
    store = store_for(run)
    reducer = RuntimeSnapshotReducer(run["run_id"])
    reducer.apply_all(store.after(0, 1_000_000))
    result = reducer.as_dict()
    result["lifecycle"] = run["status"]
    result["health"] = run["health"]
    return result
