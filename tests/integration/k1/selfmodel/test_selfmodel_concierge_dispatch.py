"""M5.E2.I3 — selfmodel <-> k1.concierge (dispatcher) seam.

Per IMPLEMENTATION_PLAN_SELF_MODEL.md M5.E2.I3:

    Validate: step-0 gate runs on every tool call; ALLOW path
    identical to baseline; DENY blocks; REQUIRE_CONFIRMATION
    escalates via k1.hil.HumanInTheLoopService.request_approval;
    DEFER_OFFLINE queues.
    Acceptance: all four decision branches green end-to-end.

Real ``ToolDispatcher`` wired with a real ``ConciergePolicyGate``,
exercised end-to-end through ``await dispatcher.dispatch(...)``.
A duck-typed HIL stub (matches the gate's ``request_approval``
contract) keeps this test focused on the *dispatcher seam*; the
real bus-backed HIL service is exhaustively covered in I7.
"""

from __future__ import annotations

from typing import Any

import pytest

from k1.concierge.llm.types import ToolCallResult, ToolSchema
from k1.concierge.tools.dispatcher import ToolDispatcher
from k1.concierge.tools.implementations import ToolContext
from k1.hil.types import ApprovalRequest, ApprovalResponse
from k1.selfmodel.adapters.concierge_policy_gate import ConciergePolicyGate
from k1.selfmodel.contracts.policy import RiskClass
from k1.selfmodel.contracts.risk_class_registry import register_tool_risk
from k1.selfmodel.contracts.situation import Capabilities, SituationFrame
from k1.selfmodel.events.topics import TOPIC_POLICY_VERDICT

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------
class _HILStub:
    """Minimal duck-typed HIL service matching the gate's contract."""

    def __init__(self, response: ApprovalResponse) -> None:
        self.calls: list[ApprovalRequest] = []
        self._response = response

    async def request_approval(self, req: ApprovalRequest) -> ApprovalResponse:
        self.calls.append(req)
        return self._response


class _CapturingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def publish_simple(self, topic: str, body: dict[str, Any]) -> None:
        self.events.append((topic, body))


def _frame(
    *,
    can_do: tuple[str, ...] = (),
    must_ask: tuple[str, ...] = (),
    freshness: dict[str, str] | None = None,
) -> SituationFrame:
    return SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        capabilities=Capabilities(
            can_do=can_do,
            requires_confirmation=must_ask,
            requires_identity_tier={},
        ),
        freshness=dict(freshness or {"self": "fresh", "family": "fresh", "constitution": "fresh"}),
    )


def _ctx() -> ToolContext:
    return ToolContext(
        session_manager=None,
        actor="front",
        recall_fn=lambda q, mt, mr: [{"id": "m1", "text": "hello"}],
    )


def _schemas() -> dict[str, ToolSchema]:
    """Real ToolSchema for the two tools we exercise."""
    return {
        "recall_memory": ToolSchema(
            name="recall_memory",
            description="K0 memory recall",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "memory_types": {"type": "array", "items": {"type": "string"}},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        ),
        "send_message": ToolSchema(
            name="send_message",
            description="Send a message",
            parameters={"type": "object", "properties": {}},
            side_effects=True,
        ),
    }


def _dispatcher_with_gate(
    frame: SituationFrame,
    *,
    hil: _HILStub | None = None,
    deferred=None,
) -> tuple[ToolDispatcher, _CapturingBus]:
    bus = _CapturingBus()
    gate = ConciergePolicyGate(
        actor_id="a1",
        frame_provider=lambda _tc: frame,
        hil_service=hil,
        bus=bus,
        deferred_queue_fn=deferred,
        trace_id_fn=lambda: "trace-x",
    )
    dispatcher = ToolDispatcher(
        actor="front",
        allowlist={"recall_memory", "send_message"},
        tool_schemas=_schemas(),
        ctx=_ctx(),
        tier="LOW",
        policy_gate=gate.evaluate,
    )
    return dispatcher, bus


def _call(name: str, **kwargs) -> ToolCallResult:
    args: dict[str, Any] = {"query": "hi", "memory_types": ["episodic"], "max_results": 3}
    args.update(kwargs)
    return ToolCallResult(id="c1", name=name, arguments=args)


# =====================================================================
# Branch 1 — ALLOW: gate returns None, dispatcher proceeds normally
# =====================================================================
async def test_allow_branch_dispatches_to_real_tool() -> None:
    dispatcher, bus = _dispatcher_with_gate(_frame(can_do=("recall_memory",)))
    out = await dispatcher.dispatch(_call("recall_memory"))
    assert out.status == "ok"
    assert out.data["count"] == 1
    assert out.data["memories"][0]["id"] == "m1"
    # Verdict event was emitted by the gate.
    assert any(t == TOPIC_POLICY_VERDICT for t, _ in bus.events)
    # Dispatcher recorded the call (history grows).
    assert len(dispatcher.call_history) == 1


