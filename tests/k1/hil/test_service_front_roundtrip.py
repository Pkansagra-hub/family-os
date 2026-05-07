"""HumanInTheLoopService <-> Front round-trip integration (E1.M2.2).

Synthetic Front handler subscribes to TOPIC_HIL_REQUEST and immediately
echoes a canned answer on TOPIC_HIL_RESPONSE. No kernel boot, no
concierge bus -- just an in-memory IEventPort that the service can use.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from k1.concierge.actors.front_hil_envelope import (
    build_hil_response_envelope_dict,
)
from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import (
    ApprovalRequest,
    CapabilityContractView,
    CapabilityGateRequest,
    ClarificationRequest,
    GateOutcome,
)


class InMemoryBus:
    """Minimal IEventPort with `(topic, payload)` semantics."""

    def __init__(self) -> None:
        self._handlers: dict[str, list] = {}
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, dict(payload)))
        # Deliver synchronously to all subscribed handlers.
        for h in list(self._handlers.get(topic, [])):
            await h(topic, dict(payload))

    def subscribe(self, topic: str, handler: Any) -> tuple[str, Any]:
        self._handlers.setdefault(topic, []).append(handler)
        return (topic, handler)

    def unsubscribe(self, handle: tuple[str, Any]) -> None:
        topic, handler = handle
        if handler in self._handlers.get(topic, []):
            self._handlers[topic].remove(handler)


class FrontEcho:
    """Stand-in Front: subscribes to TOPIC_HIL_REQUEST, replies by kind."""

    def __init__(self, bus: InMemoryBus, *, canned: dict[str, dict]) -> None:
        self.bus = bus
        self.canned = canned
        self.received: list[dict] = []
        self.handle = bus.subscribe(TOPIC_HIL_REQUEST, self._on_request)

    async def _on_request(self, topic: str, payload: dict[str, Any]) -> None:
        self.received.append(dict(payload))
        kind = payload.get("kind", "")
        resolution = self.canned.get(kind, {})
        resp = build_hil_response_envelope_dict(payload, resolution)
        await self.bus.publish(TOPIC_HIL_RESPONSE, resp)


def _svc(bus: InMemoryBus) -> HumanInTheLoopService:
    return HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(None),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=HILConfig(),
    )


# ---------------------------------------------------------------------------
# happy-path round trips
# ---------------------------------------------------------------------------


async def test_clarification_roundtrip() -> None:
    bus = InMemoryBus()
    FrontEcho(bus, canned={"clarification": {"additional_info": "tomorrow"}})
    svc = _svc(bus)
    resp = await svc.ask_clarification(
        ClarificationRequest(
            caller_key="planner:p",
            trace_id="t",
            pre_formed_question="?",
            synthesize_with_llm=False,
        )
    )
    assert resp.answer == "tomorrow"
    assert resp.timed_out is False
    await svc.shutdown()


async def test_approval_roundtrip() -> None:
    bus = InMemoryBus()
    FrontEcho(bus, canned={"approval": {"approval": True}})
    svc = _svc(bus)
    resp = await svc.request_approval(
        ApprovalRequest(caller_key="planner:p", trace_id="t", summary="run")
    )
    assert resp.decision == "approve"
    await svc.shutdown()


async def test_gate_capability_roundtrip_amber_approved() -> None:
    bus = InMemoryBus()
    FrontEcho(bus, canned={"capability_gate": {"approval": True}})
    svc = _svc(bus)
    contract = CapabilityContractView(
        name="cap.x",
        safety_band_min="AMBER",
        requires_human_confirmation=None,
        side_effects=[],
    )
    decision = await svc.gate_capability(
        CapabilityGateRequest(
            caller_key="fabric:cap.x",
            trace_id="t",
            capability_name="cap.x",
            contract=contract,
        )
    )
    assert decision.outcome is GateOutcome.ASK_APPROVED
    await svc.shutdown()


# ---------------------------------------------------------------------------
# concurrency
# ---------------------------------------------------------------------------


async def test_concurrent_3_kinds_roundtrip() -> None:
    bus = InMemoryBus()
    FrontEcho(
        bus,
        canned={
            "clarification": {"additional_info": "yes"},
            "approval": {"approval": True},
            "capability_gate": {"approval": True},
        },
    )
    svc = _svc(bus)
    contract = CapabilityContractView(
        name="cap.x",
        safety_band_min="AMBER",
        requires_human_confirmation=None,
        side_effects=[],
    )
    cl, ap, ga = await asyncio.gather(
        svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:1",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        ),
        svc.request_approval(ApprovalRequest(caller_key="planner:2", trace_id="t", summary="s")),
        svc.gate_capability(
            CapabilityGateRequest(
                caller_key="fabric:cap.x",
                trace_id="t",
                capability_name="cap.x",
                contract=contract,
            )
        ),
    )
    assert cl.answer == "yes"
    assert ap.decision == "approve"
    assert ga.outcome is GateOutcome.ASK_APPROVED
    await svc.shutdown()


async def test_correlation_id_isolation() -> None:
    """Two concurrent clarifications must each resolve to their own answer."""
    bus = InMemoryBus()

    class CorrelatingFront:
        def __init__(self) -> None:
            self.answers = {0: "first", 1: "second"}
            self.seen_count = 0
            bus.subscribe(TOPIC_HIL_REQUEST, self._on)

        async def _on(self, topic: str, payload: dict[str, Any]) -> None:
            idx = self.seen_count
            self.seen_count += 1
            resp = build_hil_response_envelope_dict(payload, {"additional_info": self.answers[idx]})
            await bus.publish(TOPIC_HIL_RESPONSE, resp)

    CorrelatingFront()
    svc = _svc(bus)
    r1, r2 = await asyncio.gather(
        svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:a",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        ),
        svc.ask_clarification(
            ClarificationRequest(
                caller_key="planner:b",
                trace_id="t",
                pre_formed_question="?",
                synthesize_with_llm=False,
            )
        ),
    )
    assert {r1.answer, r2.answer} == {"first", "second"}
    await svc.shutdown()
