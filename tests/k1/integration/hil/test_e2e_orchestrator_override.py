"""E8.M2.3 — End-to-end orchestrator override flow.

Verifies the orchestrator's contract with the unified
``HumanInTheLoopService``:

  * ``ConstraintResolver._hil_port`` is the kernel-level instance.
  * ``request_override`` round-trips through the bus and resolves with
    the simulator-supplied choice (``override`` / ``fallback`` / ``abort``).
  * Timeout maps to ``choice="abort"`` with ``timed_out=True``.
  * The plan invariant from E5/E6 holds: there is NO ``_pending_hil``
    registry on the orchestrator service (the unified HIL service owns
    pending state).

The driver is the ``request_override`` API itself, exactly as
``ExecutionMonitor.after_wave`` calls it from inside the orchestrator.
No mocks; only the user is simulated.
"""

from __future__ import annotations

import time

import pytest

from k1.hil.service import HumanInTheLoopService
from k1.hil.types import HILKind, OverrideRequest


@pytest.mark.asyncio
async def test_constraint_resolver_holds_unified_hil(kernel_service) -> None:
    cr = kernel_service._orchestrator._constraint_resolver  # type: ignore[attr-defined]
    assert cr._hil_port is kernel_service.hil_service
    assert isinstance(cr._hil_port, HumanInTheLoopService)


@pytest.mark.asyncio
async def test_no_pending_hil_registry_on_orchestrator(kernel_service) -> None:
    """Plan invariant: orchestrator must not maintain its own pending registry."""

    orch = kernel_service._orchestrator  # type: ignore[attr-defined]
    assert getattr(orch, "_pending_hil", None) is None


@pytest.mark.asyncio
async def test_override_round_trip_with_user_choice(
    kernel_service, hil_user_simulator
) -> None:
    """Simulator picks an override option; service returns it intact."""

    selected = {"option_id": "alt-1", "summary": "use cached result"}
    hil_user_simulator.script(
        HILKind.OVERRIDE,
        lambda req: {
            "choice": "override",
            "selected_alternative": selected,
            "fallback_action": None,
        },
    )
    cr = kernel_service._orchestrator._constraint_resolver  # type: ignore[attr-defined]
    req = OverrideRequest(
        caller_key="orchestrator:monitor:dag-001",
        request_id="req-001",
        trace_id="trace-override",
        plan_id="plan-001",
        unresolved_capabilities=["calendar.write"],
        proposed_alternatives=[selected, {"option_id": "alt-2"}],
        timeout_ms=2000,
    )
    t0 = time.monotonic()
    resp = await cr._hil_port.request_override(req)
    elapsed_ms = (time.monotonic() - t0) * 1000.0

    assert resp.timed_out is False
    assert resp.choice == "override"
    assert resp.selected_alternative == selected
    assert resp.fallback_action is None
    assert resp.hil_request_id
    assert elapsed_ms < 500.0, f"round-trip too slow: {elapsed_ms:.1f}ms"

    assert len(hil_user_simulator.received) == 1
    captured = hil_user_simulator.received[0]
    assert captured.kind is HILKind.OVERRIDE
    assert captured.caller_key == "orchestrator:monitor:dag-001"
    assert captured.payload["plan_id"] == "plan-001"
    assert captured.payload["unresolved_capabilities"] == ["calendar.write"]


@pytest.mark.asyncio
async def test_override_user_aborts(kernel_service, hil_user_simulator) -> None:
    """Simulator returns ``choice='abort'``; service surfaces it."""

    hil_user_simulator.script(
        HILKind.OVERRIDE,
        lambda req: {"choice": "abort"},
    )
    req = OverrideRequest(
        caller_key="orchestrator:monitor:dag-abort",
        request_id="req-abort",
        trace_id="trace-abort",
        plan_id="plan-abort",
        timeout_ms=2000,
    )
    resp = await kernel_service.hil_service.request_override(req)
    assert resp.timed_out is False
    assert resp.choice == "abort"
    assert resp.selected_alternative is None


@pytest.mark.asyncio
async def test_override_timeout_maps_to_abort(
    kernel_service, hil_user_simulator
) -> None:
    """No script + short timeout → ``choice='abort'`` with ``timed_out=True``."""

    req = OverrideRequest(
        caller_key="orchestrator:monitor:dag-to",
        request_id="req-to",
        trace_id="trace-override-to",
        plan_id="plan-to",
        timeout_ms=300,
    )
    resp = await kernel_service.hil_service.request_override(req)
    assert resp.timed_out is True
    assert resp.choice == "abort"
    assert resp.selected_alternative is None
