"""Typed control and loop events for Concierge ReAct runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BackControlEvent:
    """Control-plane event routed from the FSM into a running Back loop."""

    event_type: str
    task_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at_ns: int = field(default_factory=time.monotonic_ns)
    received_at_iteration: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "task_id": self.task_id,
            "payload": dict(self.payload),
            "created_at_ns": self.created_at_ns,
            "received_at_iteration": self.received_at_iteration,
        }


@dataclass(frozen=True, slots=True)
class ReactLoopEvent:
    """Structured marker for notable ReAct loop control decisions."""

    event_type: str
    actor: str
    scenario: str = ""
    iteration: int = -1
    trace_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "actor": self.actor,
            "scenario": self.scenario,
            "iteration": self.iteration,
            "trace_id": self.trace_id,
            "payload": dict(self.payload),
            "created_at_ms": self.created_at_ms,
        }
