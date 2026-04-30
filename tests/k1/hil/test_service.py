"""Tests for HumanInTheLoopService (E1.M1.9)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import TOPIC_HIL_AUDIT, TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import (
    ApprovalRequest,
    CapabilityContractView,
    CapabilityGateRequest,
    ClarificationRequest,
    GateOutcome,
    HILKind,
    HILResponseEnvelope,
    NeedsHumanRequest,
    OverrideRequest,
)


class FakeBus:
    """In-memory event port; lets tests inject responses."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []
        self.handlers: dict[str, list] = {}

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, dict(payload)))

    def subscribe(self, topic: str, handler: Any) -> tuple[str, Any]:
        self.handlers.setdefault(topic, []).append(handler)
        return (topic, handler)

    def unsubscribe(self, handle: tuple[str, Any]) -> None:
        topic, handler = handle
        self.handlers.get(topic, []).remove(handler)

    async def deliver_response(self, hil_id: str, kind: HILKind, payload: dict) -> None:
        env = HILResponseEnvelope(
            hil_request_id=hil_id,
            kind=kind,
            responded_at_ms=2_000,
            payload=payload,
        )
        for h in list(self.handlers.get(TOPIC_HIL_RESPONSE, [])):
            await h(TOPIC_HIL_RESPONSE, env.to_dict())

    def published_request_envelopes(self) -> list[dict]:
        return [p for t, p in self.published if t == TOPIC_HIL_REQUEST]


def _svc(
    bus: FakeBus,
    *,
    config: HILConfig | None = None,
    suspension_mgr: Any | None = None,
    llm_port: Any | None = None,
) -> HumanInTheLoopService:
    return HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(None),
        suspension_mgr=suspension_mgr,
        safety_policy=SafetyBandPolicy(),
        config=config or HILConfig(),
        llm_port=llm_port,
    )


async def _drive_response(
    bus: FakeBus, kind: HILKind, payload: dict, *, delay: float = 0.01
) -> None:
    """Wait briefly for the request to be published, then deliver response."""
    for _ in range(50):
        envs = bus.published_request_envelopes()
        if envs:
            await bus.deliver_response(envs[-1]["hil_request_id"], kind, payload)
            return
        await asyncio.sleep(delay)
    raise RuntimeError("no request published")


# ---------------------------------------------------------------------------
# 1. ask_clarification happy path
# ---------------------------------------------------------------------------


async def test_ask_clarification_happy_path() -> None:
    bus = FakeBus()
    svc = _svc(bus)
    req = ClarificationRequest(
        caller_key="planner:p1", trace_id="t", pre_formed_question="?", synthesize_with_llm=False
    )

    async def responder() -> None:
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "yes"})

    asyncio.create_task(responder())
    resp = await svc.ask_clarification(req)
    assert resp.answer == "yes"
    assert resp.timed_out is False
    assert resp.round_budget_exhausted is False
    envs = bus.published_request_envelopes()
    assert len(envs) == 1
    assert envs[0]["kind"] == "clarification"
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 2. ask_clarification timeout
# ---------------------------------------------------------------------------


async def test_ask_clarification_timeout() -> None:
    bus = FakeBus()
    cfg = HILConfig(clarification_timeout_ms=50)
    svc = _svc(bus, config=cfg)
    resp = await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
            timeout_ms=50,
        )
    )
    assert resp.timed_out is True
    assert resp.answer is None
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 3. round budget exhaustion
# ---------------------------------------------------------------------------


async def test_ask_clarification_round_budget() -> None:
    bus = FakeBus()
    cfg = HILConfig(max_clarification_rounds=2)
    svc = _svc(bus, config=cfg)

    async def respond_once() -> None:
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "ok"})

    for _ in range(2):
        asyncio.create_task(respond_once())
        resp = await svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:p",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        )
        assert resp.answer == "ok"

    # 3rd call: budget exhausted, no publish.
    publishes_before = len(bus.published_request_envelopes())
    resp3 = await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
        )
    )
    assert resp3.round_budget_exhausted is True
    assert resp3.answer is None
    assert len(bus.published_request_envelopes()) == publishes_before
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 4. reset_round_budget per caller
# ---------------------------------------------------------------------------


