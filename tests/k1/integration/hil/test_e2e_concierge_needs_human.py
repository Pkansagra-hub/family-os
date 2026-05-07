"""E8.M2.1 — End-to-end concierge ``needs_human`` flow.

Verifies that a concierge session — wired by ``KernelService`` — exposes
the unified ``HumanInTheLoopService`` as its ``hil_port``, and
that issuing a real ``needs_human`` request through that surface flows
over the bus to the simulator and back.

This is the FSM/back-tool integration contract: any caller that holds
``session.concierge.hil_port`` (or ``session.concierge.fsm._hil_port``)
gets the SAME globally-shared ``HumanInTheLoopService`` and a working
round-trip through ``TOPIC_HIL_REQUEST`` / ``TOPIC_HIL_RESPONSE``.

No mocks; only the user is simulated.
"""

from __future__ import annotations

import time

import pytest

from k1.hil.service import HumanInTheLoopService
from k1.hil.types import HILKind, NeedsHumanRequest


@pytest.mark.asyncio
async def test_concierge_session_exposes_unified_hil(kernel_service) -> None:
    """E7 wiring contract: concierge.hil_port is the kernel HIL service."""

    session = await kernel_service.create_session("e8-m21-wire")
    try:
        coord = session.concierge.hil_port
        assert coord is kernel_service.hil_service
        assert isinstance(coord, HumanInTheLoopService)
        # FSM holds the same instance.
        assert session.concierge.fsm._hil_port is kernel_service.hil_service
    finally:
        await kernel_service.destroy_session("e8-m21-wire")


@pytest.mark.asyncio
async def test_needs_human_round_trip_through_bus(
    kernel_service, hil_user_simulator
) -> None:
    """A ``needs_human`` request issued via the concierge surface resolves end-to-end."""

    session = await kernel_service.create_session("e8-m21-rt")
    try:
        # Script a "selected option index 0" resolution.
        hil_user_simulator.script(
            HILKind.NEEDS_HUMAN,
            lambda req: {
                "decision": "selected",
                "resolution": {"selected_option": 0},
                "raw_user_text": "yes, the first one",
            },
        )

        coord = session.concierge.hil_port
        task_id = "task-e8-m21-001"
        req = NeedsHumanRequest(
            caller_key=f"concierge:{task_id}",
            task_id=task_id,
            trace_id="trace-e8-m21",
            hil_type="selection",
            question="Which day works for the meeting?",
            options=[{"label": "Mon"}, {"label": "Tue"}],
            context={"intent": "schedule"},
            timeout_ms=2000,
        )
        t0 = time.monotonic()
        resp = await coord.needs_human(req)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        assert resp.timed_out is False
        assert resp.decision == "selected"
        assert resp.resolution == {"selected_option": 0}
        assert resp.raw_user_text == "yes, the first one"
        assert resp.hil_request_id  # echoed id
        # Latency budget per E8 exit criteria: < 500ms with immediate response.
        assert elapsed_ms < 500.0, f"round-trip too slow: {elapsed_ms:.1f}ms"

        # Simulator saw exactly one request with the concierge caller_key.
        assert len(hil_user_simulator.received) == 1
        captured = hil_user_simulator.received[0]
        assert captured.kind is HILKind.NEEDS_HUMAN
        assert captured.caller_key == f"concierge:{task_id}"
        assert captured.payload["task_id"] == task_id
        assert captured.payload["hil_type"] == "selection"
    finally:
        await kernel_service.destroy_session("e8-m21-rt")


@pytest.mark.asyncio
async def test_needs_human_timeout_returns_timed_out(
    kernel_service, hil_user_simulator
) -> None:
    """No script + short timeout → service returns ``timed_out=True``."""

    session = await kernel_service.create_session("e8-m21-to")
    try:
        coord = session.concierge.hil_port
        req = NeedsHumanRequest(
            caller_key="concierge:task-timeout",
            task_id="task-timeout",
            trace_id="trace-timeout",
            hil_type="clarification",
            question="ignored",
            timeout_ms=300,
        )
        resp = await coord.needs_human(req)
        assert resp.timed_out is True
        assert resp.decision == "timeout"
        assert resp.resolution == {}
    finally:
        await kernel_service.destroy_session("e8-m21-to")
