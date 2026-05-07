"""M5.E2.I5 — selfmodel <-> k1.bus seam.

Per IMPLEMENTATION_PLAN_SELF_MODEL.md M5.E2.I5:

    Validate: topic prefix registered; STRICT delivery for
    constitution.* and identity.*; payloads schema-validate;
    subscription-handle lifecycle clean on shutdown.

Real ``LocalBus`` + real ``TopicRegistry`` + real default
``TimingConfig``. We exercise:

* selfmodel STRICT prefixes resolve correctly
* prefix registration silences the "unknown topic" warning
* publish -> subscribe -> unsubscribe lifecycle for each
  selfmodel topic
* schema validator wired through the registry rejects bad payloads
"""

from __future__ import annotations

import json

import pytest

from k1.bus.envelope.envelope import DeliveryMode, Envelope
from k1.bus.impl.local_bus import LocalBus
from k1.bus.middleware import MiddlewareChain
from k1.bus.middleware.topic_validation import (
    TopicRegistry,
    TopicValidationMiddleware,
)
from k1.bus.timing.defaults import (
    DEFAULT_RULES,
    default_timing_config,
)
from k1.selfmodel.events.topics import (
    TOPIC_CONSTITUTION_AMENDMENT_PROPOSED,
    TOPIC_IDENTITY_SESSION_STARTED,
    TOPIC_POLICY_VERDICT,
    TOPIC_SELFMODEL_STARTUP_COMPLETE,
)

pytestmark = pytest.mark.integration


SELFMODEL_PREFIX = "k1.selfmodel."

ALL_SELFMODEL_TOPICS = (
    TOPIC_POLICY_VERDICT,
    TOPIC_CONSTITUTION_AMENDMENT_PROPOSED,
    TOPIC_IDENTITY_SESSION_STARTED,
    TOPIC_SELFMODEL_STARTUP_COMPLETE,
)


# =====================================================================
# STRICT delivery rules for every selfmodel sub-prefix
# =====================================================================
@pytest.mark.parametrize(
    "topic",
    ALL_SELFMODEL_TOPICS,
)
def test_selfmodel_topics_resolve_to_strict_delivery(topic: str) -> None:
    cfg = default_timing_config()
    assert (
        cfg.resolve(topic) == DeliveryMode.STRICT
    ), f"{topic} must be STRICT-ordered (correctness-critical)"


def test_default_rules_declare_all_selfmodel_subprefixes() -> None:
    """The four canonical selfmodel sub-prefixes are all STRICT in the
    shared DEFAULT_RULES table — this is what kernels rely on at
    startup."""
    expected = {
        "k1.selfmodel.policy",
        "k1.selfmodel.constitution",
        "k1.selfmodel.identity",
        "k1.selfmodel.startup",
    }
    for prefix in expected:
        assert DEFAULT_RULES.get(prefix) == DeliveryMode.STRICT


# =====================================================================
# TopicRegistry: prefix registration silences unknown-topic warnings
# =====================================================================
def test_prefix_registration_makes_selfmodel_topics_known() -> None:
    reg = TopicRegistry()
    reg.register_prefix(SELFMODEL_PREFIX)
    for topic in ALL_SELFMODEL_TOPICS:
        assert reg.is_known(topic), f"{topic} should match {SELFMODEL_PREFIX}"


def test_unknown_topic_warning_disappears_after_prefix_registration() -> None:
    reg = TopicRegistry()
    mw = TopicValidationMiddleware(reg)

    # Before registration: warning latched.
    env = Envelope(topic=TOPIC_POLICY_VERDICT, payload=b"{}")
    out = mw.process(env)
    assert out is not None  # soft validation never drops
    assert mw._warn_count == 1  # noqa: SLF001 — internal counter

    reg.register_prefix(SELFMODEL_PREFIX)
    out2 = mw.process(env)
    assert out2 is not None
    assert mw._warn_count == 1  # no new warning