async def test_reset_round_budget_per_caller() -> None:
    bus = FakeBus()
    cfg = HILConfig(max_clarification_rounds=1)
    svc = _svc(bus, config=cfg)

    async def go(caller: str) -> None:
        async def r():
            await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "ok"})

        asyncio.create_task(r())
        await svc.ask_clarification(
            ClarificationRequest(
                caller_key=caller,
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        )

    await go("planner:a")
    await go("planner:b")
    # Both at limit. Reset only planner:a.
    svc.reset_round_budget("planner:a")
    await go("planner:a")  # should succeed
    # planner:b still at limit:
    resp = await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:b",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
        )
    )
    assert resp.round_budget_exhausted is True
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 5. LLM synthesis
# ---------------------------------------------------------------------------


async def test_ask_clarification_llm_synthesis() -> None:
    bus = FakeBus()

    class _LLM:
        async def synthesize_question(self, *, context, max_tokens=300, trace_id=None):
            return "synth Q"

    svc = _svc(bus, llm_port=_LLM())

    async def r():
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "y"})

    asyncio.create_task(r())

    await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            question_context={"x": 1},
            synthesize_with_llm=True,
        )
    )
    env = bus.published_request_envelopes()[0]
    assert env["payload"]["question"] == "synth Q"
    await svc.shutdown()


async def test_ask_clarification_llm_failure() -> None:
    bus = FakeBus()

    class _LLM:
        async def synthesize_question(self, *, context, max_tokens=300, trace_id=None):
            raise RuntimeError("boom")

    svc = _svc(bus, llm_port=_LLM())

    async def r():
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "y"})

    asyncio.create_task(r())

    resp = await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            question_context={},
            synthesize_with_llm=True,
            pre_formed_question=None,
        )
    )
    assert resp.answer == "y"
    env = bus.published_request_envelopes()[0]
    assert env["payload"]["question"] == ""  # fallback empty
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 6. request_approval
# ---------------------------------------------------------------------------


async def test_request_approval_happy() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def r():
        await _drive_response(bus, HILKind.APPROVAL, {"decision": "approve"})

    asyncio.create_task(r())

    resp = await svc.request_approval(
        ApprovalRequest(caller_key="planner:p", trace_id="t", summary="run")
    )
    assert resp.decision == "approve"
    assert bus.published_request_envelopes()[0]["kind"] == "approval"
    await svc.shutdown()


async def test_request_approval_does_not_consume_clarification_budget() -> None:
    bus = FakeBus()
    cfg = HILConfig(max_clarification_rounds=1)
    svc = _svc(bus, config=cfg)

    async def r():
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "ok"})

    asyncio.create_task(r())
    await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
        )
    )

    # Approval should not be blocked by exhausted clarification budget.
    async def r2():
        await _drive_response(bus, HILKind.APPROVAL, {"decision": "approve"})

    asyncio.create_task(r2())
    resp = await svc.request_approval(
        ApprovalRequest(caller_key="planner:p", trace_id="t", summary="run")
    )
    assert resp.decision == "approve"
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 7. needs_human with / without suspension
# ---------------------------------------------------------------------------


class FakeSuspensionMgr:
    def __init__(self) -> None:
        self.suspended: list[tuple[str, dict]] = []
        self.resolved: list[tuple[str, dict]] = []

    async def suspend(self, task_id: str, reason: str, **kwargs: Any) -> None:
        self.suspended.append((task_id, {"reason": reason, **kwargs}))

    async def resolve(self, task_id: str, resolution: dict) -> None:
        self.resolved.append((task_id, resolution))


async def test_needs_human_with_suspension_mgr() -> None:
    bus = FakeBus()
    sm = FakeSuspensionMgr()
    svc = _svc(bus, suspension_mgr=sm)

    async def r():
        await _drive_response(
            bus,
            HILKind.NEEDS_HUMAN,
            {"decision": "ok", "resolution": {"k": "v"}},
        )

    asyncio.create_task(r())

    resp = await svc.needs_human(
        NeedsHumanRequest(
            caller_key="concierge:t1",
            task_id="t1",
            trace_id="t",
            hil_type="clarification",
            question="?",
        )
    )
    assert sm.suspended and sm.suspended[0][0] == "t1"
    assert sm.resolved and sm.resolved[0] == ("t1", {"k": "v"})
    assert resp.decision == "ok"
    assert resp.resolution == {"k": "v"}
    await svc.shutdown()


