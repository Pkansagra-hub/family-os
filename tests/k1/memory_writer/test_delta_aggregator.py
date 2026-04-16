"""Tests for DeltaAggregator (E-MW-3.3).

20 tests in 5 classes covering:
  - Add: single, multiple, dedup, different topics/participants
  - Flush: returns all, clears pending, clears hashes, empty, causal sort
  - Dedup: deterministic hash, ignores text, case-sensitive, empty fields
  - Config: MW-08 valid/invalid window, window_ms property
  - Concurrency: separate instances, add-flush cycle, pending_count
"""

from __future__ import annotations

import pytest

from k1.memory_writer.batch.delta_aggregator import DeltaAggregator
from k1.memory_writer.config import MWConfig
from k1.memory_writer.invariants import InvariantViolation

# ===========================================================================
# Helpers
# ===========================================================================


def _cfg(**overrides: object) -> MWConfig:
    defaults: dict = {"batch_window_ms": 250, "max_batch_size": 10}
    defaults.update(overrides)
    return MWConfig(**defaults)


def _envelope(
    participants: list[str] | None = None,
    topics: list[str] | None = None,
    text: str = "some text",
    turn: int = 1,
    seq: int = 0,
) -> dict:
    return {
        "body": {
            "participants": participants or ["person_mom"],
            "topics": topics or ["dinner"],
            "text": text,
            "conversation_turn": turn,
            "extraction_sequence": seq,
        }
    }


# ===========================================================================
# Tests
# ===========================================================================


class TestDeltaAggregatorAdd:
    """add() — single, multiple, dedup logic."""

    def test_add_single_envelope(self) -> None:
        agg = DeltaAggregator(_cfg())
        result = agg.add(_envelope())
        assert result is True
        assert agg.pending_count == 1

    def test_add_multiple_envelopes(self) -> None:
        agg = DeltaAggregator(_cfg())
        assert agg.add(_envelope(participants=["a"], topics=["x"])) is True
        assert agg.add(_envelope(participants=["b"], topics=["y"])) is True
        assert agg.add(_envelope(participants=["c"], topics=["z"])) is True
        assert agg.pending_count == 3

    def test_dedup_same_participants_topics(self) -> None:
        agg = DeltaAggregator(_cfg())
        assert agg.add(_envelope(participants=["person_mom"], topics=["dinner"])) is True
        assert agg.add(_envelope(participants=["person_mom"], topics=["dinner"])) is False
        assert agg.pending_count == 1

    def test_different_topics_not_deduped(self) -> None:
        agg = DeltaAggregator(_cfg())
        assert agg.add(_envelope(participants=["person_mom"], topics=["dinner"])) is True
        assert agg.add(_envelope(participants=["person_mom"], topics=["lunch"])) is True
        assert agg.pending_count == 2

    def test_different_participants_not_deduped(self) -> None:
        agg = DeltaAggregator(_cfg())
        assert agg.add(_envelope(participants=["person_mom"], topics=["dinner"])) is True
        assert agg.add(_envelope(participants=["person_dad"], topics=["dinner"])) is True
        assert agg.pending_count == 2


class TestDeltaAggregatorFlush:
    """flush() — returns all, clears state, causal sort."""

    def test_flush_returns_all_pending(self) -> None:
        agg = DeltaAggregator(_cfg())
        agg.add(_envelope(participants=["a"], topics=["x"]))
        agg.add(_envelope(participants=["b"], topics=["y"]))
        agg.add(_envelope(participants=["c"], topics=["z"]))
        batch = agg.flush()
        assert len(batch) == 3

    def test_flush_clears_pending(self) -> None:
        agg = DeltaAggregator(_cfg())
        agg.add(_envelope())
        agg.flush()
        assert agg.pending_count == 0

    def test_flush_clears_seen_hashes(self) -> None:
        agg = DeltaAggregator(_cfg())
        env = _envelope()
        agg.add(env)
        agg.flush()
        # Same envelope should now be accepted again
        assert agg.add(env) is True

    def test_flush_empty_returns_empty(self) -> None:
        agg = DeltaAggregator(_cfg())
        assert agg.flush() == []

    def test_flush_sorts_by_turn_then_sequence(self) -> None:
        agg = DeltaAggregator(_cfg())
        agg.add(_envelope(participants=["a"], topics=["x"], turn=5, seq=1))
        agg.add(_envelope(participants=["b"], topics=["y"], turn=3, seq=0))
        agg.add(_envelope(participants=["c"], topics=["z"], turn=3, seq=2))
        batch = agg.flush()
        turns = [(e["body"]["conversation_turn"], e["body"]["extraction_sequence"]) for e in batch]
        assert turns == [(3, 0), (3, 2), (5, 1)]