# =====================================================================
# Publish -> subscribe -> unsubscribe lifecycle on a real LocalBus
# =====================================================================
def _build_bus() -> tuple[LocalBus, TopicRegistry]:
    reg = TopicRegistry()
    reg.register_prefix(SELFMODEL_PREFIX)
    chain = MiddlewareChain([TopicValidationMiddleware(reg)])
    bus = LocalBus(middleware=chain)
    return bus, reg


@pytest.mark.parametrize("topic", ALL_SELFMODEL_TOPICS)
def test_publish_subscribe_round_trip(topic: str) -> None:
    bus, _ = _build_bus()
    received: list[Envelope] = []
    handle = bus.subscribe(topic, received.append)

    bus.publish(Envelope(topic=topic, payload=b'{"hello":"world"}'))
    assert len(received) == 1
    assert received[0].topic == topic
    assert received[0].payload == b'{"hello":"world"}'

    # Unsubscribe and verify no further delivery.
    assert bus.unsubscribe(handle) is True
    bus.publish(Envelope(topic=topic, payload=b"{}"))
    assert len(received) == 1


def test_subscription_lifecycle_clean_on_shutdown() -> None:
    """All subscribed handlers detach cleanly via unsubscribe — no
    leak detectable via re-publish."""
    bus, _ = _build_bus()
    received: dict[str, list[Envelope]] = {t: [] for t in ALL_SELFMODEL_TOPICS}
    handles = [bus.subscribe(t, received[t].append) for t in ALL_SELFMODEL_TOPICS]

    for t in ALL_SELFMODEL_TOPICS:
        bus.publish(Envelope(topic=t, payload=b"{}"))
        assert len(received[t]) == 1

    for h in handles:
        assert bus.unsubscribe(h) is True

    for t in ALL_SELFMODEL_TOPICS:
        bus.publish(Envelope(topic=t, payload=b"{}"))
    for t in ALL_SELFMODEL_TOPICS:
        assert len(received[t]) == 1, f"{t} handler still attached after unsubscribe"


# =====================================================================
# Schema validation wired through the registry
# =====================================================================
def test_payload_validator_accepts_well_formed_constitution_amendment() -> None:
    reg = TopicRegistry()

    def validator(payload: bytes, _env: Envelope) -> None:
        body = json.loads(payload.decode("utf-8"))
        if "amendment_id" not in body:
            raise ValueError("missing amendment_id")

    reg.register(TOPIC_CONSTITUTION_AMENDMENT_PROPOSED, validator=validator)
    chain = MiddlewareChain([TopicValidationMiddleware(reg, schema_validation_mode="strict")])
    bus = LocalBus(middleware=chain)

    received: list[Envelope] = []
    bus.subscribe(TOPIC_CONSTITUTION_AMENDMENT_PROPOSED, received.append)

    good = json.dumps({"amendment_id": "amd-1", "delta": {}}).encode("utf-8")
    bus.publish(Envelope(topic=TOPIC_CONSTITUTION_AMENDMENT_PROPOSED, payload=good))
    assert len(received) == 1


def test_payload_validator_drops_bad_envelope_in_strict_mode() -> None:
    reg = TopicRegistry()

    def validator(payload: bytes, _env: Envelope) -> None:
        body = json.loads(payload.decode("utf-8"))
        if "amendment_id" not in body:
            raise ValueError("missing amendment_id")

    reg.register(TOPIC_CONSTITUTION_AMENDMENT_PROPOSED, validator=validator)
    mw = TopicValidationMiddleware(reg, schema_validation_mode="strict")
    chain = MiddlewareChain([mw])
    bus = LocalBus(middleware=chain)

    received: list[Envelope] = []
    bus.subscribe(TOPIC_CONSTITUTION_AMENDMENT_PROPOSED, received.append)

    bad = json.dumps({"no_id": "oops"}).encode("utf-8")
    bus.publish(Envelope(topic=TOPIC_CONSTITUTION_AMENDMENT_PROPOSED, payload=bad))
    assert received == []
    assert mw._schema_drops == 1  # noqa: SLF001
