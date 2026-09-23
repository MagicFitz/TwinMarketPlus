"""Immutable persisted RuntimeEvent."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .schemas import EventType, Scope, redact


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_id: int
    run_id: str
    event: EventType
    scope: Scope
    stage: str
    simulation_date: str | None = None
    substage: str | None = None
    agent_id: str | None = None
    worker_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    attempt: int = 1
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error_code: str | None = None
    error_summary: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid4().hex)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event"] = self.event.value
        result["scope"] = self.scope.value
        result["input_summary"] = redact(result["input_summary"])
        result["output_summary"] = redact(result["output_summary"])
        result["error_summary"] = redact(result["error_summary"])
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeEvent":
        return cls(**{**value, "event": EventType(value["event"]), "scope": Scope(value["scope"])})