async def test_needs_human_without_suspension_mgr() -> None:
    bus = FakeBus()
    svc = _svc(bus, suspension_mgr=None)

    async def r():
        await _drive_response(bus, HILKind.NEEDS_HUMAN, {"decision": "ok", "resolution": {}})

    asyncio.create_task(r())

    resp = await svc.needs_human(
        NeedsHumanRequest(
            caller_key="concierge:t1",
            task_id="t1",
            trace_id="t",
            hil_type="clarification",
            question="?",
        )
    )
    assert resp.decision == "ok"
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 8. request_override
# ---------------------------------------------------------------------------


async def test_request_override_happy() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def r():
        await _drive_response(
            bus,
            HILKind.OVERRIDE,
            {"choice": "fallback", "fallback_action": "skip"},
        )

    asyncio.create_task(r())

    resp = await svc.request_override(
        OverrideRequest(
            caller_key="orchestrator:p",
            request_id="r1",
            trace_id="t",
            plan_id="p",
        )
    )
    assert resp.choice == "fallback"
    assert resp.fallback_action == "skip"
    assert bus.published_request_envelopes()[0]["kind"] == "override"
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 9. gate_capability matrix
# ---------------------------------------------------------------------------


def _gate_req(band: str = "GREEN", rhc: bool | None = None, side_effects=None):
    view = CapabilityContractView(
        name="cap.x",
        safety_band_min=band,
        requires_human_confirmation=rhc,
        side_effects=side_effects or [],
    )
    return CapabilityGateRequest(
        caller_key="fabric:cap.x",
        trace_id="t",
        capability_name="cap.x",
        contract=view,
    )


async def test_gate_capability_green_no_sideeffects_short_circuits() -> None:
    bus = FakeBus()
    svc = _svc(bus)
    decision = await svc.gate_capability(_gate_req("GREEN"))
    assert decision.outcome is GateOutcome.ALLOW
    # No HIL request published (audit only is acceptable; check request topic)
    assert bus.published_request_envelopes() == []
    await svc.shutdown()


async def test_gate_capability_amber_asks() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def r():
        await _drive_response(bus, HILKind.CAPABILITY_GATE, {"approved": True, "reason": "ok"})

    asyncio.create_task(r())

    decision = await svc.gate_capability(_gate_req("AMBER"))
    assert decision.outcome is GateOutcome.ASK_APPROVED
    assert decision.user_approved is True
    await svc.shutdown()


async def test_gate_capability_amber_user_denies() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def r():
        await _drive_response(bus, HILKind.CAPABILITY_GATE, {"approved": False, "reason": "no"})

    asyncio.create_task(r())

    decision = await svc.gate_capability(_gate_req("AMBER"))
    assert decision.outcome is GateOutcome.ASK_REJECTED
    assert decision.user_approved is False
    await svc.shutdown()


async def test_gate_capability_red_always_asks() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def r():
        await _drive_response(bus, HILKind.CAPABILITY_GATE, {"approved": True, "reason": "ok"})

    asyncio.create_task(r())

    decision = await svc.gate_capability(_gate_req("RED", rhc=False))
    assert decision.outcome is GateOutcome.ASK_APPROVED
    assert decision.audit_only is True
    await svc.shutdown()


async def test_gate_capability_explicit_requires_human_overrides_green() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def r():
        await _drive_response(bus, HILKind.CAPABILITY_GATE, {"approved": True, "reason": "ok"})

    asyncio.create_task(r())

    decision = await svc.gate_capability(_gate_req("GREEN", rhc=True))
    assert decision.outcome is GateOutcome.ASK_APPROVED
    await svc.shutdown()


async def test_gate_capability_timeout() -> None:
    bus = FakeBus()
    cfg = HILConfig(capability_gate_timeout_ms=50)
    svc = _svc(bus, config=cfg)
    req = _gate_req("AMBER")
    req = CapabilityGateRequest(
        caller_key=req.caller_key,
        trace_id=req.trace_id,
        capability_name=req.capability_name,
        contract=req.contract,
        timeout_ms=50,
    )
    decision = await svc.gate_capability(req)
    assert decision.outcome is GateOutcome.TIMEOUT
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 10. response correlation edge cases
# ---------------------------------------------------------------------------


