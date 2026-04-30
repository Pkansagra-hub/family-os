"""Tests for k1.hil.types (E1.M1.3)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.hil.types import (
    ApprovalRequest,
    ApprovalResponse,
    CapabilityContractView,
    CapabilityGateRequest,
    ClarificationRequest,
    ClarificationResponse,
    GateDecision,
    GateOutcome,
    HILEnvelope,
    HILKind,
    HILResponseEnvelope,
    NeedsHumanRequest,
    NeedsHumanResponse,
    OverrideRequest,
    OverrideResponse,
    view_from_capability_contract,
)


def test_hilkind_values_match_topic_strings() -> None:
    assert HILKind.CLARIFICATION.value == "clarification"
    assert HILKind.APPROVAL.value == "approval"
    assert HILKind.NEEDS_HUMAN.value == "needs_human"
    assert HILKind.OVERRIDE.value == "override"
    assert HILKind.CAPABILITY_GATE.value == "capability_gate"


def test_gateoutcome_values() -> None:
    assert {o.value for o in GateOutcome} == {
        "allow",
        "deny",
        "ask_approved",
        "ask_rejected",
        "timeout",
    }


def test_clarification_request_defaults_and_frozen() -> None:
    req = ClarificationRequest(caller_key="planner:1", trace_id="t")
    assert req.synthesize_with_llm is True
    assert req.timeout_ms == 60_000
    with pytest.raises(FrozenInstanceError):
        req.caller_key = "x"  # type: ignore[misc]


def test_approval_request_construction() -> None:
    req = ApprovalRequest(
        caller_key="planner:p",
        trace_id="t",
        summary="run plan",
    )
    assert req.options == [] and req.side_effects == []


def test_needs_human_request_construction() -> None:
    req = NeedsHumanRequest(
        caller_key="concierge:task1",
        task_id="task1",
        trace_id="t",
        hil_type="clarification",
        question="?",
    )
    assert req.timeout_ms is None


def test_override_request_construction() -> None:
    req = OverrideRequest(
        caller_key="orchestrator:p",
        request_id="r",
        trace_id="t",
        plan_id="p",
    )
    assert req.unresolved_capabilities == []


def test_capability_gate_request_construction() -> None:
    view = CapabilityContractView(
        name="cap.x", safety_band_min="GREEN", requires_human_confirmation=None
    )
    req = CapabilityGateRequest(
        caller_key="fabric:cap.x",
        trace_id="t",
        capability_name="cap.x",
        contract=view,
    )
    assert req.params == {}


def test_responses_construct_and_frozen() -> None:
    cr = ClarificationResponse(hil_request_id="x", answer="y")
    assert cr.timed_out is False
    with pytest.raises(FrozenInstanceError):
        cr.answer = "z"  # type: ignore[misc]
    assert ApprovalResponse(hil_request_id="x", decision="approve").modifications is None
    assert NeedsHumanResponse(hil_request_id="x", decision="ok").resolution == {}
    assert OverrideResponse(hil_request_id="x", choice="abort").timed_out is False
    gd = GateDecision(outcome=GateOutcome.ALLOW, hil_request_id=None, reason="ok")
    assert gd.audit_only is False


def _make_env(kind: HILKind) -> HILEnvelope:
    return HILEnvelope(
        hil_request_id="abc",
        kind=kind,
        caller_key="planner:p",
        trace_id="t",
        created_at_ms=1_700_000_000_000,
        timeout_ms=60_000,
        payload={"q": "hi", "ctx": {"k": 1}},
    )


@pytest.mark.parametrize("kind", list(HILKind))
def test_hil_envelope_round_trip(kind: HILKind) -> None:
    env = _make_env(kind)
    assert HILEnvelope.from_dict(env.to_dict()) == env


@pytest.mark.parametrize("kind", list(HILKind))
def test_hil_response_envelope_round_trip(kind: HILKind) -> None:
    resp = HILResponseEnvelope(
        hil_request_id="abc",
        kind=kind,
        responded_at_ms=1_700_000_001_000,
        payload={"answer": "yes"},
        timed_out=False,
    )
    assert HILResponseEnvelope.from_dict(resp.to_dict()) == resp


def test_view_from_capability_contract_duck_typing() -> None:
    class _C:
        name = "cap.x"
        safety_band_min = "AMBER"
        requires_human_confirmation = True
        side_effects = [{"kind": "io"}]
        description = "desc"

    view = view_from_capability_contract(_C())
    assert view.name == "cap.x"
    assert view.safety_band_min == "AMBER"
    assert view.requires_human_confirmation is True
    assert view.side_effects == [{"kind": "io"}]


def test_view_from_capability_contract_defaults_for_missing_attrs() -> None:
    class _Empty:
        name = "cap.y"

    view = view_from_capability_contract(_Empty())
    assert view.safety_band_min == "GREEN"
    assert view.requires_human_confirmation is None
    assert view.side_effects == []