class TestDeltaAggregatorDedup:
    """Dedup hash behavior."""

    def test_dedup_hash_deterministic(self) -> None:
        env = _envelope(participants=["person_mom"], topics=["dinner"])
        h1 = DeltaAggregator._compute_hash(env)
        h2 = DeltaAggregator._compute_hash(env)
        assert h1 == h2

    def test_dedup_ignores_body_text(self) -> None:
        env1 = _envelope(participants=["person_mom"], topics=["dinner"], text="text A")
        env2 = _envelope(participants=["person_mom"], topics=["dinner"], text="text B")
        assert DeltaAggregator._compute_hash(env1) == DeltaAggregator._compute_hash(env2)

    def test_dedup_is_case_sensitive(self) -> None:
        env1 = _envelope(participants=["person_mom"], topics=["dinner"])
        env2 = _envelope(participants=["PERSON_MOM"], topics=["dinner"])
        assert DeltaAggregator._compute_hash(env1) != DeltaAggregator._compute_hash(env2)

    def test_dedup_empty_participants_topics(self) -> None:
        env = _envelope(participants=[], topics=[])
        h = DeltaAggregator._compute_hash(env)
        assert isinstance(h, str)
        assert len(h) == 16


class TestDeltaAggregatorConfig:
    """MW-08 batch window validation."""

    def test_mw08_valid_window(self) -> None:
        agg = DeltaAggregator(_cfg(batch_window_ms=250))
        assert agg.window_ms == 250

    def test_mw08_zero_window_raises(self) -> None:
        with pytest.raises(InvariantViolation, match="MW-08"):
            DeltaAggregator(_cfg(batch_window_ms=0))

    def test_window_ms_property(self) -> None:
        agg = DeltaAggregator(_cfg(batch_window_ms=500))
        assert agg.window_ms == 500


class TestDeltaAggregatorConcurrency:
    """Separate instances, add-flush cycles."""

    def test_separate_instances_no_shared_state(self) -> None:
        a = DeltaAggregator(_cfg())
        b = DeltaAggregator(_cfg())
        a.add(_envelope(participants=["a"], topics=["x"]))
        assert a.pending_count == 1
        assert b.pending_count == 0

    def test_concurrent_add_flush_cycle(self) -> None:
        agg = DeltaAggregator(_cfg())
        agg.add(_envelope(participants=["a"], topics=["x"]))
        agg.add(_envelope(participants=["b"], topics=["y"]))
        agg.add(_envelope(participants=["c"], topics=["z"]))
        batch1 = agg.flush()
        assert len(batch1) == 3

        agg.add(_envelope(participants=["d"], topics=["w"]))
        agg.add(_envelope(participants=["e"], topics=["v"]))
        batch2 = agg.flush()
        assert len(batch2) == 2

    def test_pending_count_tracks_correctly(self) -> None:
        agg = DeltaAggregator(_cfg())
        agg.add(_envelope(participants=["a"], topics=["x"]))
        agg.add(_envelope(participants=["b"], topics=["y"]))
        agg.add(_envelope(participants=["a"], topics=["x"]))  # dedup
        assert agg.pending_count == 2
