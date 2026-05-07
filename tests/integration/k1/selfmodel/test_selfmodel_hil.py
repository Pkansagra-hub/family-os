"""M5.E2.I7 — selfmodel <-> k1.hil seam.

Per IMPLEMENTATION_PLAN_SELF_MODEL.md M5.E2.I7:

    Validate: REQUIRE_CONFIRMATION -> ApprovalRequest envelope on
    TOPIC_HIL_REQUEST; response on TOPIC_HIL_RESPONSE resolves the
    awaited future; audit row in HIL ledger; concierge hitl_*
    modules NOT invoked by selfmodel path (assert call-count zero
    on those entry points).
    Acceptance: HIL integration green; duplication-firewall
    assertion green (selfmodel never calls
    concierge.protocols.hitl_pipeline.*).

This wires the *real* ``HumanInTheLoopService`` (with the real
``HILLedgerAdapter`` + ``SafetyBandPolicy``) onto a minimal
in-memory ``IEventPort`` bus, with a synthetic ``FrontEcho`` that
auto-approves on ``TOPIC_HIL_REQUEST`` -> ``TOPIC_HIL_RESPONSE``.
The selfmodel-side ``ConciergePolicyGate`` uses this as its HIL
service and is exercised end-to-end.
"""

from __future__ import annotations

from typing import Any

import pytest

from k1.concierge.actors.front_hil_envelope import (
    build_hil_response_envelope_dict,
)
from k1.concierge.llm.types import ToolCallResult
from k1.concierge.protocols import hitl_pipeline
from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.selfmodel.adapters.concierge_policy_gate import ConciergePolicyGate
from k1.selfmodel.contracts.policy import RiskClass
from k1.selfmodel.contracts.risk_class_registry import register_tool_risk
from k1.selfmodel.contracts.situation import Capabilities, SituationFrame

pytestmark = pytest.mark.integration


# =====================================================================
# In-memory IEventPort + FrontEcho (mirrors tests/k1/hil/test_service_*)
# =====================================================================
class InMemoryBus:
    """Minimal IEventPort with `(topic, payload)` semantics."""

    def __init__(self) -> None:
        self._handlers: dict[str, list] = {}
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, dict(payload)))
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
    """Auto-respond to HIL requests with a canned-by-kind resolution."""

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


# =====================================================================
# Helpers
# =====================================================================
def _hil_service(bus: InMemoryBus) -> HumanInTheLoopService:
    return HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(None),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=HILConfig(),
    )


def _frame() -> SituationFrame:
    return SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        capabilities=Capabilities(
            can_do=("send_message",),
            requires_confirmation=(),
            requires_identity_tier={},
        ),
        freshness={"self": "fresh", "family": "fresh", "constitution": "fresh"},
    )


def _gate(svc: HumanInTheLoopService) -> ConciergePolicyGate:
    return ConciergePolicyGate(
        actor_id="a1",
        frame_provider=lambda _tc: _frame(),
        hil_service=svc,
        trace_id_fn=lambda: "trace-x",
    )


def _send_message_call() -> ToolCallResult:
    return ToolCallResult(id="c1", name="send_message", arguments={})


# =====================================================================
# Approval round-trip: gate -> HIL -> bus -> Front -> bus -> gate
# =====================================================================
async def test_require_confirmation_approve_passes_through_real_hil() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    bus = InMemoryBus()
    FrontEcho(bus, canned={"approval": {"approval": True}})
    svc = _hil_service(bus)
    try:
        gate = _gate(svc)
        out = await gate.evaluate(_send_message_call())
        # ALLOW after approval -> passthrough.
        assert out is None
        # Bus saw exactly one HIL_REQUEST and one HIL_RESPONSE.
        topics = [t for t, _ in bus.published]
        assert topics.count(TOPIC_HIL_REQUEST) == 1
        assert topics.count(TOPIC_HIL_RESPONSE) == 1
        # Request body identifies the gate as the caller.
        req = next(p for t, p in bus.published if t == TOPIC_HIL_REQUEST)
        assert req["caller_key"] == "selfmodel:gate:a1"
        assert req["kind"] == "approval"
    finally:
        await svc.shutdown()


async def test_require_confirmation_reject_blocks_via_real_hil() -> None:
    register_tool_risk("send_message", RiskClass.HIGH)
    bus = InMemoryBus()
    FrontEcho(bus, canned={"approval": {"approval": False}})
    svc = _hil_service(bus)
    try:
        gate = _gate(svc)
        out = await gate.evaluate(_send_message_call())
        assert out is not None
        assert out.status == "error"
        assert "DENY" in (out.error or "")
    finally:
        await svc.shutdown()


class _RecordingLedgerWriter:
    """Minimal ledger writer matching the ``write_event`` shape."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write_event(self, *, event_type: str, payload: dict) -> None:
        self.events.append((event_type, dict(payload)))


async def test_hil_ledger_records_audit_row_for_approval() -> None:
    """The HIL ledger sees both ``hil.requested`` and ``hil.resolved``
    audit entries for a completed approval round-trip."""
    register_tool_risk("send_message", RiskClass.HIGH)
    bus = InMemoryBus()
    FrontEcho(bus, canned={"approval": {"approval": True}})
    writer = _RecordingLedgerWriter()
    svc = HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(writer),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=HILConfig(),
    )
    try:
        gate = ConciergePolicyGate(
            actor_id="a1",
            frame_provider=lambda _tc: _frame(),
            hil_service=svc,
            trace_id_fn=lambda: "trace-led",
        )
        await gate.evaluate(_send_message_call())
        types = [t for t, _ in writer.events]
        assert "hil.requested" in types
        assert "hil.resolved" in types
        # Both rows reference the same hil_request_id.
        req = next(p for t, p in writer.events if t == "hil.requested")
        res = next(p for t, p in writer.events if t == "hil.resolved")
        assert req["hil_request_id"] == res["hil_request_id"]
    finally:
        await svc.shutdown()


# =====================================================================
# Duplication firewall: selfmodel never invokes concierge hitl_pipeline.*
# =====================================================================
async def test_selfmodel_never_calls_concierge_hitl_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of OPP-7 separation: ``k1.selfmodel`` MUST NOT
    re-use the concierge ``hitl_pipeline`` machinery. We monkeypatch
    every function in that module with a spy and assert call-count
    zero across a full approval round-trip."""
    register_tool_risk("send_message", RiskClass.HIGH)

    spy_calls: list[str] = []

    def make_spy(name: str):
        def _spy(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            spy_calls.append(name)
            raise AssertionError(f"selfmodel path invoked concierge.protocols.hitl_pipeline.{name}")

        return _spy

    for fn_name in (
        "detect_approval_required",
        "apply_approval_modifications",
        "process_approval_response",
        "resolve_selection_to_params",
        "build_resume_params_from_selection",
    ):
        monkeypatch.setattr(hitl_pipeline, fn_name, make_spy(fn_name))

    bus = InMemoryBus()
    FrontEcho(bus, canned={"approval": {"approval": True}})
    svc = _hil_service(bus)
    try:
        gate = _gate(svc)
        out = await gate.evaluate(_send_message_call())
        # The gate approved without raising — proves no hitl_pipeline
        # function was invoked along the path.
        assert out is None
        assert spy_calls == [], f"OPP-7 violation: selfmodel invoked {spy_calls} on hitl_pipeline"
    finally:
        await svc.shutdown()
