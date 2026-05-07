"""M2.E1.I2 — ``PolicyEvaluator`` table-driven tests."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.policy import (
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.contracts.situation import Capabilities, SituationFrame
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator


def _frame(
    *,
    can_do: tuple[str, ...] = (),
    must_ask: tuple[str, ...] = (),
    tiers: dict[str, int] | None = None,
    actor_id: str = "a1",
) -> SituationFrame:
    return SituationFrame(
        actor_id=actor_id,
        situation_kind="caregiver_context_briefing",
        capabilities=Capabilities(
            can_do=can_do,
            requires_confirmation=must_ask,
            requires_identity_tier=dict(tiers or {}),
        ),
    )


def _req(tool: str, *, risk: RiskClass = RiskClass.LOW, **kw) -> PolicyRequest:
    return PolicyRequest(actor_id="a1", tool_name=tool, risk_class=risk, **kw)


# ---------------------------------------------------------------------
# E6 — capability check (DENY before anything else)
# ---------------------------------------------------------------------
def test_e6_unknown_tool_is_denied() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(_req("ghost_tool"), _frame(can_do=("recall_memory",)))
    assert v.decision == PolicyDecision.DENY
    assert v.reason == ReasonCode.CAPABILITY_NOT_GRANTED


def test_tool_in_can_do_passes_capability_gate() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(_req("recall_memory"), _frame(can_do=("recall_memory",)))
    assert v.decision == PolicyDecision.ALLOW


def test_tool_in_must_ask_only_still_passes_capability_gate() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("send_message", risk=RiskClass.HIGH),
        _frame(must_ask=("send_message",)),
    )
    # HIGH/FRESH base = REQUIRE_CONFIRMATION; tool is in must_ask.
    assert v.decision == PolicyDecision.REQUIRE_CONFIRMATION


# ---------------------------------------------------------------------
# Tier check
# ---------------------------------------------------------------------
def test_tier_required_but_not_held_raises_require_identity() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("set_routine", risk=RiskClass.MEDIUM),
        _frame(can_do=("set_routine",), tiers={"set_routine": 2}),
        current_tier=1,
    )
    assert v.decision == PolicyDecision.REQUIRE_IDENTITY
    assert v.requires_tier == 2
    assert v.reason == ReasonCode.IDENTITY_TIER_TOO_LOW


def test_tier_held_lets_matrix_run() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("set_routine", risk=RiskClass.MEDIUM),
        _frame(can_do=("set_routine",), tiers={"set_routine": 2}),
        current_tier=2,
    )
    assert v.decision == PolicyDecision.ALLOW


# ---------------------------------------------------------------------
# Matrix sweep — every cell × {has_rule}
# ---------------------------------------------------------------------
@pytest.mark.parametrize("risk", list(RiskClass))
@pytest.mark.parametrize("state", list(FreshnessState))
def test_full_matrix_sweep(risk: RiskClass, state: FreshnessState) -> None:
    from k1.selfmodel.contracts.policy import decision_for

    expected_decision, expected_reason = decision_for(risk, state)
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("recall_memory", risk=risk),
        _frame(can_do=("recall_memory",)),
        freshness_state=state,
    )
    assert v.decision == expected_decision
    assert v.reason == expected_reason


# ---------------------------------------------------------------------
# Confirmation upgrade (constitution tightens base ALLOW)
# ---------------------------------------------------------------------
def test_must_ask_upgrades_low_fresh_allow_to_require_confirmation() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("complete_chore"),
        _frame(must_ask=("complete_chore",)),
    )
    assert v.decision == PolicyDecision.REQUIRE_CONFIRMATION
    assert v.reason == ReasonCode.NEEDS_CONFIRMATION


def test_must_ask_does_not_loosen_deny() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("set_medication", risk=RiskClass.SAFETY_SENSITIVE),
        _frame(must_ask=("set_medication",)),
        freshness_state=FreshnessState.CONFLICT_PENDING,
    )
    assert v.decision == PolicyDecision.DENY


# ---------------------------------------------------------------------
# Emergency override
# ---------------------------------------------------------------------
def test_emergency_override_promotes_safety_sensitive_defer_to_allow_audit() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("share_location", risk=RiskClass.SAFETY_SENSITIVE, emergency=True),
        _frame(can_do=("share_location",)),
        freshness_state=FreshnessState.STALE,
    )
    assert v.decision == PolicyDecision.ALLOW
    assert v.reason == ReasonCode.EMERGENCY_OVERRIDE
    assert v.audit_required is True


def test_emergency_does_not_override_deny() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("share_location", risk=RiskClass.SAFETY_SENSITIVE, emergency=True),
        _frame(can_do=("share_location",)),
        freshness_state=FreshnessState.CONFLICT_PENDING,
    )
    assert v.decision == PolicyDecision.DENY


def test_emergency_does_not_apply_to_high_risk() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        _req("send_message", risk=RiskClass.HIGH, emergency=True),
        _frame(can_do=("send_message",)),
        freshness_state=FreshnessState.STALE,
    )
    assert v.decision == PolicyDecision.DEFER_OFFLINE


# ---------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------
def test_request_type_check() -> None:
    ev = PolicyEvaluator()
    with pytest.raises(TypeError):
        ev.evaluate("not-a-request", _frame())  # type: ignore[arg-type]


def test_frame_type_check() -> None:
    ev = PolicyEvaluator()
    with pytest.raises(TypeError):
        ev.evaluate(_req("x"), "not-a-frame")  # type: ignore[arg-type]


def test_freshness_state_type_check() -> None:
    ev = PolicyEvaluator()
    with pytest.raises(TypeError):
        ev.evaluate(
            _req("recall_memory"),
            _frame(can_do=("recall_memory",)),
            freshness_state="fresh",  # type: ignore[arg-type]
        )
