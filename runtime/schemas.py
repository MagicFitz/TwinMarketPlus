"""Runtime Observatory 枚举和脱敏规则；不依赖 Web 框架。"""
from __future__ import annotations

from enum import Enum
import re
from typing import Any


class EventType(str, Enum):
    STARTED = "stage_started"
    COMPLETED = "stage_completed"
    SKIPPED = "stage_skipped"
    FAILED = "stage_failed"
    RETRYING = "stage_retrying"


class Scope(str, Enum):
    RUN = "run"
    DAY = "day"
    AGENT = "agent"
    MARKET = "market"
    SOCIAL = "social"
    ARTIFACT = "artifact"
    SYSTEM = "system"


DAY_STAGES = ("prepare", "agents", "market", "social", "commit")
AGENT_STAGES = ("state", "perception", "interpretation", "decision", "action", "commit")
SENSITIVE_KEYS = frozenset(("api_key", "key", "token", "authorization", "password", "secret", "base_url", "endpoint", "prompt", "reasoning"))


def redact(value: Any, key: str = "") -> Any:
    """Keep bounded user-facing summaries, never credentials or raw prompts."""
    if any(word in key.lower() for word in SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items() if str(k).lower() not in SENSITIVE_KEYS}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value[:20]]
    if isinstance(value, str):
        return re.sub(r"https?://\S+", "[redacted endpoint]", value)[:500]
    return value
