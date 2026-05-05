"""E8.M2.4 — End-to-end fabric capability gate flow.

Verifies the fabric's contract with the unified ``HumanInTheLoopService``
via the ``gate_capability`` API (the same surface
``CapabilityFabric._run_hil_gate`` invokes from inside fabric):

  * AMBER capability → gate fires → simulator approves → ``ASK_APPROVED``.
  * AMBER capability → simulator rejects → ``ASK_REJECTED``.
  * GREEN, no side-effects → ``SafetyBandPolicy`` short-circuits to
    ``ALLOW``; simulator sees ZERO ``capability_gate`` requests.
  * RED capability → gate fires regardless of safety band override
    (Decision #6 — RED is askable, ``audit_only=True``).
  * Timeout → ``GateOutcome.TIMEOUT``.

No mocks; only the user is simulated.
"""

from __future__ import annotations

import pytest

from k1.hil.service import HumanInTheLoopService
from k1.hil.types import (
    CapabilityContractView,
    CapabilityGateRequest,
    GateOutcome,
    HILKind,
)


def _view(
    name: str,
    band: str,
    *,
    rhc: bool | None = None,
    side_effects: list[dict] | None = None,
) -> CapabilityContractView:
    return CapabilityContractView(
        name=name,
        safety_band_min=band,
        requires_human_confirmation=rhc,
        side_effects=list(side_effects or []),
        description=f"test capability {name}",
    )


def _gate_req(view: CapabilityContractView, *, timeout_ms: int = 2000) -> CapabilityGateRequest:
    return CapabilityGateRequest(
        caller_key=f"fabric:{view.name}",
        trace_id=f"trace-{view.name}",
        capability_name=view.name,
        contract=view,
        params={"foo": "bar"},
        params_summary="foo=bar",
        timeout_ms=timeout_ms,
    )


@pytest.mark.asyncio
async def test_fabric_facade_holds_unified_hil(kernel_service) -> None:
    facade = kernel_service._shared_fabric.facade  # type: ignore[attr-defined]
    assert facade._hil_port is kernel_service.hil_service
    assert isinstance(facade._hil_port, HumanInTheLoopService)


@pytest.mark.asyncio
async def test_amber_gate_user_approves(
    kernel_service, hil_user_simulator
) -> None:
    """AMBER → gate fires → user approves → ``ASK_APPROVED``."""

    hil_user_simulator.script(
        HILKind.CAPABILITY_GATE,
        lambda req: {"approved": True, "reason": "user_ok"},
    )
    decision = await kernel_service.hil_service.gate_capability(
        _gate_req(_view("calendar_delete_event", "AMBER"))
    )
    assert decision.outcome is GateOutcome.ASK_APPROVED
    assert decision.user_approved is True
    assert decision.reason == "user_ok"
    assert decision.audit_only is False
    assert decision.hil_request_id

    assert len(hil_user_simulator.received) == 1
    captured = hil_user_simulator.received[0]
    assert captured.kind is HILKind.CAPABILITY_GATE
    assert captured.payload["capability_name"] == "calendar_delete_event"
    assert captured.payload["contract"]["safety_band_min"] == "AMBER"


@pytest.mark.asyncio
async def test_amber_gate_user_rejects(
    kernel_service, hil_user_simulator
) -> None:
    """AMBER → user rejects → ``ASK_REJECTED``."""

    hil_user_simulator.script(
        HILKind.CAPABILITY_GATE,
        lambda req: {"approved": False, "reason": "user_declined"},
    )
    decision = await kernel_service.hil_service.gate_capability(
        _gate_req(_view("calendar_delete_event", "AMBER"))
    )
    assert decision.outcome is GateOutcome.ASK_REJECTED
    assert decision.user_approved is False
    assert decision.reason == "user_declined"


@pytest.mark.asyncio
async def test_green_no_side_effects_allows_without_bus_traffic(
    kernel_service, hil_user_simulator
) -> None:
    """GREEN + no side_effects → ``SafetyBandPolicy`` ALLOWs; gate is silent."""

    decision = await kernel_service.hil_service.gate_capability(
        _gate_req(_view("weather_current", "GREEN"))
    )
    assert decision.outcome is GateOutcome.ALLOW
    assert decision.user_approved is None
    assert decision.hil_request_id is None
    assert decision.reason == "safety_policy_allow"
    # Critical: no request should ever have hit the bus.
    assert len(hil_user_simulator.received) == 0


@pytest.mark.asyncio
async def test_red_capability_always_asks(
    kernel_service, hil_user_simulator
) -> None:
    """RED → gate fires even with ``requires_human_confirmation=False``;
    decision carries ``audit_only=True``."""

    hil_user_simulator.script(
        HILKind.CAPABILITY_GATE,
        lambda req: {"approved": True, "reason": "user_ok_red"},
    )
    # rhc=False would normally short-circuit ALLOW; RED overrides that.
    decision = await kernel_service.hil_service.gate_capability(
        _gate_req(_view("system_reboot", "RED", rhc=False))
    )
    assert decision.outcome is GateOutcome.ASK_APPROVED
    assert decision.user_approved is True
    assert decision.audit_only is True
    assert len(hil_user_simulator.received) == 1


@pytest.mark.asyncio
async def test_amber_gate_timeout(
    kernel_service, hil_user_simulator
) -> None:
    """No script + short timeout → ``GateOutcome.TIMEOUT``."""

    decision = await kernel_service.hil_service.gate_capability(
        _gate_req(_view("calendar_delete_event", "AMBER"), timeout_ms=300)
    )
    assert decision.outcome is GateOutcome.TIMEOUT
    assert decision.user_approved is None
    assert decision.reason == "user_response_timeout"
