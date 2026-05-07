"""E3.M2.1 -- CapabilityFabric._run_hil_gate + _summarize_params.

Verifies the private gate helper in isolation (no _execute_impl pipeline):
  - hil_port=None short-circuits to None (gate disabled).
  - ALLOW / ASK_APPROVED outcomes return None (proceed).
  - DENY -> failure CapabilityResult with error_code="hil_denied".
  - ASK_REJECTED -> "hil_rejected_by_user".
  - TIMEOUT -> "hil_timeout".
  - _summarize_params truncates long values and caps key count.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from k1.fabric.fabric import CapabilityFabric, FabricConfig
from k1.fabric.types import CapabilityRequest
from k1.hil.types import CapabilityGateRequest, GateDecision, GateOutcome

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _RecordingHILPort:
    """Stub IHILPort that records calls and returns a canned GateDecision."""

    def __init__(self, decision: GateDecision) -> None:
        self.decision = decision
        self.calls: List[CapabilityGateRequest] = []

    async def gate_capability(self, req: CapabilityGateRequest) -> GateDecision:
        self.calls.append(req)
        return self.decision

    # Other IHILPort methods unused in these tests.
    async def ask_clarification(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_approval(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def needs_human(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def request_override(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


def _stub() -> Any:
    return object()


def _build(hil_port: Any | None = None, config: FabricConfig | None = None) -> CapabilityFabric:
    return CapabilityFabric(
        resolver=_stub(),
        context_builder=_stub(),
        validation_pipeline=_stub(),
        event_emitter=_stub(),
        registry=_stub(),
        provider_factory=_stub(),
        config=config or FabricConfig(),
        hil_port=hil_port,
    )


def _contract(name: str = "tool.calendar.delete_event") -> Any:
    return SimpleNamespace(
        name=name,
        safety_band_min="AMBER",
        requires_human_confirmation=True,
        side_effects=[{"kind": "data_delete", "target": "calendar.event", "reversible": False}],
        description="delete a calendar event",
    )


def _request(**overrides: Any) -> CapabilityRequest:
    base = dict(
        request_id="req-1",
        capability_name="tool.calendar.delete_event",
        params={"event_id": "evt-99"},
        caller="test",
        trace_id="trace-1",
    )
    base.update(overrides)
    return CapabilityRequest(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# hil_port=None short-circuit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_hil_port_returns_none() -> None:
    fabric = _build(hil_port=None)
    result = await fabric._run_hil_gate(_request(), _contract(), "trace-1")
    assert result is None


# ---------------------------------------------------------------------------
# ALLOW / ASK_APPROVED -> None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allow_returns_none() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.ALLOW, hil_request_id=None, reason="green_no_side_effects")
    )
    fabric = _build(hil_port=port)
    result = await fabric._run_hil_gate(_request(), _contract(), "trace-1")
    assert result is None
    assert len(port.calls) == 1


@pytest.mark.asyncio
async def test_ask_approved_returns_none() -> None:
    port = _RecordingHILPort(
        GateDecision(
            outcome=GateOutcome.ASK_APPROVED,
            hil_request_id="hil-1",
            reason="user approved",
            user_approved=True,
        )
    )
    fabric = _build(hil_port=port)
    result = await fabric._run_hil_gate(_request(), _contract(), "trace-1")
    assert result is None


# ---------------------------------------------------------------------------
# Failure outcomes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_rejected_returns_failure_result() -> None:
    port = _RecordingHILPort(
        GateDecision(
            outcome=GateOutcome.ASK_REJECTED,
            hil_request_id="hil-2",
            reason="user said no",
            user_approved=False,
        )
    )
    fabric = _build(hil_port=port)
    result = await fabric._run_hil_gate(_request(), _contract(), "trace-1")
    assert result is not None
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "hil_rejected_by_user"
    assert result.error.retriable is False
    assert result.trace_id == "trace-1"


@pytest.mark.asyncio
async def test_deny_returns_failure_result() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.DENY, hil_request_id=None, reason="hard block")
    )
    fabric = _build(hil_port=port)
    result = await fabric._run_hil_gate(_request(), _contract(), "trace-1")
    assert result is not None
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "hil_denied"


@pytest.mark.asyncio
async def test_timeout_returns_failure_result() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.TIMEOUT, hil_request_id="hil-3", reason="no response")
    )
    fabric = _build(hil_port=port)
    result = await fabric._run_hil_gate(_request(), _contract(), "trace-1")
    assert result is not None
    assert result.error is not None
    assert result.error.code == "hil_timeout"


# ---------------------------------------------------------------------------
# Gate request shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_request_shape_is_correct() -> None:
    port = _RecordingHILPort(
        GateDecision(outcome=GateOutcome.ALLOW, hil_request_id=None, reason="ok")
    )
    cfg = FabricConfig(hil_gate_timeout_ms=45_000)
    fabric = _build(hil_port=port, config=cfg)
    contract = _contract()
    req = _request(params={"event_id": "evt-99", "calendar_id": "cal-1"})

    await fabric._run_hil_gate(req, contract, "trace-xyz")

    assert len(port.calls) == 1
    gate_req = port.calls[0]
    assert gate_req.caller_key == f"fabric:{contract.name}"
    assert gate_req.trace_id == "trace-xyz"
    assert gate_req.capability_name == contract.name
    assert gate_req.contract.name == contract.name
    assert gate_req.contract.requires_human_confirmation is True
    assert gate_req.params == {"event_id": "evt-99", "calendar_id": "cal-1"}
    assert gate_req.timeout_ms == 45_000
    # params summary should mention both keys
    assert "event_id=" in gate_req.params_summary
    assert "calendar_id=" in gate_req.params_summary


# ---------------------------------------------------------------------------
# _summarize_params
# ---------------------------------------------------------------------------


def test_summarize_params_none_returns_placeholder() -> None:
    assert CapabilityFabric._summarize_params(None) == "(no parameters)"


def test_summarize_params_empty_returns_placeholder() -> None:
    assert CapabilityFabric._summarize_params({}) == "(no parameters)"


def test_summarize_params_truncates_long_values() -> None:
    long_value = "x" * 120
    summary = CapabilityFabric._summarize_params({"big": long_value})
    # Truncated to 57 chars + "..." = 60-char string
    assert "..." in summary
    assert "x" * 57 in summary
    # Full 120-char value must not appear
    assert long_value not in summary


def test_summarize_params_truncates_many_keys() -> None:
    params = {f"k{i}": i for i in range(7)}
    summary = CapabilityFabric._summarize_params(params)
    assert summary.endswith("...")
    # First 5 keys must be present
    for i in range(5):
        assert f"k{i}=" in summary
    # 6th and 7th keys must NOT appear
    assert "k5=" not in summary
    assert "k6=" not in summary


def test_summarize_params_few_keys_no_ellipsis() -> None:
    summary = CapabilityFabric._summarize_params({"a": 1, "b": 2})
    assert summary == "a=1, b=2"
