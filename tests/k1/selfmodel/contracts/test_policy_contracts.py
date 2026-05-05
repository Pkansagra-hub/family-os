"""M2.E1.I1 — Extended policy contracts tests.

Covers the new ``FreshnessState`` enum, expanded ``ReasonCode`` set,
``PolicyRequest.emergency`` + ``affected_member_ids``, JSON helpers,
the canonical matrix, and ``decision_for`` defensive paths.
"""

from __future__ import annotations

import json

import pytest

from k1.selfmodel.contracts.policy import (
    DEFAULT_DECISION_MATRIX,
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    PolicyVerdict,
    ReasonCode,
    RiskClass,
    decision_for,
)


# ---------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------
def test_freshness_state_members() -> None:
    assert {s.value for s in FreshnessState} == {
        "fresh",
        "stale",
        "offline_local_only",
        "conflict_pending",
    }


def test_reason_code_extensions_present() -> None:
    expected = {
        "ok",
        "capability_not_granted",
        "needs_confirmation",
        "identity_tier_too_low",
        "projection_stale",
        "offline_only",
        "black_band",
        "constitution_conflict",
        "emergency_override",
        "unknown_tool",
        "soft_warn",  # M14.E1.I3
    }
    assert {r.value for r in ReasonCode} == expected


# ---------------------------------------------------------------------
# Matrix coverage
# ---------------------------------------------------------------------
def test_matrix_covers_every_risk_x_state_cell() -> None:
    states = list(FreshnessState)
    for risk in RiskClass:
        row = DEFAULT_DECISION_MATRIX[risk]
        for state in states:
            assert state in row, f"missing cell ({risk}, {state})"


@pytest.mark.parametrize(
    ("risk", "state", "decision", "reason"),
    [
        # low row — always allow, reason reflects state
        (RiskClass.LOW, FreshnessState.FRESH, PolicyDecision.ALLOW, ReasonCode.OK),
        (RiskClass.LOW, FreshnessState.STALE, PolicyDecision.ALLOW, ReasonCode.PROJECTION_STALE),
        (
            RiskClass.LOW,
            FreshnessState.OFFLINE_LOCAL_ONLY,
            PolicyDecision.ALLOW,
            ReasonCode.OFFLINE_ONLY,
        ),
        (
            RiskClass.LOW,
            FreshnessState.CONFLICT_PENDING,
            PolicyDecision.ALLOW,
            ReasonCode.CONSTITUTION_CONFLICT,
        ),
        # medium row
        (RiskClass.MEDIUM, FreshnessState.FRESH, PolicyDecision.ALLOW, ReasonCode.OK),
        (
            RiskClass.MEDIUM,
            FreshnessState.STALE,
            PolicyDecision.REQUIRE_CONFIRMATION,
            ReasonCode.PROJECTION_STALE,
        ),
        (
            RiskClass.MEDIUM,
            FreshnessState.OFFLINE_LOCAL_ONLY,
            PolicyDecision.REQUIRE_CONFIRMATION,
            ReasonCode.OFFLINE_ONLY,
        ),
        (
            RiskClass.MEDIUM,
            FreshnessState.CONFLICT_PENDING,
            PolicyDecision.DENY,
            ReasonCode.CONSTITUTION_CONFLICT,
        ),
        # high row
        (
            RiskClass.HIGH,
            FreshnessState.FRESH,
            PolicyDecision.REQUIRE_CONFIRMATION,
            ReasonCode.NEEDS_CONFIRMATION,
        ),
        (
            RiskClass.HIGH,
            FreshnessState.STALE,
            PolicyDecision.DEFER_OFFLINE,
            ReasonCode.PROJECTION_STALE,
        ),
        (
            RiskClass.HIGH,
            FreshnessState.OFFLINE_LOCAL_ONLY,
            PolicyDecision.DEFER_OFFLINE,
            ReasonCode.OFFLINE_ONLY,
        ),
        (
            RiskClass.HIGH,
            FreshnessState.CONFLICT_PENDING,
            PolicyDecision.DENY,
            ReasonCode.CONSTITUTION_CONFLICT,
        ),
        # safety_sensitive row
        (
            RiskClass.SAFETY_SENSITIVE,
            FreshnessState.FRESH,
            PolicyDecision.REQUIRE_CONFIRMATION,
            ReasonCode.NEEDS_CONFIRMATION,
        ),
        (
            RiskClass.SAFETY_SENSITIVE,
            FreshnessState.STALE,
            PolicyDecision.DEFER_OFFLINE,
            ReasonCode.PROJECTION_STALE,
        ),
        (
            RiskClass.SAFETY_SENSITIVE,
            FreshnessState.OFFLINE_LOCAL_ONLY,
            PolicyDecision.DEFER_OFFLINE,
            ReasonCode.OFFLINE_ONLY,
        ),
        (
            RiskClass.SAFETY_SENSITIVE,
            FreshnessState.CONFLICT_PENDING,
            PolicyDecision.DENY,
            ReasonCode.CONSTITUTION_CONFLICT,
        ),
    ],
)
def test_decision_for_table(risk, state, decision, reason) -> None:
    d, r = decision_for(risk, state)
    assert d == decision
    assert r == reason


def test_decision_for_unknown_risk_defaults_deny() -> None:
    d, r = decision_for("nonsense", FreshnessState.FRESH)  # type: ignore[arg-type]
    assert d == PolicyDecision.DENY
    assert r == ReasonCode.UNKNOWN_TOOL


def test_decision_for_unknown_state_defaults_deny() -> None:
    d, r = decision_for(RiskClass.MEDIUM, "weird")  # type: ignore[arg-type]
    assert d == PolicyDecision.DENY


# ---------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------
def test_request_to_json_round_trips() -> None:
    req = PolicyRequest(
        actor_id="a1",
        tool_name="set_routine",
        risk_class=RiskClass.MEDIUM,
        arguments={"k": "v"},
        trace_id="t1",
        emergency=True,
        affected_member_ids=("c1", "c2"),
    )
    blob = json.dumps(req.to_json())  # must not raise
    parsed = json.loads(blob)
    assert parsed["risk_class"] == "medium"
    assert parsed["affected_member_ids"] == ["c1", "c2"]
    assert parsed["emergency"] is True


def test_verdict_to_json_round_trips() -> None:
    v = PolicyVerdict(
        decision=PolicyDecision.REQUIRE_CONFIRMATION,
        reason=ReasonCode.NEEDS_CONFIRMATION,
        detail="x",
        requires_tier=2,
        pending_id="hil-1",
        audit_required=True,
    )
    parsed = json.loads(json.dumps(v.to_json()))
    assert parsed == {
        "decision": "REQUIRE_CONFIRMATION",
        "reason": "needs_confirmation",
        "detail": "x",
        "requires_tier": 2,
        "pending_id": "hil-1",
        "audit_required": True,
    }
