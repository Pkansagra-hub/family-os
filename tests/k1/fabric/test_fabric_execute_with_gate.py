"""E3.M2.2 -- Verify the HIL gate is wired into ``CapabilityFabric._execute_impl``.

Integration tests use ``FabricFactory.create_for_testing`` so the full pipeline
runs end-to-end. Step 2.5 (HIL gate) sits between Step 2 (resolve) and
Step 3 (build context).

Covers:
  - GREEN capability + ALLOW gate -> provider invoked, success result.
  - AMBER capability + ASK_APPROVED -> provider invoked, success result.
  - AMBER capability + ASK_REJECTED -> failure with ``hil_rejected_by_user``;
    no ``capability.completed`` event emitted.
  - DENY -> ``hil_denied``; no ``capability.completed`` event.
  - TIMEOUT -> ``hil_timeout``; no ``capability.completed`` event.
  - ``hil_port=None`` -> gate skipped entirely; AMBER capability still runs.
  - Resolution failure -> gate NOT invoked.
  - Failure path emits a ``capability.failed`` event AND a learning signal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from k1.fabric.events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_FAILED,
    TOPIC_LEARNING_SIGNAL,
)
from k1.fabric.factory import FabricFactory
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
    Tier,
)
from k1.hil.types import CapabilityGateRequest, GateDecision, GateOutcome
from tests.k1.fabric.helpers import register_contract_with_provider

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _RecordingHILPort:
    """Stub IHILPort that records gate calls and returns a canned decision."""

    def __init__(self, decision: GateDecision) -> None:
        self.decision = decision
        self.calls: List[CapabilityGateRequest] = []

    async def gate_capability(self, req: CapabilityGateRequest) -> GateDecision:
        self.calls.append(req)
        return self.decision

    async def ask_clarification(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_approval(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def needs_human(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_override(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fabric(hil_port: Any | None = None):
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
        hil_port=hil_port,
    )


def _register_contract(
    fabric,
    *,
    name: str,
    safety_band: str = SafetyBand.AMBER.value,
    requires_human_confirmation: bool | None = True,
    side_effects: list[dict] | None = None,
    provider_id: str | None = None,
) -> CapabilityContract:
    contract = CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Gate-test capability",
        capabilities=[name],
        provider_type="MCP",
        provider_id=provider_id or f"mcp-{name.replace('.', '-')}",
        required_inputs=[InputSpec(name="query", type="STRING", description="q")],
        output={"type": "object"},
        safety_band_min=safety_band,
        requires_human_confirmation=requires_human_confirmation,
        side_effects=list(side_effects or []),
    )
    register_contract_with_provider(fabric, contract)
    return contract


def _request(name: str, *, safety_band: str = SafetyBand.AMBER.value) -> CapabilityRequest:
    return CapabilityRequest(
        capability_name=name,
        params={"query": "ping"},
        tier=Tier.LOW.value,
        caller="test-gate",
        safety_band=safety_band,
    )


def _completed_for(fabric, name: str) -> list:
    return [
        (t, p)
        for (t, p) in fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_COMPLETED)
        if p.get("capability_name") == name
    ]


# ---------------------------------------------------------------------------
# ALLOW path -- gate invoked, provider runs
# ---------------------------------------------------------------------------


async def test_green_capability_calls_gate_then_executes() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.ALLOW, hil_request_id=None, reason="green_no_side_effects")
    )
    fabric = _make_fabric(hil_port=port)
    _register_contract(
        fabric,
        name="tool.execute.gate_green",
        safety_band=SafetyBand.GREEN.value,
        requires_human_confirmation=None,
        side_effects=[],
    )

    result = await fabric.execute(
        _request("tool.execute.gate_green", safety_band=SafetyBand.GREEN.value)
    )

    assert len(port.calls) == 1, "Gate must be called exactly once"
    assert port.calls[0].capability_name == "tool.execute.gate_green"
    assert port.calls[0].caller_key == "fabric:tool.execute.gate_green"
    assert result.success is True
    assert result.error is None


async def test_amber_user_approves_executes() -> None:
    port = _RecordingHILPort(
        GateDecision(
            outcome=GateOutcome.ASK_APPROVED,
            hil_request_id="hil-1",
            reason="user approved",
            user_approved=True,
        )
    )
    fabric = _make_fabric(hil_port=port)
    _register_contract(
        fabric,
        name="tool.execute.gate_amber_ok",
        safety_band=SafetyBand.AMBER.value,
        requires_human_confirmation=True,
    )

    result = await fabric.execute(_request("tool.execute.gate_amber_ok"))

    assert len(port.calls) == 1
    assert result.success is True


# ---------------------------------------------------------------------------
# Failure paths -- provider must NOT be invoked
# ---------------------------------------------------------------------------


async def test_amber_user_rejects_returns_hil_rejected() -> None:
    port = _RecordingHILPort(
        GateDecision(
            outcome=GateOutcome.ASK_REJECTED,
            hil_request_id="hil-2",
            reason="user said no",
            user_approved=False,
        )
    )
    fabric = _make_fabric(hil_port=port)
    name = "tool.execute.gate_amber_no"
    _register_contract(fabric, name=name, requires_human_confirmation=True)

    result = await fabric.execute(_request(name))

    assert len(port.calls) == 1
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "hil_rejected_by_user"
    assert result.error.retriable is False
    # Provider was NOT executed -> no ``capability.completed`` event for this name.
    assert not _completed_for(fabric, name), "completed event must NOT fire when gate rejects"


async def test_deny_returns_hil_denied() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.DENY, hil_request_id=None, reason="hard block")
    )
    fabric = _make_fabric(hil_port=port)
    name = "tool.execute.gate_deny"
    _register_contract(fabric, name=name, requires_human_confirmation=True)

    result = await fabric.execute(_request(name))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "hil_denied"
    assert not _completed_for(fabric, name)


async def test_timeout_returns_hil_timeout() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.TIMEOUT, hil_request_id="hil-x", reason="no response")
    )
    fabric = _make_fabric(hil_port=port)
    name = "tool.execute.gate_timeout"
    _register_contract(fabric, name=name, requires_human_confirmation=True)

    result = await fabric.execute(_request(name))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "hil_timeout"
    assert not _completed_for(fabric, name)


# ---------------------------------------------------------------------------
# Backwards compatibility -- hil_port=None preserves legacy fast path
# ---------------------------------------------------------------------------


async def test_no_hil_port_skips_gate_for_amber() -> None:
    fabric = _make_fabric(hil_port=None)
    name = "tool.execute.gate_disabled"
    _register_contract(fabric, name=name, requires_human_confirmation=True)

    result = await fabric.execute(_request(name))

    # Without hil_port, AMBER + requires_human_confirmation still executes.
    assert result.success is True


# ---------------------------------------------------------------------------
# Gate is not consulted when resolution fails
# ---------------------------------------------------------------------------


async def test_gate_not_invoked_when_resolution_fails() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.ALLOW, hil_request_id=None, reason="ok")
    )
    fabric = _make_fabric(hil_port=port)
    # Do NOT register the capability -- resolution will fail.

    result = await fabric.execute(_request("tool.execute.never_registered"))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "resolution_failed"
    assert len(port.calls) == 0, "Gate must NOT be called when resolution fails"


# ---------------------------------------------------------------------------
# Failure path emits failed event + learning signal
# ---------------------------------------------------------------------------


async def test_gate_failure_emits_failed_event_and_learning_signal() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.ASK_REJECTED, hil_request_id="x", reason="no")
    )
    fabric = _make_fabric(hil_port=port)
    name = "tool.execute.gate_event_check"
    _register_contract(fabric, name=name, requires_human_confirmation=True)

    result = await fabric.execute(_request(name))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "hil_rejected_by_user"

    failed = [
        (t, p)
        for (t, p) in fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_FAILED)
        if p.get("capability_name") == name
    ]
    learning = [
        (t, p)
        for (t, p) in fabric.event_port.get_captured(topic=TOPIC_LEARNING_SIGNAL)
        if p.get("capability_name") == name
    ]
    assert len(failed) >= 1, "capability.failed must be emitted on gate rejection"
    assert len(learning) >= 1, "learning signal must be emitted on gate rejection"
