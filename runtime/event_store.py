"""Append-only jsonl store with a bounded hot buffer for SSE consumers."""
from __future__ import annotations

import json
import threading
from collections import deque
from pathlib import Path

from .event import RuntimeEvent


class EventStore:
    def __init__(self, path: Path, buffer_size: int = 2048):
        self.path = path
        self._lock = threading.Lock()
        self._buffer: deque[RuntimeEvent] = deque(maxlen=buffer_size)
        self._last_id = 0
        self._load_tail()

    def _load_tail(self) -> None:
        if not self.path.is_file():
            return
        try:
            with self.path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        event = RuntimeEvent.from_dict(json.loads(line))
                    except (ValueError, TypeError, json.JSONDecodeError):
                        continue  # tolerate a partial final write after a crash
                    self._buffer.append(event)
                    self._last_id = max(self._last_id, event.event_id)
        except OSError:
            return

    def append(self, event: RuntimeEvent) -> RuntimeEvent:
        with self._lock:
            if event.event_id <= 0:
                event = RuntimeEvent.from_dict({**event.as_dict(), "event_id": self._last_id + 1})
            if event.event_id <= self._last_id:
                raise ValueError("event_id must be strictly ordered within a run")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.as_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
            self._last_id = event.event_id
            self._buffer.append(event)
            return event

    def after(self, event_id: int = 0, limit: int = 1000) -> list[RuntimeEvent]:
        # Persistent scan is required when a reconnect gap predates the hot buffer.
        if event_id < self._last_id - len(self._buffer):
            found: list[RuntimeEvent] = []
            if self.path.is_file():
                with self.path.open(encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            item = RuntimeEvent.from_dict(json.loads(line))
                        except (ValueError, TypeError, json.JSONDecodeError):
                            continue
                        if item.event_id > event_id:
                            found.append(item)
                            if len(found) >= limit:
                                break
            return found
        return [item for item in self._buffer if item.event_id > event_id][:limit]

    @property
    def last_id(self) -> int:
        return self._last_id
