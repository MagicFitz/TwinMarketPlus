"""Deterministic reducer from persisted events to the live UI snapshot."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .event import RuntimeEvent
from .schemas import AGENT_STAGES, DAY_STAGES, EventType


EVENT_STATUS = {
    EventType.STARTED: "running", EventType.COMPLETED: "completed", EventType.SKIPPED: "skipped",
    EventType.FAILED: "failed", EventType.RETRYING: "retrying",
}


class RuntimeSnapshotReducer:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.last_event_id = 0
        self.run: dict[str, Any] = {"status": "pending", "health": "healthy"}
        self.day: dict[str, Any] = {"date": None, "stages": {stage: {"status": "pending"} for stage in DAY_STAGES}}
        self.agents: dict[str, dict[str, Any]] = {}
        self.workers: dict[str, dict[str, Any]] = {}
        self.diagnostics: list[dict[str, Any]] = []
        self.today_summary = Counter({"buy": 0, "sell": 0, "hold": 0, "orders": 0, "posts": 0, "interactions": 0, "failures": 0})

    def apply(self, event: RuntimeEvent) -> None:
        if event.event_id <= self.last_event_id:
            return
        self.last_event_id = event.event_id
        status = EVENT_STATUS[event.event]
        base = {"status": status, "substage": event.substage, "duration_ms": event.duration_ms,
                "attempt": event.attempt, "message": event.message, "input_summary": event.input_summary,
                "output_summary": event.output_summary, "updated_at": event.ended_at or event.started_at}
        if event.scope.value == "run":
            self.run.update(base)
            if status == "failed": self.run["health"] = "degraded"
        elif event.scope.value == "day":
            if event.stage == "prepare" and event.event == EventType.STARTED and event.simulation_date != self.day.get("date"):
                self.today_summary = Counter({"buy": 0, "sell": 0, "hold": 0, "orders": 0, "posts": 0, "interactions": 0, "failures": 0})
            if event.simulation_date: self.day["date"] = event.simulation_date
            self.day["stages"].setdefault(event.stage, {}).update(base)
        elif event.scope.value == "agent" and event.agent_id:
            agent = self.agents.setdefault(event.agent_id, {"agent_id": event.agent_id, "stages": {stage: {"status": "pending"} for stage in AGENT_STAGES}})
            agent["stages"].setdefault(event.stage, {}).update(base)
            agent.update({"worker_id": event.worker_id, "last_stage": event.stage, "updated_at": base["updated_at"]})
            if event.worker_id:
                self.workers[event.worker_id] = {"worker_id": event.worker_id, "agent_id": event.agent_id, "stage": event.stage, **base}
            if event.stage == "action" and event.event == EventType.COMPLETED:
                for key, name in (("buy", "buy"), ("sell", "sell"), ("hold", "hold"), ("orders", "orders")):
                    self.today_summary[name] += int(event.output_summary.get(key, 0) or 0)
            if event.event == EventType.FAILED:
                self.today_summary["failures"] += 1
        elif event.scope.value == "social" and event.event == EventType.COMPLETED:
            self.today_summary["posts"] += int(event.output_summary.get("posts", 0) or 0)
            self.today_summary["interactions"] += int(event.output_summary.get("interactions", 0) or 0)
        if event.event in (EventType.FAILED, EventType.RETRYING) or (event.duration_ms or 0) > 30_000:
            self.diagnostics.append(event.as_dict())
            self.diagnostics = self.diagnostics[-100:]

    def apply_all(self, events: Iterable[RuntimeEvent]) -> None:
        for event in events: self.apply(event)

    def as_dict(self) -> dict[str, Any]:
        counts = Counter(agent.get("stages", {}).get("commit", {}).get("status", "pending") for agent in self.agents.values())
        return {"run_id": self.run_id, "last_event_id": self.last_event_id, "run": self.run, "day": self.day,
                "agents": list(self.agents.values()), "workers": list(self.workers.values()),
                "agent_counts": {key: counts.get(key, 0) for key in ("completed", "running", "pending", "retrying", "failed", "skipped")},
                "today_summary": dict(self.today_summary), "diagnostics": self.diagnostics}
