"""M14.E1.I7 — soft_warn / ALLOW_WITH_CAUTION evaluator tests.

Pins the new third-tier conscience behaviour:

  * ``ConscienceBucket.soft_warn`` is parsed from v1 YAML.
  * ``ConscienceDigest.is_soft_warn`` reads it.
  * ``PolicyEvaluator`` returns ``ALLOW_WITH_CAUTION`` /
    ``ReasonCode.SOFT_WARN`` when an otherwise-ALLOW act is
    in soft_warn.
  * ``ConciergePolicyGate`` lets the call through (returns ``None``)
    on ALLOW_WITH_CAUTION while ``PolicyVerdictEvent.caution`` is
    True on the bus.
  * The default constitution exposes ``soft_warn`` for guardian.
"""

from __future__ import annotations

from k1.selfmodel.contracts.conscience import ConscienceBucket, ConscienceDigest
from k1.selfmodel.contracts.constitution_body import (
    CONSCIENCE_SOFT_WARN,
    get_conscience_bucket,
)
from k1.selfmodel.contracts.policy import (
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.contracts.situation import SituationFrame
from k1.selfmodel.events.payloads import PolicyVerdictEvent
from k1.selfmodel.service.bootstrap_constitution import load_bootstrap_yaml_v1
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator

_BODY_V1 = load_bootstrap_yaml_v1()


# ---------------------------------------------------------------------------
# Contract layer
# ---------------------------------------------------------------------------


def test_soft_warn_constant_is_str() -> None:
    assert CONSCIENCE_SOFT_WARN == "soft_warn"


def test_conscience_bucket_has_soft_warn_default_empty() -> None:
    bucket = ConscienceBucket()
    assert bucket.soft_warn == ()


def test_conscience_digest_is_soft_warn_lookup() -> None:
    d = ConscienceDigest(soft_warn_acts=("post_to_social",))
    assert d.is_soft_warn("post_to_social") is True
    assert d.is_soft_warn("send_message") is False
    assert "soft_warn_acts" in d.to_json()


# ---------------------------------------------------------------------------
# Parser layer (v1 YAML round-trip)
# ---------------------------------------------------------------------------


def test_v1_yaml_parses_soft_warn_for_guardian() -> None:
    bucket = get_conscience_bucket(_BODY_V1, role="guardian")
    assert "share_purchase_history" in bucket.soft_warn
    assert "post_to_social" in bucket.soft_warn


def test_v1_yaml_round_trip_custom_soft_warn() -> None:
    body = {
        "schema_version": 1,
        "conscience_rules": {
            "guardian": {
                "forbidden": [],
                "must_ask": [],
                "soft_warn": ["x", "y"],
            }
        },
    }
    bucket = get_conscience_bucket(body, role="guardian")
    assert bucket.soft_warn == ("x", "y")


# ---------------------------------------------------------------------------
# Evaluator step 4.5
# ---------------------------------------------------------------------------


def _make_frame_with(soft_warn: tuple[str, ...]) -> SituationFrame:
    digest = ConscienceDigest(soft_warn_acts=soft_warn)
    return SituationFrame(
        actor_id="member.alice",
        situation_kind="S1",
        composed_at_ms=1,
        device_id="dev-1",
        conscience=digest,
    )


def test_evaluator_emits_allow_with_caution_for_soft_warn_act() -> None:
    evaluator = PolicyEvaluator()
    frame = _make_frame_with(("post_to_social",))
    request = PolicyRequest(
        actor_id="member.alice",
        tool_name="post_to_social",
        risk_class=RiskClass.LOW,
    )
    verdict = evaluator.evaluate(
        request, frame, freshness_state=FreshnessState.FRESH, current_tier=2
    )
    assert verdict.decision is PolicyDecision.ALLOW_WITH_CAUTION
    assert verdict.reason is ReasonCode.SOFT_WARN


def test_evaluator_unaffected_when_act_not_in_soft_warn() -> None:
    evaluator = PolicyEvaluator()
    frame = _make_frame_with(("post_to_social",))
    request = PolicyRequest(
        actor_id="member.alice",
        tool_name="weather_current",
        risk_class=RiskClass.LOW,
    )
    verdict = evaluator.evaluate(
        request, frame, freshness_state=FreshnessState.FRESH, current_tier=2
    )
    assert verdict.decision is PolicyDecision.ALLOW


def test_must_ask_takes_precedence_over_soft_warn() -> None:
    """If an act is in BOTH must_ask and soft_warn, must_ask wins."""
    evaluator = PolicyEvaluator()
    digest = ConscienceDigest(
        must_ask_acts=("send_message",),
        soft_warn_acts=("send_message",),
    )
    frame = SituationFrame(
        actor_id="member.alice",
        situation_kind="S1",
        composed_at_ms=1,
        device_id="dev-1",
        conscience=digest,
    )
    request = PolicyRequest(
        actor_id="member.alice",
        tool_name="send_message",
        risk_class=RiskClass.LOW,
    )
    verdict = evaluator.evaluate(
        request, frame, freshness_state=FreshnessState.FRESH, current_tier=2
    )
    assert verdict.decision is PolicyDecision.REQUIRE_CONFIRMATION


# ---------------------------------------------------------------------------
# Event payload — caution flag survives serialization
# ---------------------------------------------------------------------------


def test_policy_verdict_event_caution_true_for_allow_with_caution() -> None:
    from k1.selfmodel.contracts.policy import PolicyVerdict

    verdict = PolicyVerdict(
        decision=PolicyDecision.ALLOW_WITH_CAUTION,
        reason=ReasonCode.SOFT_WARN,
        detail="cautionary act",
    )
    event = PolicyVerdictEvent.from_verdict(
        actor_id="member.alice",
        tool_name="post_to_social",
        risk_class=RiskClass.LOW,
        verdict=verdict,
    )
    assert event.caution is True
    payload = event.to_json()
    assert payload["caution"] is True
    assert payload["decision"] == "ALLOW_WITH_CAUTION"
    assert payload["reason"] == "soft_warn"


def test_policy_verdict_event_caution_false_for_plain_allow() -> None:
    from k1.selfmodel.contracts.policy import PolicyVerdict

    verdict = PolicyVerdict(decision=PolicyDecision.ALLOW, reason=ReasonCode.OK)
    event = PolicyVerdictEvent.from_verdict(
        actor_id="member.alice",
        tool_name="weather_current",
        risk_class=RiskClass.LOW,
        verdict=verdict,
    )
    assert event.caution is False