async def test_allow_branch_baseline_parity_when_no_gate() -> None:
    """ALLOW path with gate must match baseline (no gate) behaviour."""
    baseline = ToolDispatcher(
        actor="front",
        allowlist={"recall_memory"},
        tool_schemas=_schemas(),
        ctx=_ctx(),
        tier="LOW",
    )
    base_out = await baseline.dispatch(_call("recall_memory"))

    gated, _ = _dispatcher_with_gate(_frame(can_do=("recall_memory",)))
    gated_out = await gated.dispatch(_call("recall_memory"))

    assert base_out.status == gated_out.status == "ok"
    assert base_out.data == gated_out.data


# =====================================================================
# Branch 2 — DENY: capability not granted by SituationFrame
# =====================================================================
async def test_deny_branch_blocks_before_implementation_runs() -> None:
    seen: list[str] = []
    ctx = ToolContext(
        session_manager=None,
        actor="front",
        recall_fn=lambda q, mt, mr: seen.append(q) or [],  # type: ignore[func-returns-value]
    )
    bus = _CapturingBus()
    gate = ConciergePolicyGate(
        actor_id="a1",
        frame_provider=lambda _tc: _frame(can_do=()),  # nothing allowed
        bus=bus,
        trace_id_fn=lambda: "trace-x",
    )
    dispatcher = ToolDispatcher(
        actor="front",
        allowlist={"recall_memory"},
        tool_schemas=_schemas(),
        ctx=ctx,
        tier="LOW",
        policy_gate=gate.evaluate,
    )
    out = await dispatcher.dispatch(_call("recall_memory"))
    assert out.status == "error"
    assert "capability_not_granted" in (out.error or "")
    # Tool implementation must NOT have run.
    assert seen == []


# =====================================================================
# Branch 3 — REQUIRE_CONFIRMATION: gate escalates via HIL
# =====================================================================
async def test_require_confirmation_approve_dispatches_after_hil() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)  # forces REQUIRE_CONFIRMATION
    hil = _HILStub(ApprovalResponse(hil_request_id="hil-OK", decision="approve"))
    dispatcher, _ = _dispatcher_with_gate(
        _frame(can_do=("send_message",)),
        hil=hil,
    )
    out = await dispatcher.dispatch(ToolCallResult(id="c1", name="send_message", arguments={}))
    # send_message has no implementation registered → unknown tool path
    # in execute_tool yields status="error". What we *care about* here
    # is that the gate escalated to HIL exactly once and then returned
    # None (passthrough) so the dispatcher invoked execute_tool.
    assert len(hil.calls) == 1
    assert hil.calls[0].caller_key == "selfmodel:gate:a1"
    # Passthrough: not blocked by gate (would be status=error w/ a
    # gate-shaped message). Dispatcher recorded the call.
    assert len(dispatcher.call_history) == 1
    assert out is not None  # whatever execute_tool returned


async def test_require_confirmation_reject_blocks_at_gate() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    hil = _HILStub(ApprovalResponse(hil_request_id="hil-NO", decision="reject"))
    dispatcher, _ = _dispatcher_with_gate(
        _frame(can_do=("send_message",)),
        hil=hil,
    )
    out = await dispatcher.dispatch(ToolCallResult(id="c1", name="send_message", arguments={}))
    assert out.status == "error"
    assert "DENY" in (out.error or "")
    # Implementation never reached → call_history not appended for blocked.
    assert len(dispatcher.call_history) == 0


# =====================================================================
# Branch 4 — DEFER_OFFLINE: stale freshness on safety/HIGH risk
# =====================================================================
async def test_defer_offline_branch_queues_and_returns_partial() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    queued_ids: list[str] = []

    def queue_fn(_req, _frame) -> str:
        queued_ids.append("queued-1")
        return "queued-1"

    dispatcher, _ = _dispatcher_with_gate(
        _frame(can_do=("send_message",), freshness={"self": "stale"}),
        deferred=queue_fn,
    )
    out = await dispatcher.dispatch(ToolCallResult(id="c1", name="send_message", arguments={}))
    assert out.status == "partial"
    assert "DEFER_OFFLINE" in (out.error or "")
    assert queued_ids == ["queued-1"]
    assert out.data["verdict"]["pending_id"] == "queued-1"


# =====================================================================
# Gate exception: dispatcher fails closed
# =====================================================================
async def test_gate_exception_fails_closed() -> None:
    async def boom(_tc) -> None:
        raise RuntimeError("gate down")

    dispatcher = ToolDispatcher(
        actor="front",
        allowlist={"recall_memory"},
        tool_schemas=_schemas(),
        ctx=_ctx(),
        tier="LOW",
        policy_gate=boom,
    )
    out = await dispatcher.dispatch(_call("recall_memory"))
    assert out.status == "error"
    assert "policy gate" in (out.error or "")
