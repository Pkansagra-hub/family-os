"""Shared helpers for structured error envelopes across kernel ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

KERNEL_COMPONENT_GATE = "kernel.gate"
KERNEL_COMPONENT_POLICY = "kernel.policy"
KERNEL_COMPONENT_QOS = "kernel.qos"
KERNEL_COMPONENT_SSE = "kernel.sse"
KERNEL_COMPONENT_QUERY = "kernel.query"
KERNEL_COMPONENT_OBSERVE = "kernel.observe"
KERNEL_COMPONENT_DRIVER = "kernel.driver"


@dataclass(slots=True)
class ErrorEnvelope:
    """Structured error payload serialized by kernel ports."""

    code: str
    component: str
    trace_id: str
    reason: str | None = None
    hint: str | None = None
    budgets: Mapping[str, int] | None = None
    details: Mapping[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "component": self.component,
            "trace_id": self.trace_id,
        }
        if self.reason:
            error["reason"] = self.reason
        if self.hint:
            error["hint"] = self.hint
        if self.budgets:
            error["budgets"] = {
                str(key): max(0, int(value)) for key, value in self.budgets.items()
            }
        if self.details:
            error["details"] = dict(self.details)
        return {"error": error}
