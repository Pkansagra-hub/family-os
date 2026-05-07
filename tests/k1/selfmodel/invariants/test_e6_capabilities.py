"""M2.E1.I4 — Empty-Set Invariant E6: no tool dispatch outside capabilities.

Whiteboard E6: the policy gate must DENY any tool not present in
``frame.capabilities.can_do`` ∪ ``frame.capabilities.requires_confirmation``,
regardless of risk class, freshness, or emergency flag.
"""

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

pytestmark = pytest.mark.invariant


def _empty_caps_frame() -> SituationFrame:
    return SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        capabilities=Capabilities(),  # empty: nothing allowed
    )


@pytest.mark.parametrize("risk", list(RiskClass))
@pytest.mark.parametrize("state", list(FreshnessState))
def test_e6_empty_capabilities_always_deny(risk: RiskClass, state: FreshnessState) -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        PolicyRequest(actor_id="a1", tool_name="any_tool", risk_class=risk),
        _empty_caps_frame(),
        freshness_state=state,
    )
    assert v.decision == PolicyDecision.DENY
    assert v.reason == ReasonCode.CAPABILITY_NOT_GRANTED


def test_e6_emergency_does_not_bypass_capability_check() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        PolicyRequest(
            actor_id="a1",
            tool_name="ghost_tool",
            risk_class=RiskClass.SAFETY_SENSITIVE,
            emergency=True,
        ),
        _empty_caps_frame(),
        freshness_state=FreshnessState.STALE,
    )
    assert v.decision == PolicyDecision.DENY
    assert v.reason == ReasonCode.CAPABILITY_NOT_GRANTED


def test_e6_held_tier_does_not_bypass_capability_check() -> None:
    ev = PolicyEvaluator()
    v = ev.evaluate(
        PolicyRequest(actor_id="a1", tool_name="ghost_tool", risk_class=RiskClass.LOW),
        _empty_caps_frame(),
        current_tier=99,  # super-user; still must be in capabilities
    )
    assert v.decision == PolicyDecision.DENY


def test_e6_tool_in_can_do_passes() -> None:
    """Sanity counter-test: same tool in caps is NOT denied with this reason."""
    ev = PolicyEvaluator()
    frame = SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        capabilities=Capabilities(can_do=("recall_memory",)),
    )
    v = ev.evaluate(
        PolicyRequest(actor_id="a1", tool_name="recall_memory"),
        frame,
    )
    assert v.reason != ReasonCode.CAPABILITY_NOT_GRANTED
    assert v.decision == PolicyDecision.ALLOW
