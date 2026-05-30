"""GAP-HIL-009 -- HIL presentation-ack lifecycle.

Verifies that ``require_presentation_ack=True`` enforces a two-phase wait:
the service first waits up to ``presentation_timeout_ms`` for a
``TOPIC_HIL_PRESENTED`` envelope keyed by ``hil_request_id``, and only
arms the per-kind response timer after that ack. When the ack never
arrives the request resolves with ``timed_out=True`` and a
``presentation_timeout`` reason instead of stranding a worker behind a
silent timer.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import (
    TOPIC_HIL_PRESENTED,
    TOPIC_HIL_REQUEST,
    TOPIC_HIL_RESPONSE,
)
from k1.hil.types import (
    HILKind,
    HILPresentedEnvelope,
    HILResponseEnvelope,
    NeedsHumanRequest,
)


class FakeBus:
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

    async def deliver_presented(self, hil_id: str, kind: HILKind) -> None:
        env = HILPresentedEnvelope(
            hil_request_id=hil_id,
            task_id="task-x",
            kind=kind,
            presented_at_ms=1_500,
            presentation_channel="front_chat",
            trace_id="t",
        )
        for h in list(self.handlers.get(TOPIC_HIL_PRESENTED, [])):
            await h(TOPIC_HIL_PRESENTED, env.to_dict())

    async def deliver_response(self, hil_id: str, kind: HILKind, payload: dict) -> None:
        env = HILResponseEnvelope(
            hil_request_id=hil_id,
            kind=kind,
            responded_at_ms=2_500,
            payload=payload,
        )
        for h in list(self.handlers.get(TOPIC_HIL_RESPONSE, [])):
            await h(TOPIC_HIL_RESPONSE, env.to_dict())

    def published_request_envelopes(self) -> list[dict]:
        return [p for t, p in self.published if t == TOPIC_HIL_REQUEST]


def _svc_with_presentation_ack(
    bus: FakeBus,
    *,
    presentation_timeout_ms: int = 5_000,
) -> HumanInTheLoopService:
    cfg = HILConfig(
        require_presentation_ack=True,
        presentation_timeout_ms=presentation_timeout_ms,
        # Short response timer so the test doesn't take forever once the ack arrives.
        needs_human_timeout_ms=5_000,
    )
    return HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(None),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=cfg,
        llm_port=None,
    )


@pytest.mark.asyncio
async def test_presentation_ack_then_response_resolves() -> None:
    bus = FakeBus()
    svc = _svc_with_presentation_ack(bus)
    req = NeedsHumanRequest(
        caller_key="planner:p1",
        task_id="task-x",
        trace_id="t",
        hil_type="clarification",
        question="need input",
    )

    async def drive() -> None:
        for _ in range(50):
            envs = bus.published_request_envelopes()
            if envs:
                hil_id = envs[-1]["hil_request_id"]
                await bus.deliver_presented(hil_id, HILKind.NEEDS_HUMAN)
                # Small gap to ensure the response timer has armed.
                await asyncio.sleep(0.01)
                await bus.deliver_response(
                    hil_id,
                    HILKind.NEEDS_HUMAN,
                    {"decision": "answered", "resolution": {"answer": "ok"}},
                )
                return
            await asyncio.sleep(0.01)
        raise RuntimeError("no request published")

    asyncio.create_task(drive())
    resp = await svc.needs_human(req)
    assert resp.timed_out is False
    assert resp.decision == "answered"
    assert resp.resolution.get("answer") == "ok"
    await svc.shutdown()


@pytest.mark.asyncio
async def test_presentation_ack_timeout_returns_typed_response() -> None:
    bus = FakeBus()
    # Tight presentation timeout, no ack ever sent.
    svc = _svc_with_presentation_ack(bus, presentation_timeout_ms=50)
    req = NeedsHumanRequest(
        caller_key="planner:p1",
        task_id="task-x",
        trace_id="t",
        hil_type="clarification",
        question="need input",
    )
    resp = await svc.needs_human(req)
    assert resp.timed_out is True
    assert resp.decision == "timeout"
    # Sanity: the request was actually published.
    assert bus.published_request_envelopes(), "request envelope should still be published"
    # And the counter ticked.
    assert svc._counters.get("presentation_timed_out", 0) >= 1
    await svc.shutdown()


@pytest.mark.asyncio
async def test_unknown_presentation_ack_is_ignored() -> None:
    """A stray TOPIC_HIL_PRESENTED for an unknown id must not crash the service."""
    bus = FakeBus()
    svc = _svc_with_presentation_ack(bus, presentation_timeout_ms=200)
    # Deliver an ack for a nonexistent id BEFORE any request exists.
    await bus.deliver_presented("does-not-exist", HILKind.NEEDS_HUMAN)
    # Then exercise a normal request; it should still time out cleanly.
    req = NeedsHumanRequest(
        caller_key="planner:p1",
        task_id="task-x",
        trace_id="t",
        hil_type="clarification",
        question="need input",
    )
    resp = await svc.needs_human(req)
    assert resp.timed_out is True
    assert resp.decision == "timeout"
    await svc.shutdown()
