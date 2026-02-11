"""
Tests for k1.bus.impl.topic_trie -- Radix trie for topic matching.

Coverage targets:
    - Exact match (single handler, multiple handlers)
    - Single wildcard (*) at various positions
    - Greedy wildcard (>) matches trailing segments
    - No match returns empty list
    - Overlapping patterns (exact + wildcard on same topic)
    - Remove by subscription_id
    - Remove unknown subscription_id returns False
    - Double remove returns False
    - Clear empties everything
    - Validation: empty pattern, empty segment, > not last
    - Size tracking
    - Compaction after tombstones
"""

import pytest

from k1.bus.impl.topic_trie import TopicTrie

# ===================================================================
# Helpers
# ===================================================================


def _h(name: str):
    """Create a named handler for identification in assertions."""

    def handler(env):
        pass

    handler.__qualname__ = name
    handler._name = name
    return handler


# ===================================================================
# Exact matching
# ===================================================================


class TestExactMatch:
    """Exact topic matching (no wildcards)."""

    def test_single_handler(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("k1.capability.completed.v1", h, "sub-1")
        result = trie.match("k1.capability.completed.v1")
        assert result == [h]

    def test_no_match(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.capability.completed.v1", _h("h1"), "sub-1")
        assert trie.match("k1.capability.failed.v1") == []

    def test_multiple_handlers_same_pattern(self) -> None:
        trie: TopicTrie = TopicTrie()
        h1, h2 = _h("h1"), _h("h2")
        trie.insert("k1.test.event", h1, "sub-1")
        trie.insert("k1.test.event", h2, "sub-2")
        result = trie.match("k1.test.event")
        assert result == [h1, h2]

    def test_different_topics_dont_cross(self) -> None:
        trie: TopicTrie = TopicTrie()
        h1, h2 = _h("h1"), _h("h2")
        trie.insert("k1.topic.a", h1, "sub-1")
        trie.insert("k1.topic.b", h2, "sub-2")
        assert trie.match("k1.topic.a") == [h1]
        assert trie.match("k1.topic.b") == [h2]

    def test_prefix_doesnt_match_longer(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.test", _h("h1"), "sub-1")
        assert trie.match("k1.test.deeper") == []

    def test_longer_doesnt_match_prefix(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.test.deeper", _h("h1"), "sub-1")
        assert trie.match("k1.test") == []

    def test_single_segment_topic(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("heartbeat", h, "sub-1")
        assert trie.match("heartbeat") == [h]
        assert trie.match("heartbeat.sub") == []

    def test_empty_topic_no_match(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.test", _h("h1"), "sub-1")
        assert trie.match("") == []


# ===================================================================
# Single wildcard (*) matching
# ===================================================================


class TestSingleWildcard:
    """Single wildcard (*) matches exactly one segment."""

    def test_wildcard_middle(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("k1.agent.*.delta.v1", h, "sub-1")
        assert trie.match("k1.agent.abc.delta.v1") == [h]
        assert trie.match("k1.agent.xyz.delta.v1") == [h]

    def test_wildcard_doesnt_match_multiple_segments(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.agent.*.delta.v1", _h("h1"), "sub-1")
        assert trie.match("k1.agent.abc.def.delta.v1") == []

    def test_wildcard_at_end(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("k1.capability.*", h, "sub-1")
        assert trie.match("k1.capability.completed") == [h]
        assert trie.match("k1.capability.failed") == [h]

    def test_wildcard_at_start(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("*.capability.completed", h, "sub-1")
        assert trie.match("k1.capability.completed") == [h]
        assert trie.match("k2.capability.completed") == [h]

    def test_multiple_wildcards(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("k1.*.*.v1", h, "sub-1")
        assert trie.match("k1.agent.delta.v1") == [h]
        assert trie.match("k1.foo.bar.v1") == [h]
        assert trie.match("k1.foo.bar.v2") == []

    def test_wildcard_only(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("*", h, "sub-1")
        assert trie.match("anything") == [h]
        assert trie.match("k1") == [h]
        # But * is exactly one segment, not zero
        assert trie.match("two.segments") == []


# ===================================================================
# Greedy wildcard (>) matching
# ===================================================================


class TestGreedyWildcard:
    """Greedy wildcard (>) matches one or more trailing segments."""

    def test_greedy_basic(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("k1.agent.>", h, "sub-1")
        assert trie.match("k1.agent.abc") == [h]
        assert trie.match("k1.agent.abc.delta") == [h]
        assert trie.match("k1.agent.abc.delta.v1") == [h]

    def test_greedy_doesnt_match_exact_prefix(self) -> None:
        """'>' requires at least one more segment beyond the prefix."""
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.agent.>", _h("h1"), "sub-1")
        # "k1.agent" has no segment after "agent" for > to match
        assert trie.match("k1.agent") == []

    def test_greedy_at_root(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert(">", h, "sub-1")
        assert trie.match("anything") == [h]
        assert trie.match("k1.deep.topic") == [h]

    def test_greedy_with_single_wildcard_before(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("k1.*.>", h, "sub-1")
        assert trie.match("k1.agent.delta") == [h]
        assert trie.match("k1.session.update.v1") == [h]
        assert trie.match("k1.agent") == []  # > needs >=1 seg


# ===================================================================
# Overlapping patterns
# ===================================================================


class TestOverlappingPatterns:
    """Multiple patterns that match the same topic."""

    def test_exact_and_wildcard_both_match(self) -> None:
        trie: TopicTrie = TopicTrie()
        h_exact, h_wild = _h("exact"), _h("wild")
        trie.insert("k1.capability.completed.v1", h_exact, "sub-1")
        trie.insert("k1.capability.*.v1", h_wild, "sub-2")
        result = trie.match("k1.capability.completed.v1")
        assert h_exact in result
        assert h_wild in result
        assert len(result) == 2

    def test_exact_and_greedy_both_match(self) -> None:
        trie: TopicTrie = TopicTrie()
        h_exact, h_greedy = _h("exact"), _h("greedy")
        trie.insert("k1.agent.abc.delta.v1", h_exact, "sub-1")
        trie.insert("k1.agent.>", h_greedy, "sub-2")
        result = trie.match("k1.agent.abc.delta.v1")
        assert h_exact in result
        assert h_greedy in result

    def test_wildcard_and_greedy_both_match(self) -> None:
        trie: TopicTrie = TopicTrie()
        h_wild, h_greedy = _h("wild"), _h("greedy")
        trie.insert("k1.agent.*.delta.v1", h_wild, "sub-1")
        trie.insert("k1.agent.>", h_greedy, "sub-2")
        result = trie.match("k1.agent.abc.delta.v1")
        assert h_wild in result
        assert h_greedy in result

    def test_triple_overlap(self) -> None:
        trie: TopicTrie = TopicTrie()
        h1, h2, h3 = _h("exact"), _h("wild"), _h("greedy")
        trie.insert("k1.a.b.c", h1, "sub-1")
        trie.insert("k1.a.*.c", h2, "sub-2")
        trie.insert("k1.a.>", h3, "sub-3")
        result = trie.match("k1.a.b.c")
        assert len(result) == 3


# ===================================================================
# Remove
# ===================================================================


class TestRemove:
    """Subscription removal by ID."""

    def test_remove_existing(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("h1")
        trie.insert("k1.test", h, "sub-1")
        assert trie.match("k1.test") == [h]
        assert trie.remove("sub-1") is True
        assert trie.match("k1.test") == []

    def test_remove_unknown_returns_false(self) -> None:
        trie: TopicTrie = TopicTrie()
        assert trie.remove("nonexistent") is False

    def test_double_remove_returns_false(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.test", _h("h1"), "sub-1")
        assert trie.remove("sub-1") is True
        assert trie.remove("sub-1") is False

    def test_remove_one_of_many(self) -> None:
        trie: TopicTrie = TopicTrie()
        h1, h2, h3 = _h("h1"), _h("h2"), _h("h3")
        trie.insert("k1.test", h1, "sub-1")
        trie.insert("k1.test", h2, "sub-2")
        trie.insert("k1.test", h3, "sub-3")
        trie.remove("sub-2")
        result = trie.match("k1.test")
        assert h1 in result
        assert h2 not in result
        assert h3 in result

    def test_remove_updates_size(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.a", _h("h1"), "sub-1")
        trie.insert("k1.b", _h("h2"), "sub-2")
        assert trie.size == 2
        trie.remove("sub-1")
        assert trie.size == 1


# ===================================================================
# Validation
# ===================================================================


class TestValidation:
    """Pattern validation on insert."""

    def test_empty_pattern_rejected(self) -> None:
        trie: TopicTrie = TopicTrie()
        with pytest.raises(ValueError, match="must not be empty"):
            trie.insert("", _h("h1"), "sub-1")

    def test_empty_segment_rejected(self) -> None:
        trie: TopicTrie = TopicTrie()
        with pytest.raises(ValueError, match="empty segment"):
            trie.insert("k1..test", _h("h1"), "sub-1")

    def test_greedy_not_last_rejected(self) -> None:
        trie: TopicTrie = TopicTrie()
        with pytest.raises(ValueError, match="must be the last segment"):
            trie.insert("k1.>.test", _h("h1"), "sub-1")

    def test_greedy_last_accepted(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("k1.test.>", _h("h1"), "sub-1")
        assert trie.size == 1


# ===================================================================
# Size and clear
# ===================================================================


class TestSizeAndClear:
    """Size tracking and clear."""

    def test_empty_size(self) -> None:
        trie: TopicTrie = TopicTrie()
        assert trie.size == 0
        assert len(trie) == 0

    def test_size_after_inserts(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("a", _h("h1"), "s1")
        trie.insert("b", _h("h2"), "s2")
        trie.insert("c", _h("h3"), "s3")
        assert trie.size == 3

    def test_clear(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("a", _h("h1"), "s1")
        trie.insert("b", _h("h2"), "s2")
        trie.clear()
        assert trie.size == 0
        assert trie.match("a") == []
        assert trie.match("b") == []

    def test_repr(self) -> None:
        trie: TopicTrie = TopicTrie()
        trie.insert("a", _h("h1"), "s1")
        assert "subscriptions=1" in repr(trie)


# ===================================================================
# Compaction
# ===================================================================


class TestCompaction:
    """Tombstone compaction after removals."""

    def test_compaction_after_heavy_removal(self) -> None:
        """Insert many, remove most, verify remaining still match."""
        trie: TopicTrie = TopicTrie()
        handlers = [_h(f"h{i}") for i in range(10)]
        for i, h in enumerate(handlers):
            trie.insert("k1.test.topic", h, f"sub-{i}")

        # Remove 8 of 10 (>50% tombstones triggers compaction)
        for i in range(8):
            trie.remove(f"sub-{i}")

        result = trie.match("k1.test.topic")
        assert len(result) == 2
        assert handlers[8] in result
        assert handlers[9] in result
        assert trie.size == 2


# ===================================================================
# Real-world K1 topic patterns
# ===================================================================


class TestRealWorldPatterns:
    """Tests using actual K1 topic patterns from K1_FLOWS.md."""

    def test_capability_lifecycle(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("cap_handler")
        trie.insert("k1.capability.>", h, "sub-1")
        assert trie.match("k1.capability.completed.v1") == [h]
        assert trie.match("k1.capability.invoked.v1") == [h]
        assert trie.match("k1.capability.failed.v1") == [h]
        assert trie.match("k1.orchestration.started") == []

    def test_agent_delta_pattern(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("delta_handler")
        trie.insert("k1.agent.*.delta.v1", h, "sub-1")
        assert trie.match("k1.agent.planner-001.delta.v1") == [h]
        assert trie.match("k1.agent.search-002.delta.v1") == [h]
        assert trie.match("k1.agent.planner-001.status.v1") == []

    def test_session_events(self) -> None:
        trie: TopicTrie = TopicTrie()
        h_all = _h("session_all")
        h_update = _h("session_update")
        trie.insert("k1.session.>", h_all, "sub-1")
        trie.insert("k1.session.update.v1", h_update, "sub-2")
        result = trie.match("k1.session.update.v1")
        assert h_all in result
        assert h_update in result
        assert trie.match("k1.session.created.v1") == [h_all]

    def test_k0_bridge_sse(self) -> None:
        trie: TopicTrie = TopicTrie()
        h = _h("sse_handler")
        trie.insert("k1.k0.sse.>", h, "sub-1")
        assert trie.match("k1.k0.sse.emotion.update") == [h]
        assert trie.match("k1.k0.sse.memory.consolidated") == [h]
        assert trie.match("k1.k0.rpc.query") == []
