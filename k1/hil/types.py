"""HIL request/response/envelope dataclasses (E1.M1.3).

All dataclasses are frozen + slotted for safety and memory.
Wire envelopes (`HILEnvelope`, `HILResponseEnvelope`) are the single
shape that flows on the bus; per-kind payload dicts are nested under
`payload`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Discriminator + outcome enums
# ---------------------------------------------------------------------------


class HILKind(str, Enum):
    """Discriminator for request kind. Value matches wire string."""

    CLARIFICATION = "clarification"
    APPROVAL = "approval"
    NEEDS_HUMAN = "needs_human"
    OVERRIDE = "override"
    CAPABILITY_GATE = "capability_gate"


class GateOutcome(str, Enum):
    """Outcome of `gate_capability` decision."""

    ALLOW = "allow"  # safety policy short-circuit, no user prompt
    DENY = "deny"  # reserved for future hard-blocks (not used today)
    ASK_APPROVED = "ask_approved"  # asked user, user approved
    ASK_REJECTED = "ask_rejected"  # asked user, user rejected
    TIMEOUT = "timeout"  # asked user, no response in budget


# ---------------------------------------------------------------------------
# CapabilityContractView -- minimal read-only view (no fabric import cycle)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CapabilityContractView:
    """Subset of CapabilityContract that the HIL gate needs.

    Built by `view_from_capability_contract` in E2 (lives in
    `k1.hil.types` to avoid forcing fabric -> hil cycle).
    """

    name: str
    safety_band_min: str  # "GREEN" | "AMBER" | "RED" | "CRISIS"
    requires_human_confirmation: bool | None  # None = infer from band + side_effects
    side_effects: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""


def view_from_capability_contract(contract: Any) -> CapabilityContractView:
    """Adapter: any object exposing the four fields -> CapabilityContractView.

    Duck-typed to avoid importing `k1.fabric.types.CapabilityContract`
    (E3 calls this from inside fabric so the import direction is
    fabric -> hil; the reverse import path would create a cycle).
    """

    return CapabilityContractView(
        name=getattr(contract, "name", ""),
        safety_band_min=getattr(contract, "safety_band_min", "GREEN"),
        requires_human_confirmation=getattr(contract, "requires_human_confirmation", None),
        side_effects=list(getattr(contract, "side_effects", []) or []),
        description=getattr(contract, "description", ""),
    )


# ---------------------------------------------------------------------------
# Per-kind requests
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    """Planner SKETCH ambiguity resolution."""

    caller_key: str
    trace_id: str
    question_context: dict[str, Any] = field(default_factory=dict)
    synthesize_with_llm: bool = True
    pre_formed_question: str | None = None
    timeout_ms: int = 60_000


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Planner VALIDATE high-impact plan approval."""

    caller_key: str
    trace_id: str
    summary: str
    options: list[dict[str, Any]] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    safety_assessment: str = ""
    estimated_duration_ms: int = 0
    timeout_ms: int = 120_000


@dataclass(frozen=True, slots=True)
class NeedsHumanRequest:
    """Concierge Back -> FSM clarification/approval/selection."""

    caller_key: str
    task_id: str
    trace_id: str
    hil_type: str  # Literal["clarification", "approval", "selection"]
    question: str
    options: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    safety_band: str = "GREEN"
    react_history: list[dict[str, Any]] = field(default_factory=list)
    timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class OverrideRequest:
    """Orchestrator ConstraintResolver fallback."""

    caller_key: str
    request_id: str
    trace_id: str
    plan_id: str
    unresolved_capabilities: list[str] = field(default_factory=list)
    proposed_alternatives: list[dict[str, Any]] = field(default_factory=list)
    timeout_ms: int = 60_000


@dataclass(frozen=True, slots=True)
class CapabilityGateRequest:
    """Fabric pre-execution gate."""

    caller_key: str
    trace_id: str
    capability_name: str
    contract: CapabilityContractView
    params: dict[str, Any] = field(default_factory=dict)
    params_summary: str = ""
    timeout_ms: int = 120_000


# ---------------------------------------------------------------------------
# Per-kind responses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClarificationResponse:
    hil_request_id: str
    answer: str | None
    timed_out: bool = False
    round_budget_exhausted: bool = False


