"""
tests.poc.test_m01_topics -- Topic taxonomy validation.

Validates all 28 topic constants against the K1 TimingChain:
    - Every STRICT_TOPICS topic resolves to DeliveryMode.STRICT
    - Every RELAXED_TOPICS topic resolves to DeliveryMode.RELAXED
    - URGENT_TOPICS have the correct Priority mapping
    - Subscription groups are disjoint (no topic in both FRONT and BACK)
    - ALL_TOPICS = STRICT_TOPICS | RELAXED_TOPICS
    - Count invariants: 28 total, 26 strict, 2 relaxed, 6 urgent
"""

from __future__ import annotations

import pytest

from k1.bus.envelope import DeliveryMode
from k1.bus.timing.defaults import default_timing_config
from k1.concierge.bus.topics import (
    ALL_TOPICS,
    BACK_SUBSCRIPTIONS,
    FRONT_SUBSCRIPTIONS,
    RELAXED_TOPICS,
    STRICT_TOPICS,
    TOPIC_AFFECT_UPDATE,
    TOPIC_PROACTIVE_FILL,
    TOPIC_WEAVE_BATCH,
    URGENT_TOPICS,
    get_priority,
)


class TestTopicCounts:
    """Verify set cardinalities match V2 Section 3."""

    def test_all_topics_count(self) -> None:
        assert len(ALL_TOPICS) == 46

    def test_strict_count(self) -> None:
        assert len(STRICT_TOPICS) == 36

    def test_relaxed_count(self) -> None:
        assert len(RELAXED_TOPICS) == 10

    def test_urgent_count(self) -> None:
        assert len(URGENT_TOPICS) == 6

    def test_strict_union_relaxed_equals_all(self) -> None:
        assert STRICT_TOPICS | RELAXED_TOPICS == ALL_TOPICS

    def test_strict_relaxed_disjoint(self) -> None:
        assert STRICT_TOPICS & RELAXED_TOPICS == frozenset()


class TestTimingResolution:
    """Verify every topic resolves to the correct DeliveryMode via TimingConfig."""

    @pytest.fixture()
    def config(self):
        return default_timing_config()

    @pytest.mark.parametrize("topic", sorted(STRICT_TOPICS))
    def test_strict_topics_resolve_strict(self, config, topic: str) -> None:
        mode = config.resolve(topic)
        assert mode == DeliveryMode.STRICT, f"{topic} resolved to {mode.name}, expected STRICT"

    @pytest.mark.parametrize("topic", sorted(RELAXED_TOPICS))
    def test_relaxed_topics_resolve_relaxed(self, config, topic: str) -> None:
        mode = config.resolve(topic)
        assert mode == DeliveryMode.RELAXED, f"{topic} resolved to {mode.name}, expected RELAXED"

    def test_weave_batch_is_strict(self, config) -> None:
        """k1.internal.weave.batch.v1 must resolve STRICT (requires k1.internal rule)."""
        assert config.resolve(TOPIC_WEAVE_BATCH) == DeliveryMode.STRICT


class TestPriorityMapping:
    """Verify get_priority returns correct values per V2 table."""

    @pytest.mark.parametrize("topic", sorted(URGENT_TOPICS))
    def test_urgent_topics_priority_zero(self, topic: str) -> None:
        assert get_priority(topic) == 0  # Priority.URGENT

    def test_affect_update_background(self) -> None:
        assert get_priority(TOPIC_AFFECT_UPDATE) == 3  # Priority.BACKGROUND

    def test_proactive_fill_background(self) -> None:
        assert get_priority(TOPIC_PROACTIVE_FILL) == 3  # Priority.BACKGROUND

    def test_default_interactive(self) -> None:
        """Unlisted topics default to INTERACTIVE (2)."""
        assert get_priority("k1.orchestration.task.dispatch.v1") == 2


class TestSubscriptionGroups:
    """Verify subscription groups are well-formed."""

    def test_front_back_disjoint(self) -> None:
        overlap = FRONT_SUBSCRIPTIONS & BACK_SUBSCRIPTIONS
        assert overlap == frozenset(), f"Overlap: {overlap}"

    def test_front_subscriptions_nonempty(self) -> None:
        assert len(FRONT_SUBSCRIPTIONS) > 0

    def test_back_subscriptions_nonempty(self) -> None:
        assert len(BACK_SUBSCRIPTIONS) > 0

    def test_all_subscriptions_are_known_topics(self) -> None:
        combined = FRONT_SUBSCRIPTIONS | BACK_SUBSCRIPTIONS
        unknown = combined - ALL_TOPICS
        assert unknown == frozenset(), f"Unknown topics in subscriptions: {unknown}"
