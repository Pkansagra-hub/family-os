"""Tests for RelevanceFilter (E-MW-1.1).

34 tests across 7 test classes covering R1-R6 rules,
DedupRingBuffer, entity counter-example, and RelevanceFilter integration.
"""

from __future__ import annotations

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.filter.relevance_filter import RelevanceFilter
from k1.memory_writer.filter.rules import (
    DedupRingBuffer,
    check_r1_clarification,
    check_r2_system_meta,
    check_r3_duplicate,
    check_r4_empty,
    check_r5_continuation,
    check_r6_tool_call_boost,
)
from k1.memory_writer.invariants import InvariantViolation
from k1.memory_writer.types import SkipReason

# ===========================================================================
# R4: Empty / Trivial
# ===========================================================================


class TestR4EmptyTrivial:
    def test_single_word_trivial(self):
        assert check_r4_empty("ok", []) == SkipReason.EMPTY

    def test_below_threshold_trivial(self):
        assert check_r4_empty("sure", []) == SkipReason.EMPTY

    def test_above_threshold_passes(self):
        assert check_r4_empty("We went to the park today", []) is None

    def test_entity_overrides_trivial(self):
        assert check_r4_empty("yes", ["Mom"]) is None

    def test_unknown_short_not_trivial(self):
        """Short message not in TRIVIAL_PATTERNS passes."""
        assert check_r4_empty("blue car", []) is None

    def test_punctuation_normalization(self):
        assert check_r4_empty("thanks!", []) == SkipReason.EMPTY


# ===========================================================================
# R5: Continuation
# ===========================================================================


class TestR5Continuation:
    def test_exact_continuation_phrase(self):
        assert check_r5_continuation("go on", []) == SkipReason.TRIVIAL

    def test_continuation_with_entity(self):
        assert check_r5_continuation("tell me more about Mom", ["Mom"]) is None

    def test_over_max_words(self):
        msg = "please go on and tell me even more about this very interesting thing"
        assert check_r5_continuation(msg, []) is None

    def test_case_insensitive(self):
        assert check_r5_continuation("Go On", []) == SkipReason.TRIVIAL

    def test_non_continuation_short(self):
        assert check_r5_continuation("I agree", []) is None


# ===========================================================================
# R6: Tool Call Boost
# ===========================================================================


class TestR6ToolCallBoost:
    def test_tool_call_overrides_trivial(self):
        assert check_r6_tool_call_boost({"tool_calls": [{"name": "search"}]}) is True

    def test_tool_call_overrides_cont(self):
        assert check_r6_tool_call_boost({"tool_calls": [{"name": "calc"}]}) is True

    def test_empty_tool_calls(self):
        assert check_r6_tool_call_boost({"tool_calls": []}) is False

    def test_no_metadata(self):
        assert check_r6_tool_call_boost({}) is False


# ===========================================================================
# R1: Clarification
# ===========================================================================


class TestR1Clarification:
    def test_clarification_with_repair(self):
        result = check_r1_clarification("What do you mean?", "I meant the Italian place", [])
        assert result == SkipReason.CLARIFICATION

    def test_clarification_no_repair(self):
        result = check_r1_clarification("What do you mean?", "The weather is nice", [])
        assert result is None

    def test_repair_without_clarification(self):
        result = check_r1_clarification("Hello", "I meant the Italian place", [])
        assert result is None

    def test_entity_overrides(self):
        result = check_r1_clarification("What do you mean, Mom?", "I meant...", ["Mom"])
        assert result is None

    def test_partial_match(self):
        result = check_r1_clarification("Can you explain the recipe?", "To clarify, use 2 cups", [])
        assert result == SkipReason.CLARIFICATION


# ===========================================================================
# R2: System / Meta
# ===========================================================================