@dataclass(frozen=True, slots=True)
class ApprovalResponse:
    hil_request_id: str
    decision: str  # Literal["approve", "modify", "reject"]
    modifications: dict[str, Any] | None = None
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class NeedsHumanResponse:
    hil_request_id: str
    decision: str
    resolution: dict[str, Any] = field(default_factory=dict)
    raw_user_text: str | None = None
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class OverrideResponse:
    hil_request_id: str
    choice: str  # Literal["override", "fallback", "abort"]
    selected_alternative: dict[str, Any] | None = None
    fallback_action: str | None = None
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class GateDecision:
    outcome: GateOutcome
    hil_request_id: str | None
    reason: str
    user_approved: bool | None = None
    audit_only: bool = False


# ---------------------------------------------------------------------------
# Wire envelopes (single shape on bus)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HILEnvelope:
    """Outbound envelope on TOPIC_HIL_REQUEST."""

    hil_request_id: str
    kind: HILKind
    caller_key: str
    trace_id: str
    created_at_ms: int
    timeout_ms: int
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hil_request_id": self.hil_request_id,
            "kind": self.kind.value,
            "caller_key": self.caller_key,
            "trace_id": self.trace_id,
            "created_at_ms": self.created_at_ms,
            "timeout_ms": self.timeout_ms,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HILEnvelope:
        return cls(
            hil_request_id=str(d["hil_request_id"]),
            kind=HILKind(d["kind"]),
            caller_key=str(d["caller_key"]),
            trace_id=str(d["trace_id"]),
            created_at_ms=int(d["created_at_ms"]),
            timeout_ms=int(d["timeout_ms"]),
            payload=dict(d.get("payload", {})),
        )


@dataclass(frozen=True, slots=True)
class HILPresentedEnvelope:
    """GAP-HIL-009: presentation acknowledgement on TOPIC_HIL_PRESENTED.

    Published by the Front actor (or any HIL presenter) once an answerable
    prompt has been rendered to a user surface. The HumanInTheLoopService
    uses this signal to arm the per-kind human-response timer *after*
    presentation rather than at request publish.

    Fields are intentionally minimal -- this is a lifecycle marker, not
    a content payload.
    """

    hil_request_id: str
    task_id: str
    kind: HILKind
    presented_at_ms: int
    presentation_channel: str  # "front_chat" | "widget" | "voice" | ...
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hil_request_id": self.hil_request_id,
            "task_id": self.task_id,
            "kind": self.kind.value,
            "presented_at_ms": self.presented_at_ms,
            "presentation_channel": self.presentation_channel,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HILPresentedEnvelope:
        return cls(
            hil_request_id=str(d["hil_request_id"]),
            task_id=str(d.get("task_id", "")),
            kind=HILKind(d["kind"]),
            presented_at_ms=int(d.get("presented_at_ms", 0)),
            presentation_channel=str(d.get("presentation_channel", "")),
            trace_id=str(d.get("trace_id", "")),
        )


@dataclass(frozen=True, slots=True)
class HILResponseEnvelope:
    """Inbound envelope on TOPIC_HIL_RESPONSE."""

    hil_request_id: str
    kind: HILKind
    responded_at_ms: int
    payload: dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "hil_request_id": self.hil_request_id,
            "kind": self.kind.value,
            "responded_at_ms": self.responded_at_ms,
            "payload": dict(self.payload),
            "timed_out": bool(self.timed_out),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HILResponseEnvelope:
        return cls(
            hil_request_id=str(d["hil_request_id"]),
            kind=HILKind(d["kind"]),
            responded_at_ms=int(d["responded_at_ms"]),
            payload=dict(d.get("payload", {})),
            timed_out=bool(d.get("timed_out", False)),
        )


# ---------------------------------------------------------------------------
# Ledger event types (kernel-level, not concierge-coupled)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HILRequestedEvent:
    hil_request_id: str
    kind: str
    caller_key: str
    trace_id: str
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HILResolvedEvent:
    hil_request_id: str
    kind: str
    decision_summary: str
    timestamp_ms: int
    duration_ms: int
    # M13.E2.I3 -- attribution of the resolver (user_id / "system:timeout" /
    # "system:cancel"). Empty string preserves wire compatibility with
    # pre-M13 events.
    resolver_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HILTimedOutEvent:
    hil_request_id: str
    kind: str
    caller_key: str
    timestamp_ms: int
    timeout_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HILBlockedEvent:
    hil_request_id: str
    kind: str
    caller_key: str
    reason: str
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
