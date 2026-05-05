"""M0.E1.I2 — policy contract dataclasses are frozen and minimal-construct.

The full ``RiskClass`` / ``ReasonCode`` / freshness × risk matrix lands
in M2; this test only locks in the M0 stub shape.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.selfmodel.contracts.policy import (
    PolicyDecision,
    PolicyRequest,
    PolicyVerdict,
    ReasonCode,
    RiskClass,
)


def test_policy_decision_enum_members() -> None:
    expected = {
        "ALLOW",
        "ALLOW_WITH_CAUTION",  # M14.E1.I3
        "DENY",
        "REQUIRE_CONFIRMATION",
        "REQUIRE_IDENTITY",
        "DEFER_OFFLINE",
    }
    assert {m.name for m in PolicyDecision} == expected


def test_risk_class_enum_members() -> None:
    expected = {"LOW", "MEDIUM", "HIGH", "SAFETY_SENSITIVE"}
    assert {m.name for m in RiskClass} == expected


def test_reason_code_includes_canonical_codes() -> None:
    names = {m.name for m in ReasonCode}
    assert {"OK", "CAPABILITY_NOT_GRANTED", "BLACK_BAND"} <= names


def test_policy_request_min_construct() -> None:
    req = PolicyRequest(actor_id="alice", tool_name="recall_memory")
    assert req.risk_class == RiskClass.LOW
    assert req.arguments == {}
    assert req.trace_id == ""


def test_policy_verdict_min_construct() -> None:
    v = PolicyVerdict(decision=PolicyDecision.ALLOW)
    assert v.reason == ReasonCode.OK
    assert v.detail == ""
    assert v.requires_tier == 0
    assert v.pending_id == ""


@pytest.mark.parametrize(
    "instance,field_name",
    [
        (PolicyRequest(actor_id="a", tool_name="t"), "actor_id"),
        (PolicyVerdict(decision=PolicyDecision.ALLOW), "decision"),
    ],
)
def test_policy_dataclasses_are_frozen(instance: object, field_name: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, "tampered")