async def test_response_with_unknown_id_dropped() -> None:
    bus = FakeBus()
    svc = _svc(bus)
    # Deliver a response for a hil_request_id we never created.
    await bus.deliver_response("ghost-id", HILKind.CLARIFICATION, {"answer": "x"})

    # No crash; service still functional.
    async def r():
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "ok"})

    asyncio.create_task(r())
    resp = await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
        )
    )
    assert resp.answer == "ok"
    await svc.shutdown()


async def test_concurrent_requests_independent() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def driver() -> None:
        # Wait for 3 publishes, then respond to each in reverse order.
        for _ in range(200):
            if len(bus.published_request_envelopes()) >= 3:
                break
            await asyncio.sleep(0.005)
        envs = bus.published_request_envelopes()
        # Respond out of order.
        await bus.deliver_response(
            envs[2]["hil_request_id"], HILKind.CLARIFICATION, {"answer": "c"}
        )
        await bus.deliver_response(
            envs[0]["hil_request_id"], HILKind.CLARIFICATION, {"answer": "a"}
        )
        await bus.deliver_response(
            envs[1]["hil_request_id"], HILKind.CLARIFICATION, {"answer": "b"}
        )

    asyncio.create_task(driver())
    results = await asyncio.gather(
        svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:1",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        ),
        svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:2",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        ),
        svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:3",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        ),
    )
    assert {r.answer for r in results} == {"a", "b", "c"}
    await svc.shutdown()


async def test_shutdown_cancels_pending() -> None:
    bus = FakeBus()
    cfg = HILConfig(clarification_timeout_ms=10_000)
    svc = _svc(bus, config=cfg)

    async def caller() -> Any:
        return await svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:p",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
                timeout_ms=10_000,
            )
        )

    task = asyncio.create_task(caller())
    # Wait for publish to happen.
    for _ in range(50):
        if bus.published_request_envelopes():
            break
        await asyncio.sleep(0.005)
    await svc.shutdown()
    with pytest.raises((asyncio.CancelledError, asyncio.TimeoutError)):
        await task


# ---------------------------------------------------------------------------
# 11. ledger + envelope uniqueness
# ---------------------------------------------------------------------------


class _RecordingWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write_event(self, event_type: str, payload: dict) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


async def test_ledger_writes_request_and_resolve() -> None:
    bus = FakeBus()
    w = _RecordingWriter()
    svc = HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(w),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=HILConfig(),
    )

    async def r():
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "ok"})

    asyncio.create_task(r())

    await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
        )
    )
    types = [e["event_type"] for e in w.events]
    assert "hil.requested" in types
    assert "hil.resolved" in types
    await svc.shutdown()


async def test_ledger_writes_timeout() -> None:
    bus = FakeBus()
    w = _RecordingWriter()
    svc = HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(w),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=HILConfig(clarification_timeout_ms=50),
    )
    await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
            timeout_ms=50,
        )
    )
    assert any(e["event_type"] == "hil.timed_out" for e in w.events)
    await svc.shutdown()


async def test_envelope_uuid_uniqueness() -> None:
    bus = FakeBus()
    svc = _svc(bus)

    async def driver(n: int) -> None:
        for _ in range(200):
            if len(bus.published_request_envelopes()) >= n:
                break
            await asyncio.sleep(0.005)
        for env in bus.published_request_envelopes():
            await bus.deliver_response(
                env["hil_request_id"], HILKind.CLARIFICATION, {"answer": "x"}
            )

    n = 25
    asyncio.create_task(driver(n))
    await asyncio.gather(
        *[
            svc.ask_clarification(
                ClarificationRequest(
                    caller_key=f"planner:{i}",
                    trace_id="t",
                    pre_formed_question="?",
                    synthesize_with_llm=False,
                )
            )
            for i in range(n)
        ]
    )
    ids = [e["hil_request_id"] for e in bus.published_request_envelopes()]
    assert len(ids) == n
    assert len(set(ids)) == n
    await svc.shutdown()


# ---------------------------------------------------------------------------
# 12. audit topic emission
# ---------------------------------------------------------------------------


async def test_audit_topic_disabled() -> None:
    bus = FakeBus()
    svc = _svc(bus, config=HILConfig(enable_audit_topic=False))

    async def r():
        await _drive_response(bus, HILKind.CLARIFICATION, {"answer": "ok"})

    asyncio.create_task(r())

    await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
        )
    )
    audit = [t for t, _ in bus.published if t == TOPIC_HIL_AUDIT]
    assert audit == []
    await svc.shutdown()
