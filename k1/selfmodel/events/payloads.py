"""Typed payloads for ``k1.selfmodel`` bus events (M2.E3.I1).

All payloads are frozen dataclasses with a ``to_json()`` method that
returns a plain ``dict[str, object]`` suitable for the bus envelope
``body`` field.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from k1.selfmodel.contracts.policy import (
    PolicyDecision,
    PolicyVerdict,
    ReasonCode,
    RiskClass,
)

__all__ = [
    "PolicyVerdictEvent",
    "PolicyEscalationEvent",
    "PolicyDeferredEvent",
]


@dataclass(frozen=True)
class PolicyVerdictEvent:
    """Emitted on every gate decision (ALLOW + DENY + escalations)."""

    actor_id: str
    tool_name: str
    risk_class: RiskClass
    decision: PolicyDecision
    reason: ReasonCode
    requires_tier: int = 0
    audit_required: bool = False
    pending_id: str = ""
    trace_id: str = ""
    detail: str = ""
    caution: bool = False  # M14.E1.I6 — true on ALLOW_WITH_CAUTION

    @classmethod
    def from_verdict(
        cls,
        *,
        actor_id: str,
        tool_name: str,
        risk_class: RiskClass,
        verdict: PolicyVerdict,
        trace_id: str = "",
    ) -> "PolicyVerdictEvent":
        return cls(
            actor_id=actor_id,
            tool_name=tool_name,
            risk_class=risk_class,
            decision=verdict.decision,
            reason=verdict.reason,
            requires_tier=verdict.requires_tier,
            audit_required=verdict.audit_required,
            pending_id=verdict.pending_id,
            trace_id=trace_id,
            detail=verdict.detail,
            caution=(verdict.decision == PolicyDecision.ALLOW_WITH_CAUTION),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "tool_name": self.tool_name,
            "risk_class": self.risk_class.value,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "requires_tier": self.requires_tier,
            "audit_required": self.audit_required,
            "pending_id": self.pending_id,
            "trace_id": self.trace_id,
            "detail": self.detail,
            "caution": self.caution,
        }


@dataclass(frozen=True)
class PolicyEscalationEvent:
    """Emitted when the gate routes a request to HIL approval."""

    actor_id: str
    tool_name: str
    risk_class: RiskClass
    hil_request_id: str
    summary: str = ""
    side_effects: tuple[str, ...] = field(default_factory=tuple)
    trace_id: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "tool_name": self.tool_name,
            "risk_class": self.risk_class.value,
            "hil_request_id": self.hil_request_id,
            "summary": self.summary,
            "side_effects": list(self.side_effects),
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True)
class PolicyDeferredEvent:
    """Emitted when ``DEFER_OFFLINE`` queues a tool call for later."""

    actor_id: str
    tool_name: str
    risk_class: RiskClass
    queued_id: str = ""
    reason: ReasonCode = ReasonCode.OFFLINE_ONLY
    trace_id: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "tool_name": self.tool_name,
            "risk_class": self.risk_class.value,
            "queued_id": self.queued_id,
            "reason": self.reason.value,
            "trace_id": self.trace_id,
        }
