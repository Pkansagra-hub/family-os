"""M4.E4.I1 — SelfModelMetrics tests (typed, fail-soft)."""

from __future__ import annotations

from typing import Any

from k1.selfmodel.obs.metrics import SelfModelMetrics


class FakeCollector:
    def __init__(self) -> None:
        self.inc: list[tuple[str, dict[str, Any]]] = []
        self.obs: list[tuple[str, float, dict[str, Any]]] = []

    def increment(self, name, *, labels=None):
        self.inc.append((name, dict(labels or {})))

    def observe(self, name, *, labels=None, value):
        self.obs.append((name, float(value), dict(labels or {})))


# ---------------------------------------------------------------------
# Null collector — every method is a no-op
# ---------------------------------------------------------------------
def test_null_collector_is_safe() -> None:
    m = SelfModelMetrics(None)
    m.composer_build_ms(1.5, situation_kind="x")
    m.policy_decision(decision="allow", reason="ok", risk_class="low")
    m.amendment_transition(from_state="DRAFT", to_state="VOTING")
    m.capsule_build_ms(2.0)
    m.capsule_bytes(1234)
    m.bridge_submit(topic="t", band="GREEN")
    m.bridge_sse_event(topic="t")
    m.bridge_sse_reconnect()
    m.invariant_violation(code="E3")
    m.citation_pack(size=3, build_ms=1.0)


# ---------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------
def test_composer_build_ms_emits_observe_and_increment() -> None:
    c = FakeCollector()
    SelfModelMetrics(c).composer_build_ms(2.5, situation_kind="caregiver")
    assert (SelfModelMetrics.M_COMPOSER_BUILD_MS, 2.5, {"situation_kind": "caregiver"}) in c.obs
    assert (SelfModelMetrics.M_COMPOSER_FRAME, {"situation_kind": "caregiver"}) in c.inc


def test_composer_failure_increments() -> None:
    c = FakeCollector()
    SelfModelMetrics(c).composer_failure(situation_kind="x", error="boom")
    assert c.inc == [
        (SelfModelMetrics.M_COMPOSER_FAILURE, {"situation_kind": "x", "error": "boom"})
    ]


# ---------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------
def test_policy_decision_records_labels() -> None:
    c = FakeCollector()
    SelfModelMetrics(c).policy_decision(decision="deny", reason="age_lock", risk_class="high")
    name, labels = c.inc[0]
    assert name == SelfModelMetrics.M_POLICY_DECISION
    assert labels == {"decision": "deny", "reason": "age_lock", "risk_class": "high"}


def test_policy_evaluate_ms_observes() -> None:
    c = FakeCollector()
    SelfModelMetrics(c).policy_evaluate_ms(0.42, decision="allow")
    assert c.obs == [(SelfModelMetrics.M_POLICY_EVAL_MS, 0.42, {"decision": "allow"})]


# ---------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------
def test_amendment_transition_increments() -> None:
    c = FakeCollector()
    SelfModelMetrics(c).amendment_transition(from_state="DRAFT", to_state="VOTING")
    assert c.inc == [(SelfModelMetrics.M_AMENDMENT_TRANSITION, {"from": "DRAFT", "to": "VOTING"})]


def test_amendment_invalid_transition_increments() -> None:
    c = FakeCollector()
    SelfModelMetrics(c).amendment_invalid_transition(from_state="ACTIVE", attempted="DRAFT")
    assert c.inc == [
        (SelfModelMetrics.M_AMENDMENT_INVALID_TRANSITION, {"from": "ACTIVE", "attempted": "DRAFT"})
    ]


# ---------------------------------------------------------------------
# Capsule + Citation + Bridge
# ---------------------------------------------------------------------
def test_capsule_metrics() -> None:
    c = FakeCollector()
    m = SelfModelMetrics(c)
    m.capsule_build_ms(3.0)
    m.capsule_bytes(2048)
    m.capsule_failure(error="size")
    assert (SelfModelMetrics.M_CAPSULE_BUILD_MS, 3.0, {}) in c.obs
    assert (SelfModelMetrics.M_CAPSULE_BYTES, 2048.0, {}) in c.obs
    assert (SelfModelMetrics.M_CAPSULE_FAILURE, {"error": "size"}) in c.inc


def test_citation_pack_emits_two_observations() -> None:
    c = FakeCollector()
    SelfModelMetrics(c).citation_pack(size=4, build_ms=1.5)
    names = {o[0] for o in c.obs}
    assert {SelfModelMetrics.M_CITATION_PACK_SIZE, SelfModelMetrics.M_CITATION_BUILD_MS} <= names


def test_bridge_metrics() -> None:
    c = FakeCollector()
    m = SelfModelMetrics(c)
    m.bridge_submit(topic="sync.delta", band="GREEN")
    m.bridge_submit_failure(topic="sync.delta", error="net")
    m.bridge_sse_event(topic="k0.sync.complete.v1")
    m.bridge_sse_reconnect()
    inc_names = [n for n, _ in c.inc]
    assert SelfModelMetrics.M_BRIDGE_SUBMIT in inc_names
    assert SelfModelMetrics.M_BRIDGE_SUBMIT_FAILURE in inc_names
    assert SelfModelMetrics.M_BRIDGE_SSE_EVENT in inc_names
    assert SelfModelMetrics.M_BRIDGE_SSE_RECONNECT in inc_names


# ---------------------------------------------------------------------
# Invariant
# ---------------------------------------------------------------------
def test_invariant_violation_logs_and_increments(caplog) -> None:
    c = FakeCollector()
    with caplog.at_level("ERROR"):
        SelfModelMetrics(c).invariant_violation(code="E3", detail="black egress")
    assert c.inc == [(SelfModelMetrics.M_INVARIANT_VIOLATION, {"code": "E3"})]
    assert any("INVARIANT VIOLATION" in r.message for r in caplog.records)


# ---------------------------------------------------------------------
# Collector raising — fail-soft
# ---------------------------------------------------------------------
def test_collector_increment_failure_is_swallowed() -> None:
    class Bad:
        def increment(self, *a, **kw):
            raise RuntimeError("k")

        def observe(self, *a, **kw):
            raise RuntimeError("k")

    m = SelfModelMetrics(Bad())
    m.composer_build_ms(1.0, situation_kind="x")  # must not raise
    m.invariant_violation(code="E3")
