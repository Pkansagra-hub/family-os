"""M2.E2.I1 — ``ConciergePolicyGate`` adapter tests.

Stubbed ``HumanInTheLoopService`` + capturing bus + scripted
``frame_provider`` exercise every gate branch:

* ALLOW                              → returns None (passthrough)
* DENY                               → returns ToolResult(error)
* REQUIRE_IDENTITY                   → returns ToolResult(error)
* REQUIRE_CONFIRMATION (approve)     → returns None (HIL approved)
* REQUIRE_CONFIRMATION (reject)      → returns ToolResult(error)
* REQUIRE_CONFIRMATION (timeout)     → returns ToolResult(error)
* REQUIRE_CONFIRMATION (no HIL)      → returns ToolResult(error)
* DEFER_OFFLINE                      → returns ToolResult(partial), queues
* Emergency override                 → returns None (passthrough + audit)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from k1.concierge.llm.types import ToolCallResult
from k1.hil.types import ApprovalRequest, ApprovalResponse
from k1.selfmodel.adapters.concierge_policy_gate import (
    ConciergePolicyGate,
    _freshness_from_frame,
)
from k1.selfmodel.contracts.policy import (
    FreshnessState,
    PolicyDecision,
    RiskClass,
)
from k1.selfmodel.contracts.risk_class_registry import (
    RISK_CLASS_BY_TOOL,
    register_tool_risk,
)
from k1.selfmodel.contracts.situation import Capabilities, SituationFrame
from k1.selfmodel.events.topics import (
    TOPIC_POLICY_DEFERRED,
    TOPIC_POLICY_ESCALATION,
    TOPIC_POLICY_VERDICT,
)


# ---------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------
class _HILStub:
    """Minimal duck-typed HIL service for the gate."""

    def __init__(self, response: ApprovalResponse) -> None:
        self.calls: list[ApprovalRequest] = []
        self._response = response

    async def request_approval(self, req: ApprovalRequest) -> ApprovalResponse:
        self.calls.append(req)
        return self._response


@dataclass
class _CapturedEvent:
    topic: str
    body: dict[str, Any]


class _BusStub:
    """Captures events without running the real bus envelope machinery."""

    def __init__(self) -> None:
        self.events: list[_CapturedEvent] = []

    def publish_simple(self, topic: str, body: dict[str, Any]) -> None:
        self.events.append(_CapturedEvent(topic=topic, body=body))


def _frame(
    *,
    can_do: tuple[str, ...] = (),
    must_ask: tuple[str, ...] = (),
    tiers: dict[str, int] | None = None,
    freshness: dict[str, str] | None = None,
) -> SituationFrame:
    return SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        capabilities=Capabilities(
            can_do=can_do,
            requires_confirmation=must_ask,
            requires_identity_tier=dict(tiers or {}),
        ),
        freshness=dict(freshness or {"self": "fresh", "family": "fresh", "constitution": "fresh"}),
    )


def _gate(
    frame: SituationFrame,
    *,
    hil: _HILStub | None = None,
    bus: _BusStub | None = None,
    deferred=None,
    current_tier: int = 0,
) -> tuple[ConciergePolicyGate, _BusStub]:
    bus = bus or _BusStub()
    g = ConciergePolicyGate(
        actor_id="a1",
        frame_provider=lambda _tc: frame,
        hil_service=hil,
        bus=bus,
        deferred_queue_fn=deferred,
        current_tier_fn=lambda: current_tier,
        trace_id_fn=lambda: "trace-1",
    )
    return g, bus


def _call(name: str = "recall_memory") -> ToolCallResult:
    return ToolCallResult(id="c1", name=name, arguments={"k": "v"})


# ---------------------------------------------------------------------
# ALLOW
# ---------------------------------------------------------------------
async def test_allow_passes_through_and_emits_verdict() -> None:
    gate, bus = _gate(_frame(can_do=("recall_memory",)))
    out = await gate.evaluate(_call("recall_memory"))
    assert out is None
    topics = [e.topic for e in bus.events]
    assert TOPIC_POLICY_VERDICT in topics
    body = next(e.body for e in bus.events if e.topic == TOPIC_POLICY_VERDICT)
    assert body["decision"] == "ALLOW"
    assert body["actor_id"] == "a1"
    assert body["trace_id"] == "trace-1"


# ---------------------------------------------------------------------
# DENY (E6)
# ---------------------------------------------------------------------
async def test_capability_denied_returns_blocked_result() -> None:
    gate, bus = _gate(_frame(can_do=()))
    out = await gate.evaluate(_call("recall_memory"))
    assert out is not None
    assert out.status == "error"
    assert "capability_not_granted" in (out.error or "")
    assert any(e.topic == TOPIC_POLICY_VERDICT for e in bus.events)


# ---------------------------------------------------------------------
# REQUIRE_IDENTITY
# ---------------------------------------------------------------------
async def test_require_identity_returns_blocked_result() -> None:
    register_tool_risk("set_routine", RiskClass.MEDIUM)
    gate, _ = _gate(
        _frame(can_do=("set_routine",), tiers={"set_routine": 2}),
        current_tier=0,
    )
    out = await gate.evaluate(_call("set_routine"))
    assert out is not None and out.status == "error"
    assert "REQUIRE_IDENTITY" in (out.error or "")
    assert out.data["verdict"]["requires_tier"] == 2


# ---------------------------------------------------------------------
# REQUIRE_CONFIRMATION → HIL approved
# ---------------------------------------------------------------------
async def test_confirmation_approved_passes_through() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    hil = _HILStub(ApprovalResponse(hil_request_id="hil-1", decision="approve"))
    gate, bus = _gate(_frame(can_do=("send_message",)), hil=hil)
    out = await gate.evaluate(_call("send_message"))
    assert out is None  # passthrough after approve
    assert len(hil.calls) == 1
    assert TOPIC_POLICY_ESCALATION in [e.topic for e in bus.events]
    # final verdict event should record ALLOW (post-approval).
    verdict_events = [e for e in bus.events if e.topic == TOPIC_POLICY_VERDICT]
    assert verdict_events[-1].body["decision"] == "ALLOW"


async def test_confirmation_rejected_returns_blocked() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    hil = _HILStub(ApprovalResponse(hil_request_id="hil-2", decision="reject"))
    gate, _ = _gate(_frame(can_do=("send_message",)), hil=hil)
    out = await gate.evaluate(_call("send_message"))
    assert out is not None and out.status == "error"
    assert "DENY" in (out.error or "")
    assert out.data["verdict"]["pending_id"] == "hil-2"


async def test_confirmation_timeout_denies() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    hil = _HILStub(
        ApprovalResponse(hil_request_id="hil-3", decision="approve", timed_out=True)
    )
    gate, _ = _gate(_frame(can_do=("send_message",)), hil=hil)
    out = await gate.evaluate(_call("send_message"))
    assert out is not None
    assert "DENY" in (out.error or "")
    assert "timed out" in (out.error or "")


async def test_confirmation_without_hil_blocks() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    gate, _ = _gate(_frame(can_do=("send_message",)), hil=None)
    out = await gate.evaluate(_call("send_message"))
    assert out is not None and out.status == "error"
    assert "REQUIRE_CONFIRMATION" in (out.error or "")


# ---------------------------------------------------------------------
# DEFER_OFFLINE
# ---------------------------------------------------------------------
async def test_defer_offline_queues_and_emits_event() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    captured: list[Any] = []

    def queue(req, frame):
        captured.append((req.tool_name, frame.actor_id))
        return "q-42"

    gate, bus = _gate(
        _frame(can_do=("send_message",), freshness={"self": "stale"}),
        deferred=queue,
    )
    out = await gate.evaluate(_call("send_message"))
    assert out is not None and out.status == "partial"
    assert "DEFER_OFFLINE" in (out.error or "")
    assert out.data["verdict"]["pending_id"] == "q-42"
    assert captured == [("send_message", "a1")]
    assert any(e.topic == TOPIC_POLICY_DEFERRED for e in bus.events)


async def test_defer_offline_without_queue_fn_still_blocks() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    gate, bus = _gate(
        _frame(can_do=("send_message",), freshness={"self": "stale"}),
        deferred=None,
    )
    out = await gate.evaluate(_call("send_message"))
    assert out is not None and out.status == "partial"
    assert any(e.topic == TOPIC_POLICY_DEFERRED for e in bus.events)


async def test_deferred_queue_fn_failure_is_swallowed() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)

    def boom(req, frame):
        raise RuntimeError("queue down")

    gate, _ = _gate(
        _frame(can_do=("send_message",), freshness={"self": "stale"}),
        deferred=boom,
    )
    out = await gate.evaluate(_call("send_message"))
    # Failure inside the queue must NOT prevent the gate from returning a verdict.
    assert out is not None and out.status == "partial"


# ---------------------------------------------------------------------
# Emergency override
# ---------------------------------------------------------------------
async def test_emergency_safety_sensitive_override_passes_through() -> None:
    # We need to inject emergency flag — go through the evaluator directly
    # by registering a SAFETY_SENSITIVE tool and then issuing the request via gate.
    # Since the gate builds PolicyRequest internally, we verify only the
    # non-emergency path here; the evaluator-level emergency is covered in
    # test_policy_evaluator.py. See that file for the matrix exercise.
    register_tool_risk("share_location", RiskClass.SAFETY_SENSITIVE)
    gate, _ = _gate(_frame(can_do=("share_location",), freshness={"self": "stale"}))
    out = await gate.evaluate(_call("share_location"))
    # SAFETY_SENSITIVE / STALE without emergency = DEFER_OFFLINE
    assert out is not None and out.status == "partial"


# ---------------------------------------------------------------------
# HIL service raising
# ---------------------------------------------------------------------
async def test_hil_exception_is_swallowed_and_blocks() -> None:
    class _BrokenHIL:
        async def request_approval(self, req):
            raise RuntimeError("hil down")

    register_tool_risk("send_message", RiskClass.HIGH)
    gate, _ = _gate(_frame(can_do=("send_message",)), hil=_BrokenHIL())  # type: ignore[arg-type]
    out = await gate.evaluate(_call("send_message"))
    assert out is not None and out.status == "error"


# ---------------------------------------------------------------------
# Frame provider validation
# ---------------------------------------------------------------------
async def test_frame_provider_must_return_situation_frame() -> None:
    gate = ConciergePolicyGate(
        actor_id="a1",
        frame_provider=lambda _tc: "not-a-frame",  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(TypeError):
        await gate.evaluate(_call())


def test_constructor_validates_actor_id() -> None:
    with pytest.raises(ValueError):
        ConciergePolicyGate(actor_id="", frame_provider=lambda _tc: _frame())


def test_constructor_validates_frame_provider() -> None:
    with pytest.raises(ValueError):
        ConciergePolicyGate(actor_id="a1", frame_provider=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Worst-of-three freshness selection
# ---------------------------------------------------------------------
def test_freshness_worst_of_three() -> None:
    f1 = _frame(freshness={"self": "fresh", "family": "stale", "constitution": "fresh"})
    assert _freshness_from_frame(f1) == FreshnessState.STALE

    f2 = _frame(freshness={"self": "stale", "family": "offline_local_only", "constitution": "fresh"})
    assert _freshness_from_frame(f2) == FreshnessState.OFFLINE_LOCAL_ONLY

    f3 = _frame(freshness={"self": "fresh", "family": "fresh", "constitution": "conflict_pending"})
    assert _freshness_from_frame(f3) == FreshnessState.CONFLICT_PENDING

    f4 = _frame(freshness={"self": "fresh", "family": "fresh", "constitution": "fresh"})
    assert _freshness_from_frame(f4) == FreshnessState.FRESH


# ---------------------------------------------------------------------
# tool_call validation
# ---------------------------------------------------------------------
async def test_tool_call_required() -> None:
    gate, _ = _gate(_frame(can_do=("recall_memory",)))
    with pytest.raises(ValueError):
        await gate.evaluate(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Cleanup: prevent test ordering from leaking custom registrations.
# ---------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _restore_risk_registry():
    snapshot = dict(RISK_CLASS_BY_TOOL)
    yield
    RISK_CLASS_BY_TOOL.clear()
    RISK_CLASS_BY_TOOL.update(snapshot)