class TestR2SystemMeta:
    def test_tone_change(self):
        assert check_r2_system_meta("Change your tone to formal", []) == SkipReason.SYSTEM_TURN

    def test_capability_query(self):
        assert check_r2_system_meta("What can you do?", []) == SkipReason.SYSTEM_TURN

    def test_entity_overrides(self):
        assert check_r2_system_meta("Help me schedule Mom's appointment", ["Mom"]) is None

    def test_life_question(self):
        assert check_r2_system_meta("How do I make pasta?", []) is None

    def test_stop_pattern(self):
        assert check_r2_system_meta("Stop asking questions", []) == SkipReason.SYSTEM_TURN


# ===========================================================================
# R3: Duplicate
# ===========================================================================


class TestR3Duplicate:
    def test_same_hash_within_window(self):
        ring = DedupRingBuffer(capacity=10)
        r1 = check_r3_duplicate(["Mom"], ["dinner"], 1000, ring, window_ms=300_000)
        assert r1 is None  # first time
        r2 = check_r3_duplicate(["Mom"], ["dinner"], 2000, ring, window_ms=300_000)
        assert r2 == SkipReason.DUPLICATE

    def test_same_hash_outside_window(self):
        ring = DedupRingBuffer(capacity=10)
        check_r3_duplicate(["Mom"], ["dinner"], 1000, ring, window_ms=300_000)
        r2 = check_r3_duplicate(["Mom"], ["dinner"], 500_000, ring, window_ms=300_000)
        assert r2 is None

    def test_different_hash(self):
        ring = DedupRingBuffer(capacity=10)
        check_r3_duplicate(["Mom"], ["dinner"], 1000, ring, window_ms=300_000)
        r2 = check_r3_duplicate(["Dad"], ["lunch"], 2000, ring, window_ms=300_000)
        assert r2 is None

    def test_ring_buffer_capacity(self):
        ring = DedupRingBuffer(capacity=3)
        for i in range(4):
            check_r3_duplicate([f"p{i}"], [f"t{i}"], i * 1000, ring)
        # First entry (p0, t0) evicted — should not be a dup
        r = check_r3_duplicate(["p0"], ["t0"], 5000, ring, window_ms=300_000)
        assert r is None

    def test_clear_on_session_end(self):
        ring = DedupRingBuffer(capacity=10)
        check_r3_duplicate(["Mom"], ["dinner"], 1000, ring)
        ring.clear()
        r = check_r3_duplicate(["Mom"], ["dinner"], 2000, ring, window_ms=300_000)
        assert r is None  # cleared, so not a dup


# ===========================================================================
# RelevanceFilter — Integrated
# ===========================================================================


class TestRelevanceFilterIntegrated:
    def test_full_evaluation_pass(self):
        f = RelevanceFilter(MWConfig())
        decision = f.evaluate(
            user_message="Mom called about dinner tonight",
            assistant_response="That sounds nice!",
            entities=["Mom"],
            topics=["dinner"],
            turn_id="t-001",
            timestamp_ms=1000,
        )
        assert decision.passed is True
        assert decision.skip_reason is None
        assert decision.latency_ms < 5.0

    def test_full_evaluation_skip_trivial(self):
        f = RelevanceFilter(MWConfig())
        decision = f.evaluate(
            user_message="ok",
            assistant_response="Alright.",
            entities=[],
            topics=[],
            turn_id="t-002",
            timestamp_ms=1000,
        )
        assert decision.passed is False
        assert decision.skip_reason == SkipReason.EMPTY

    def test_mw07_enforcement(self):
        with pytest.raises(InvariantViolation, match="MW-07"):
            RelevanceFilter.__new__(RelevanceFilter)
            # Directly test that passing an LLM port key triggers MW-07
            from k1.memory_writer.invariants import assert_mw07_filter_no_llm

            assert_mw07_filter_no_llm({"model_hub": object()})

    def test_tool_call_boost_in_full_filter(self):
        """Tool call metadata causes auto-PASS even for trivial message."""
        f = RelevanceFilter(MWConfig())
        decision = f.evaluate(
            user_message="ok",
            assistant_response="Done.",
            entities=[],
            topics=[],
            turn_id="t-003",
            timestamp_ms=1000,
            turn_metadata={"tool_calls": [{"name": "search_restaurants"}]},
        )
        assert decision.passed is True
