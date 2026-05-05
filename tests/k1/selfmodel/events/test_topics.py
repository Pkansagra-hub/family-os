"""M2.E3.I1 — Topic registry + payload tests."""

from __future__ import annotations

import json
import re

import pytest

from k1.bus.envelope import DeliveryMode
from k1.bus.timing.defaults import DEFAULT_RULES
from k1.selfmodel.contracts.policy import (
    PolicyDecision,
    PolicyVerdict,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.events.payloads import (
    PolicyDeferredEvent,
    PolicyEscalationEvent,
    PolicyVerdictEvent,
)
from k1.selfmodel.events.topics import (
    ALL_SELFMODEL_TOPICS,
    TOPIC_POLICY_ESCALATION,
    TOPIC_POLICY_VERDICT,
)


_TOPIC_RE = re.compile(r"^k1\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v\d+$")


@pytest.mark.parametrize("topic", list(ALL_SELFMODEL_TOPICS))
def test_topic_string_matches_canonical_pattern(topic: str) -> None:
    assert _TOPIC_RE.match(topic), f"topic {topic!r} violates k1.<domain>.<event>.<version>"


def test_topics_unique() -> None:
    assert len(set(ALL_SELFMODEL_TOPICS)) == len(ALL_SELFMODEL_TOPICS)


@pytest.mark.parametrize(
    "prefix",
    [
        "k1.selfmodel.policy",
        "k1.selfmodel.constitution",
        "k1.selfmodel.identity",
        "k1.selfmodel.startup",
    ],
)
def test_strict_delivery_for_selfmodel_prefixes(prefix: str) -> None:
    assert DEFAULT_RULES.get(prefix) == DeliveryMode.STRICT, (
        f"{prefix} must be STRICT for ordering guarantees"
    )


def test_policy_verdict_event_from_verdict() -> None:
    v = PolicyVerdict(
        decision=PolicyDecision.REQUIRE_CONFIRMATION,
        reason=ReasonCode.NEEDS_CONFIRMATION,
        detail="x",
        requires_tier=2,
        pending_id="hil-1",
        audit_required=True,
    )
    evt = PolicyVerdictEvent.from_verdict(
        actor_id="a1",
        tool_name="set_routine",
        risk_class=RiskClass.MEDIUM,
        verdict=v,
        trace_id="t1",
    )
    parsed = json.loads(json.dumps(evt.to_json()))
    assert parsed["decision"] == "REQUIRE_CONFIRMATION"
    assert parsed["risk_class"] == "medium"
    assert parsed["requires_tier"] == 2
    assert parsed["pending_id"] == "hil-1"
    assert parsed["audit_required"] is True
    assert parsed["trace_id"] == "t1"


def test_policy_escalation_event_round_trips() -> None:
    e = PolicyEscalationEvent(
        actor_id="a1",
        tool_name="send_message",
        risk_class=RiskClass.HIGH,
        hil_request_id="hil-2",
        summary="please approve",
        side_effects=("send_message",),
        trace_id="t2",
    )
    parsed = json.loads(json.dumps(e.to_json()))
    assert parsed["side_effects"] == ["send_message"]
    assert parsed["hil_request_id"] == "hil-2"


def test_policy_deferred_event_round_trips() -> None:
    e = PolicyDeferredEvent(
        actor_id="a1",
        tool_name="send_message",
        risk_class=RiskClass.HIGH,
        queued_id="q-1",
        reason=ReasonCode.OFFLINE_ONLY,
        trace_id="t3",
    )
    parsed = json.loads(json.dumps(e.to_json()))
    assert parsed["queued_id"] == "q-1"
    assert parsed["reason"] == "offline_only"


def test_canonical_topic_strings() -> None:
    assert TOPIC_POLICY_VERDICT == "k1.selfmodel.policy.verdict.v1"
    assert TOPIC_POLICY_ESCALATION == "k1.selfmodel.policy.escalation.v1"
