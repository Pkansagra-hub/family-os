"""E8.M1.1 — Smoke tests for HILUserSimulator.

Verifies the test harness itself before we use it to drive scenarios:
  1. Simulator captures a real HIL request emitted by the unified
     ``HumanInTheLoopService`` running inside a fully booted kernel.
  2. Scripted responses round-trip through the bus and resolve the
     service-side future with the expected payload.
  3. Unscripted requests time out, returning ``timed_out=True``.

No mocks. The kernel boots a real bus, real ``HumanInTheLoopService``,
real ``KernelHILEventAdapter`` — only the user is simulated.
"""

from __future__ import annotations

import asyncio

import pytest

from k1.hil.types import ApprovalRequest, HILKind


@pytest.mark.asyncio
async def test_simulator_receives_real_request(kernel_service, hil_user_simulator) -> None:
    """A real HIL request flows through the bus into the simulator."""

    req = ApprovalRequest(
        caller_key="test:smoke:receive",
        trace_id="trace-recv-1",
        summary="smoke receive",
        timeout_ms=500,
    )
    # No script registered -> service will time out, but the simulator
    # must still observe the request envelope on TOPIC_HIL_REQUEST.
    resp = await kernel_service.hil_service.request_approval(req)

    assert resp.timed_out is True
    # Flush any pending bus deliveries.
    await asyncio.sleep(0.05)
    assert len(hil_user_simulator.received) == 1
    captured = hil_user_simulator.received[0]
    assert captured.kind is HILKind.APPROVAL
    assert captured.caller_key == "test:smoke:receive"
    assert captured.trace_id == "trace-recv-1"
    assert captured.payload["summary"] == "smoke receive"


@pytest.mark.asyncio
async def test_simulator_emits_scripted_response(kernel_service, hil_user_simulator) -> None:
    """A scripted response resolves the service future with the payload."""

    hil_user_simulator.script(
        HILKind.APPROVAL,
        lambda req: {"decision": "approve", "modifications": None},
    )

    req = ApprovalRequest(
        caller_key="test:smoke:approve",
        trace_id="trace-approve-1",
        summary="please approve",
        timeout_ms=2000,
    )
    resp = await kernel_service.hil_service.request_approval(req)

    assert resp.timed_out is False
    assert resp.decision == "approve"
    assert resp.modifications is None
    assert resp.hil_request_id  # non-empty echoed id


@pytest.mark.asyncio
async def test_unscripted_request_times_out(kernel_service, hil_user_simulator) -> None:
    """Without a script, the request times out and the simulator records it."""

    req = ApprovalRequest(
        caller_key="test:smoke:timeout",
        trace_id="trace-timeout-1",
        summary="no script registered",
        timeout_ms=300,
    )
    resp = await kernel_service.hil_service.request_approval(req)

    assert resp.timed_out is True
    assert resp.decision == "reject"  # service maps timeout -> reject for approval
    assert len(hil_user_simulator.received) == 1
    assert hil_user_simulator.received[0].kind is HILKind.APPROVAL
