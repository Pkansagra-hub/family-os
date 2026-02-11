"""
Tests for k1.bus.middleware.topic_validation -- TopicRegistry + TopicValidationMiddleware.

Covers:
    TopicRegistry:
        - Exact topic registration and lookup
        - Prefix registration and matching
        - Wildcard registration (fnmatch glob)
        - Unregister by exact/prefix/wildcard
        - Size and clear
        - Unknown topic returns False

    TopicValidationMiddleware:
        - Known topic passes silently
        - Unknown topic logs warning but does NOT drop
        - Warning count increments
        - Middleware Protocol conformance
        - Never returns None (soft validation)
        - Multiple unknown topics accumulate warnings
"""

from __future__ import annotations

import logging

import pytest

from k1.bus.envelope import Envelope
from k1.bus.middleware import Middleware
from k1.bus.middleware.topic_validation import TopicRegistry, TopicValidationMiddleware

# ---------------------------------------------------------------------------
# TopicRegistry
# ---------------------------------------------------------------------------


class TestTopicRegistryExact:
    """Exact topic registration and lookup."""

    def test_register_and_find(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.capability.completed.v1")
        assert reg.is_known("k1.capability.completed.v1")

    def test_unknown_topic(self) -> None:
        reg = TopicRegistry()
        assert not reg.is_known("k1.unknown.topic")

    def test_multiple_exact(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.a")
        reg.register("k1.b")
        assert reg.is_known("k1.a")
        assert reg.is_known("k1.b")
        assert not reg.is_known("k1.c")

    def test_unregister_exact(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.test.topic")
        assert reg.unregister("k1.test.topic")
        assert not reg.is_known("k1.test.topic")

    def test_unregister_nonexistent(self) -> None:
        reg = TopicRegistry()
        assert not reg.unregister("k1.never.registered")


class TestTopicRegistryPrefix:
    """Prefix registration and matching."""

    def test_prefix_match(self) -> None:
        reg = TopicRegistry()
        reg.register_prefix("k1.agent.")
        assert reg.is_known("k1.agent.abc.delta.v1")
        assert reg.is_known("k1.agent.xyz")
        assert not reg.is_known("k1.capability.completed")

    def test_prefix_exact_boundary(self) -> None:
        reg = TopicRegistry()
        reg.register_prefix("k1.agent.")
        # Prefix must start with "k1.agent." -- "k1.agent" alone won't match
        assert not reg.is_known("k1.agent")

    def test_multiple_prefixes(self) -> None:
        reg = TopicRegistry()
        reg.register_prefix("k1.agent.")
        reg.register_prefix("k1.capability.")
        assert reg.is_known("k1.agent.test")
        assert reg.is_known("k1.capability.done")
        assert not reg.is_known("k1.session.start")

    def test_unregister_prefix(self) -> None:
        reg = TopicRegistry()
        reg.register_prefix("k1.test.")
        assert reg.unregister("k1.test.")
        assert not reg.is_known("k1.test.something")

    def test_duplicate_prefix_not_added(self) -> None:
        reg = TopicRegistry()
        reg.register_prefix("k1.test.")
        reg.register_prefix("k1.test.")
        assert reg.size == 1


class TestTopicRegistryWildcard:
    """Wildcard (fnmatch glob) registration."""

    def test_wildcard_star(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.agent.*.delta.*")
        assert reg.is_known("k1.agent.abc.delta.v1")
        assert reg.is_known("k1.agent.xyz.delta.v2")
        assert not reg.is_known("k1.agent.abc.state.v1")

    def test_wildcard_question_mark(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.test.?.done")
        assert reg.is_known("k1.test.a.done")
        assert not reg.is_known("k1.test.ab.done")

    def test_unregister_wildcard(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.*.wildcard")
        assert reg.unregister("k1.*.wildcard")
        assert not reg.is_known("k1.test.wildcard")

    def test_duplicate_wildcard_not_added(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.*.test")
        reg.register("k1.*.test")
        assert reg.size == 1


class TestTopicRegistryMixed:
    """Mixed registration modes and utility methods."""

    def test_size_counts_all(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.exact.topic")
        reg.register_prefix("k1.prefix.")
        reg.register("k1.*.wildcard")
        assert reg.size == 3

    def test_clear(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.a")
        reg.register_prefix("k1.b.")
        reg.register("k1.*.c")
        reg.clear()
        assert reg.size == 0
        assert not reg.is_known("k1.a")

    def test_exact_takes_priority_over_prefix(self) -> None:
        """Exact match is checked first (O(1) vs O(n))."""
        reg = TopicRegistry()
        reg.register("k1.agent.specific")
        reg.register_prefix("k1.agent.")
        # Both match, but exact is checked first
        assert reg.is_known("k1.agent.specific")

    def test_repr(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.a")
        reg.register_prefix("k1.b.")
        reg.register("k1.*.c")
        r = repr(reg)
        assert "exact=1" in r
        assert "prefixes=1" in r
        assert "wildcards=1" in r


# ---------------------------------------------------------------------------
# TopicValidationMiddleware
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_with_topics() -> TopicRegistry:
    """Registry with some known topics."""
    reg = TopicRegistry()
    reg.register("k1.capability.completed.v1")
    reg.register("k1.orchestration.phase.v1")
    reg.register_prefix("k1.agent.")
    reg.register("k1.session.*.v1")
    return reg


class TestTopicValidationProtocol:
    """TopicValidationMiddleware satisfies the Middleware Protocol."""

    def test_isinstance_middleware(self) -> None:
        reg = TopicRegistry()
        mw = TopicValidationMiddleware(reg)
        assert isinstance(mw, Middleware)


class TestTopicValidationSoftCheck:
    """Soft validation: warns but never drops."""

    def test_known_topic_passes_silently(self, registry_with_topics: TopicRegistry) -> None:
        mw = TopicValidationMiddleware(registry_with_topics)
        env = Envelope(
            topic="k1.capability.completed.v1",
            envelope_id=1,
            payload=b"x",
        )
        result = mw.process(env)
        assert result is env
        assert mw.warning_count == 0

    def test_known_prefix_passes(self, registry_with_topics: TopicRegistry) -> None:
        mw = TopicValidationMiddleware(registry_with_topics)
        env = Envelope(
            topic="k1.agent.abc.delta.v1",
            envelope_id=2,
            payload=b"x",
        )
        result = mw.process(env)
        assert result is env
        assert mw.warning_count == 0

    def test_known_wildcard_passes(self, registry_with_topics: TopicRegistry) -> None:
        mw = TopicValidationMiddleware(registry_with_topics)
        env = Envelope(
            topic="k1.session.start.v1",
            envelope_id=3,
            payload=b"x",
        )
        result = mw.process(env)
        assert result is env
        assert mw.warning_count == 0

    def test_unknown_topic_warns_but_delivers(
        self, registry_with_topics: TopicRegistry, caplog: pytest.LogCaptureFixture
    ) -> None:
        mw = TopicValidationMiddleware(registry_with_topics)
        env = Envelope(
            topic="k1.totally.unknown.topic",
            envelope_id=4,
            payload=b"x",
        )
        with caplog.at_level(logging.WARNING):
            result = mw.process(env)

        # NEVER drops -- soft validation
        assert result is env
        assert mw.warning_count == 1
        assert "Unknown topic" in caplog.text
        assert "k1.totally.unknown.topic" in caplog.text

    def test_multiple_unknown_topics_accumulate(self, registry_with_topics: TopicRegistry) -> None:
        mw = TopicValidationMiddleware(registry_with_topics)
        for i in range(5):
            env = Envelope(
                topic=f"k1.rogue.topic.{i}",
                envelope_id=10 + i,
                payload=b"x",
            )
            result = mw.process(env)
            assert result is not None  # Never drops

        assert mw.warning_count == 5

    def test_never_returns_none(self, registry_with_topics: TopicRegistry) -> None:
        """Soft validation: process() ALWAYS returns the envelope."""
        mw = TopicValidationMiddleware(registry_with_topics)
        env = Envelope(
            topic="k1.absolutely.unknown",
            envelope_id=99,
            payload=b"x",
        )
        result = mw.process(env)
        assert result is not None

    def test_registry_property(self, registry_with_topics: TopicRegistry) -> None:
        mw = TopicValidationMiddleware(registry_with_topics)
        assert mw.registry is registry_with_topics

    def test_repr(self, registry_with_topics: TopicRegistry) -> None:
        mw = TopicValidationMiddleware(registry_with_topics)
        r = repr(mw)
        assert "TopicValidationMiddleware" in r
        assert "warnings=0" in r


# ---------------------------------------------------------------------------
# Integration: middleware with empty registry
# ---------------------------------------------------------------------------


class TestTopicValidationEmptyRegistry:
    """With an empty registry, all topics are unknown."""

    def test_all_unknown_on_empty(self) -> None:
        reg = TopicRegistry()
        mw = TopicValidationMiddleware(reg)
        env = Envelope(topic="k1.test", envelope_id=1, payload=b"x")
        result = mw.process(env)
        assert result is env  # Still delivered
        assert mw.warning_count == 1
