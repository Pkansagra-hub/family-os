"""DEFERRED-7 (post-P3.4 rewrite of MS-4 Epic 4.1).

Cross-component publish->bus->subscriber tests for ``dispatch_task`` across
LOW / MEDIUM / HIGH tiers.

The original Epic 4.1 spec at ``09_wiring_plan.md`` line 2938 keyed on the
``Phase1Result.complexity_tier`` field that was removed in P3.4. These tests
replace that obsolete coverage with the post-P3.4-correct surface:

    ``await dispatch_task(intents_raw, tier=..., publish_fn=...)``

publishes a ``TaskDispatch`` through a real ``BusFactory.create_local()``
LocalBus and a real subscriber receives it on ``TOPIC_TASK_DISPATCH``.
Tier propagation is asserted by deserialising the payload back into a
``TaskDispatch`` and inspecting ``.tier``.

Scope: classification + tier decision -> dispatch envelope -> bus hop.
NOT covered here (and intentionally separate concerns):
    * FSM state-machine transitions on receipt (covered by m02_e24).
    * Back actor ReAct loop on receipt (covered by m10_e101 + back tests).
    * tier derivation from ``plan: bool`` signals (covered by
      ``test_dispatch_task_plan_derivation.py``).
"""

from __future__ import annotations

import threading

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.bus.factory import BusFactory
from k1.concierge.bus.topics import TOPIC_TASK_DISPATCH
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.tools import dispatch_task


def _make_bus_publish_fn(bus, *, session_id: str, request_id: str, trace_id: str):
    """Return an async ``publish_fn`` that wraps a ``TaskDispatch`` in an
    :class:`Envelope` and pushes it through ``bus.publish``.

    Mirrors the production envelope_bridge mapping but kept inline so the
    test is self-contained and does not depend on the bridge module.
    """

    async def _publish(td: TaskDispatch) -> None:
        env = Envelope(
            topic=TOPIC_TASK_DISPATCH,
            priority=Priority.INTERACTIVE,
            cognitive_trace_id=trace_id,
            session_id=session_id,
            request_id=request_id,
            payload=td.to_payload(),
            payload_format=PayloadFormat.JSON,
        )
        bus.publish(env)

    return _publish


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tier_arg", "expected_tier"),
    [
        ("LOW", ComplexityTier.LOW),
        ("MEDIUM", ComplexityTier.MEDIUM),
        ("HIGH", ComplexityTier.HIGH),
    ],
)
async def test_dispatch_task_publishes_through_real_bus(tier_arg, expected_tier):
    """``dispatch_task(tier=...)`` -> real LocalBus -> subscriber receives
    a ``TOPIC_TASK_DISPATCH`` envelope whose payload deserialises to a
    ``TaskDispatch`` with the requested tier.

    Three parametrized cases (LOW / MEDIUM / HIGH) cover the three tier
    decision branches that the dispatcher and Back actor key on.
    """

    bus = BusFactory.create_local()
    received: list[Envelope] = []
    delivered = threading.Event()

    def _handler(env: Envelope) -> None:
        received.append(env)
        delivered.set()

    handle = bus.subscribe(TOPIC_TASK_DISPATCH, _handler)
    try:
        publish_fn = _make_bus_publish_fn(
            bus,
            session_id="sess-deferred7",
            request_id="req-deferred7",
            trace_id=f"trace-{tier_arg.lower()}",
        )

        result = await dispatch_task(
            intents_raw=[{"action": "lookup", "params": {"q": "weather"}}],
            tier=tier_arg,
            publish_fn=publish_fn,
        )

        assert bus.flush(timeout_ms=2000), "bus.flush timed out"
        assert delivered.wait(timeout=2.0), "subscriber never received envelope"

        assert result["count"] == 1
        assert result["classification"] == "single"
        assert len(result["dispatched"]) == 1

        assert len(received) == 1
        env = received[0]
        assert env.topic == TOPIC_TASK_DISPATCH
        assert env.session_id == "sess-deferred7"
        assert env.request_id == "req-deferred7"
        assert env.payload_format == PayloadFormat.JSON

        td = TaskDispatch.from_payload(env.payload)
        assert td.tier == expected_tier
        assert td.task_id == result["dispatched"][0]
        assert td.task_id.startswith("task-")
        assert len(td.intents) == 1
        assert td.intents[0].action == "lookup"
        # budget_hint is auto-derived from tier; only assert it is a positive int
        assert isinstance(td.budget_hint, int) and td.budget_hint > 0
    finally:
        bus.unsubscribe(handle)
        bus.close()
