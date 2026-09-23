"""Best-effort instrumentation. Observation failures never abort simulation work."""
from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from .event import RuntimeEvent
from .event_store import EventStore
from .schemas import EventType, Scope


class RuntimeObserver:
    def __init__(self, run_id: str, store: EventStore, on_degraded: Callable[[str], None] | None = None):
        self.run_id, self.store, self.on_degraded = run_id, store, on_degraded
        self._started: dict[tuple[str, str, str | None, str | None, int], tuple[str, float]] = {}

    def emit(self, event: EventType, scope: Scope, stage: str, **fields) -> RuntimeEvent | None:
        try:
            return self.store.append(RuntimeEvent(event_id=0, run_id=self.run_id, event=event, scope=scope, stage=stage, **fields))
        except Exception as error:  # intentionally isolated from simulation result
            if self.on_degraded:
                self.on_degraded(f"RuntimeEvent write failed: {type(error).__name__}")
            return None

    def _key(self, scope: Scope, stage: str, fields: dict) -> tuple[str, str, str | None, str | None, int]:
        return scope.value, stage, fields.get("agent_id"), fields.get("worker_id"), int(fields.get("attempt", 1))
    def started(self, scope: Scope, stage: str, **fields):
        started_at = datetime.now(timezone.utc).isoformat()
        self._started[self._key(scope, stage, fields)] = (started_at, perf_counter())
        return self.emit(EventType.STARTED, scope, stage, started_at=started_at, **fields)
    def completed(self, scope: Scope, stage: str, **fields):
        started_at, started_clock = self._started.pop(self._key(scope, stage, fields), (None, None))
        return self.emit(EventType.COMPLETED, scope, stage, started_at=started_at, ended_at=datetime.now(timezone.utc).isoformat(), duration_ms=(round((perf_counter() - started_clock) * 1000) if started_clock is not None else None), **fields)
    def skipped(self, scope: Scope, stage: str, **fields): return self.emit(EventType.SKIPPED, scope, stage, **fields)
    def failed(self, scope: Scope, stage: str, **fields): return self.emit(EventType.FAILED, scope, stage, **fields)
    def retrying(self, scope: Scope, stage: str, **fields): return self.emit(EventType.RETRYING, scope, stage, **fields)
