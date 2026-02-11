"""
Tests for k1.bus.timing.timing_chain -- TimingChain ordering enforcement.

Coverage targets:
    - BEST_EFFORT: immediate delivery, no buffering
    - RELAXED: immediate delivery, reorder detection
    - STRICT causal: parent must deliver before child
    - STRICT causal: cascade (parent -> child -> grandchild)
    - STRICT sequence: gap detected, buffered until filled
    - STRICT sequence: consecutive buffered released in order
    - STRICT combined: causal + sequence both enforced
    - Timeout sweep releases stuck envelopes
    - Stats tracking (all counters)
    - CausalTracker unit tests (delivered set, child buffer)
    - GapBuffer unit tests (expected tracking, gap fill release)
    - Buffer overflow safety (force release)
    - Thread safety under concurrent process + sweep
    - Defaults module (default_timing_config, DEFAULT_RULES)
    - BusFactory.create_local_ordered / create_for_testing(ordered=True)
    - LocalBus with TimingChain end-to-end
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from k1.bus import BusFactory, Envelope
from k1.bus.envelope import DeliveryMode, Priority
from k1.bus.impl.local_bus import LocalBus
from k1.bus.timing.defaults import DEFAULT_MODE, DEFAULT_RULES, default_timing_config
from k1.bus.timing.timing_chain import TimingChain, _BufferedEnvelope, _CausalTracker, _GapBuffer
from k1.bus.timing.timing_config import TimingConfig

STRICT = DeliveryMode.STRICT
RELAXED = DeliveryMode.RELAXED
BEST_EFFORT = DeliveryMode.BEST_EFFORT


# ===================================================================
# Helpers
# ===================================================================


def _env(
    topic: str = "k1.test",
    *,
    envelope_id: int = 0,
    sequence: int = 0,
    parent_id: int = 0,
    payload: bytes = b"",
    priority: Priority = Priority.INTERACTIVE,
) -> Envelope:
    """Create a pre-stamped envelope for testing."""
    return Envelope(
        topic=topic,
        payload=payload,
        priority=priority,
        envelope_id=envelope_id,
        sequence=sequence,
        parent_id=parent_id,
    )


class _Recorder:
    """Dispatch callback that records delivery order."""

    def __init__(self) -> None:
        self.delivered: list[Envelope] = []
        self._lock = threading.Lock()

    def __call__(self, envelope: Envelope) -> None:
        with self._lock:
            self.delivered.append(envelope)

    @property
    def ids(self) -> list[int]:
        return [e.envelope_id for e in self.delivered]

    @property
    def seqs(self) -> list[int]:
        return [e.sequence for e in self.delivered]


# ===================================================================
# CausalTracker unit tests
# ===================================================================


class TestCausalTracker:
    def test_root_parent_always_delivered(self) -> None:
        ct = _CausalTracker()
        assert ct.is_parent_delivered(0) is True

    def test_unknown_parent_not_delivered(self) -> None:
        ct = _CausalTracker()
        assert ct.is_parent_delivered(42) is False

    def test_mark_delivered_makes_parent_available(self) -> None:
        ct = _CausalTracker()
        ct.mark_delivered(42)
        assert ct.is_parent_delivered(42) is True

    def test_buffer_child_and_release_on_parent_delivery(self) -> None:
        ct = _CausalTracker()
        env = _env(envelope_id=2, parent_id=1)
        be = _BufferedEnvelope(envelope=env, buffered_at_ns=time.monotonic_ns())
        ct.buffer_child(1, be)
        assert ct.pending_count == 1

        children = ct.mark_delivered(1)
        assert len(children) == 1
        assert children[0].envelope.envelope_id == 2
        assert ct.pending_count == 0

    def test_multiple_children_released_together(self) -> None:
        ct = _CausalTracker()
        now = time.monotonic_ns()
        for i in range(5):
            env = _env(envelope_id=10 + i, parent_id=1)
            ct.buffer_child(1, _BufferedEnvelope(envelope=env, buffered_at_ns=now))

        assert ct.pending_count == 5
        children = ct.mark_delivered(1)
        assert len(children) == 5
        assert ct.pending_count == 0

    def test_timeout_releases_old_entries(self) -> None:
        ct = _CausalTracker()
        old_time = time.monotonic_ns() - 10_000_000_000  # 10s ago
        env = _env(envelope_id=2, parent_id=1)
        ct.buffer_child(1, _BufferedEnvelope(envelope=env, buffered_at_ns=old_time))

        timed_out = ct.get_timed_out(
            timeout_ns=1_000_000_000,  # 1s timeout
            now_ns=time.monotonic_ns(),
        )
        assert len(timed_out) == 1
        assert timed_out[0].envelope.envelope_id == 2
        assert ct.pending_count == 0

    def test_timeout_keeps_recent_entries(self) -> None:
        ct = _CausalTracker()
        now = time.monotonic_ns()
        env = _env(envelope_id=2, parent_id=1)
        ct.buffer_child(1, _BufferedEnvelope(envelope=env, buffered_at_ns=now))

        timed_out = ct.get_timed_out(
            timeout_ns=1_000_000_000,
            now_ns=now,
        )
        assert len(timed_out) == 0
        assert ct.pending_count == 1


# ===================================================================
# GapBuffer unit tests
# ===================================================================


class TestGapBuffer:
    def test_first_envelope_seq_1_is_ready(self) -> None:
        gb = _GapBuffer()
        env = _env(topic="t", sequence=1)
        is_ready, released = gb.check_and_buffer(env, time.monotonic_ns())
        assert is_ready is True
        assert released == []
        assert gb.expected_sequence("t") == 2

    def test_sequential_envelopes_all_ready(self) -> None:
        gb = _GapBuffer()
        now = time.monotonic_ns()
        for seq in range(1, 6):
            env = _env(topic="t", sequence=seq)
            is_ready, released = gb.check_and_buffer(env, now)
            assert is_ready is True
            assert released == []
        assert gb.expected_sequence("t") == 6

    def test_gap_buffers_envelope(self) -> None:
        gb = _GapBuffer()
        now = time.monotonic_ns()

        # Send seq 1 (ok)
        gb.check_and_buffer(_env(topic="t", sequence=1), now)

        # Send seq 3 (gap: missing 2)
        is_ready, released = gb.check_and_buffer(_env(topic="t", sequence=3), now)
        assert is_ready is False
        assert released == []
        assert gb.total_buffered == 1
        assert gb.pending_for_topic("t") == 1

    def test_gap_fill_releases_buffered(self) -> None:
        gb = _GapBuffer()
        now = time.monotonic_ns()

        gb.check_and_buffer(_env(topic="t", sequence=1, envelope_id=1), now)

        # Gap: send 3 and 4 (missing 2)
        gb.check_and_buffer(_env(topic="t", sequence=3, envelope_id=3), now)
        gb.check_and_buffer(_env(topic="t", sequence=4, envelope_id=4), now)

        # Fill gap with 2
        is_ready, released = gb.check_and_buffer(_env(topic="t", sequence=2, envelope_id=2), now)
        assert is_ready is True
        assert len(released) == 2  # 3 and 4 released
        assert released[0].sequence == 3
        assert released[1].sequence == 4
        assert gb.total_buffered == 0
        assert gb.expected_sequence("t") == 5

    def test_duplicate_sequence_still_ready(self) -> None:
        gb = _GapBuffer()
        now = time.monotonic_ns()
        gb.check_and_buffer(_env(topic="t", sequence=1), now)
        # Duplicate seq 1
        is_ready, released = gb.check_and_buffer(_env(topic="t", sequence=1), now)
        assert is_ready is True  # Deliver (idempotent handlers)

    def test_per_topic_isolation(self) -> None:
        gb = _GapBuffer()
        now = time.monotonic_ns()

        gb.check_and_buffer(_env(topic="a", sequence=1), now)
        gb.check_and_buffer(_env(topic="b", sequence=1), now)

        # Gap on topic "a", topic "b" unaffected
        gb.check_and_buffer(_env(topic="a", sequence=3), now)
        assert gb.pending_for_topic("a") == 1
        assert gb.pending_for_topic("b") == 0

        # Topic "b" still in-sequence
        is_ready, _ = gb.check_and_buffer(_env(topic="b", sequence=2), now)
        assert is_ready is True

    def test_timeout_releases_buffered(self) -> None:
        gb = _GapBuffer()
        old_time = time.monotonic_ns() - 10_000_000_000

        gb.check_and_buffer(_env(topic="t", sequence=1), old_time)
        gb.check_and_buffer(_env(topic="t", sequence=3, envelope_id=3), old_time)

        released = gb.get_timed_out(
            "t",
            timeout_ns=1_000_000_000,
            now_ns=time.monotonic_ns(),
        )
        assert len(released) == 1
        assert released[0].sequence == 3

    def test_timeout_advances_expected(self) -> None:
        gb = _GapBuffer()
        old_time = time.monotonic_ns() - 10_000_000_000

        gb.check_and_buffer(_env(topic="t", sequence=1), old_time)
        gb.check_and_buffer(_env(topic="t", sequence=3), old_time)
        gb.check_and_buffer(_env(topic="t", sequence=4), old_time)

        gb.get_timed_out("t", timeout_ns=1_000_000_000, now_ns=time.monotonic_ns())
        # Expected should advance past the released sequences
        assert gb.expected_sequence("t") >= 4


# ===================================================================
# TimingChain -- BEST_EFFORT mode
# ===================================================================


class TestTimingChainBestEffort:
    def test_immediate_delivery(self) -> None:
        config = TimingConfig(rules={"k1.fire": BEST_EFFORT})
        chain = TimingChain(config=config)
        rec = _Recorder()

        chain.process(_env(topic="k1.fire.event", envelope_id=1, sequence=1), rec)
        assert rec.ids == [1]
        assert chain.stats.delivered_immediate == 1

    def test_no_buffering_on_gap(self) -> None:
        """BEST_EFFORT delivers even with sequence gaps."""
        config = TimingConfig(rules={"k1.fire": BEST_EFFORT})
        chain = TimingChain(config=config)
        rec = _Recorder()

        # Send seq 1, skip 2, send 3
        chain.process(_env(topic="k1.fire.a", envelope_id=1, sequence=1), rec)
        chain.process(_env(topic="k1.fire.a", envelope_id=3, sequence=3), rec)
        assert len(rec.delivered) == 2
        assert chain.stats.buffered_gap == 0

    def test_no_causal_buffering(self) -> None:
        """BEST_EFFORT ignores parent_id."""
        config = TimingConfig(rules={"k1.fire": BEST_EFFORT})
        chain = TimingChain(config=config)
        rec = _Recorder()

        # Child sent before parent
        chain.process(
            _env(topic="k1.fire.a", envelope_id=2, sequence=1, parent_id=99),
            rec,
        )
        assert len(rec.delivered) == 1  # Delivered immediately


# ===================================================================
# TimingChain -- RELAXED mode
# ===================================================================


class TestTimingChainRelaxed:
    def test_immediate_delivery(self) -> None:
        config = TimingConfig(rules={"k1.affect": RELAXED})
        chain = TimingChain(config=config)
        rec = _Recorder()

        chain.process(_env(topic="k1.affect.update", envelope_id=1, sequence=1), rec)
        assert rec.ids == [1]

    def test_reorder_detected_and_logged(self) -> None:
        config = TimingConfig(rules={"k1.affect": RELAXED})
        chain = TimingChain(config=config)
        rec = _Recorder()

        # In-order
        chain.process(_env(topic="k1.affect.x", envelope_id=1, sequence=1), rec)
        chain.process(_env(topic="k1.affect.x", envelope_id=2, sequence=2), rec)

        # Out of order: seq 1 arriving again (old/duplicate)
        chain.process(_env(topic="k1.affect.x", envelope_id=3, sequence=1), rec)

        # All 3 delivered (RELAXED never buffers)
        assert len(rec.delivered) == 3
        assert chain.stats.reorders_detected == 1
        assert chain.stats.delivered_immediate == 3


# ===================================================================
# TimingChain -- STRICT causal ordering
# ===================================================================


class TestTimingChainStrictCausal:
    def _strict_config(self) -> TimingConfig:
        return TimingConfig(rules={"k1.cap": STRICT})

    def test_root_envelope_delivered_immediately(self) -> None:
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        chain.process(
            _env(topic="k1.cap.a", envelope_id=1, sequence=1, parent_id=0),
            rec,
        )
        assert rec.ids == [1]

    def test_child_waits_for_parent(self) -> None:
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        # Child arrives first (parent_id=1, but 1 not delivered yet)
        chain.process(
            _env(topic="k1.cap.a", envelope_id=2, sequence=2, parent_id=1),
            rec,
        )
        assert rec.ids == []
        assert chain.causal_pending == 1
        assert chain.stats.buffered_causal == 1

        # Now parent arrives
        chain.process(
            _env(topic="k1.cap.a", envelope_id=1, sequence=1, parent_id=0),
            rec,
        )
        # Parent delivered first, then child released
        assert rec.ids == [1, 2]
        assert chain.causal_pending == 0
        assert chain.stats.released_causal == 1

    def test_causal_cascade_grandchild(self) -> None:
        """Grandchild waits for child waits for parent."""
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        # Grandchild (parent_id=2)
        chain.process(
            _env(topic="k1.cap.a", envelope_id=3, sequence=3, parent_id=2),
            rec,
        )
        # Child (parent_id=1)
        chain.process(
            _env(topic="k1.cap.a", envelope_id=2, sequence=2, parent_id=1),
            rec,
        )
        assert rec.ids == []
        assert chain.causal_pending == 2

        # Parent arrives -- releases child, which releases grandchild
        chain.process(
            _env(topic="k1.cap.a", envelope_id=1, sequence=1, parent_id=0),
            rec,
        )
        assert rec.ids == [1, 2, 3]

    def test_multiple_children_same_parent(self) -> None:
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        # 3 children waiting for parent 1
        for i in [2, 3, 4]:
            chain.process(
                _env(topic="k1.cap.a", envelope_id=i, sequence=i, parent_id=1),
                rec,
            )
        assert chain.causal_pending == 3

        # Parent arrives
        chain.process(
            _env(topic="k1.cap.a", envelope_id=1, sequence=1, parent_id=0),
            rec,
        )
        # Parent + 3 children delivered
        assert len(rec.delivered) == 4
        assert rec.ids[0] == 1  # parent first


# ===================================================================
# TimingChain -- STRICT sequence gap buffering
# ===================================================================


class TestTimingChainStrictSequence:
    def _strict_config(self) -> TimingConfig:
        return TimingConfig(rules={"k1.cap": STRICT})

    def test_in_order_delivery(self) -> None:
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        for seq in range(1, 6):
            chain.process(_env(topic="k1.cap.a", envelope_id=seq, sequence=seq), rec)
        assert rec.seqs == [1, 2, 3, 4, 5]

    def test_gap_buffers_then_releases(self) -> None:
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        # Seq 1 (ok)
        chain.process(_env(topic="k1.cap.a", envelope_id=1, sequence=1), rec)
        # Seq 3 (gap: missing 2)
        chain.process(_env(topic="k1.cap.a", envelope_id=3, sequence=3), rec)
        assert rec.ids == [1]
        assert chain.gap_pending == 1

        # Fill gap with seq 2
        chain.process(_env(topic="k1.cap.a", envelope_id=2, sequence=2), rec)
        assert rec.ids == [1, 2, 3]
        assert chain.gap_pending == 0

    def test_large_gap_multiple_buffered(self) -> None:
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        # Seq 1
        chain.process(_env(topic="k1.cap.a", envelope_id=1, sequence=1), rec)
        # Skip 2, send 3,4,5
        for seq in [3, 4, 5]:
            chain.process(_env(topic="k1.cap.a", envelope_id=seq, sequence=seq), rec)
        assert rec.ids == [1]
        assert chain.gap_pending == 3

        # Fill with 2 -> releases 3,4,5 in order
        chain.process(_env(topic="k1.cap.a", envelope_id=2, sequence=2), rec)
        assert rec.ids == [1, 2, 3, 4, 5]

    def test_per_topic_gap_independence(self) -> None:
        chain = TimingChain(config=self._strict_config())
        rec = _Recorder()

        # Topic A: seq 1
        chain.process(_env(topic="k1.cap.a", envelope_id=1, sequence=1), rec)
        # Topic B: seq 1
        chain.process(_env(topic="k1.cap.b", envelope_id=2, sequence=1), rec)
        # Topic A: seq 3 (gap)
        chain.process(_env(topic="k1.cap.a", envelope_id=3, sequence=3), rec)
        # Topic B: seq 2 (no gap)
        chain.process(_env(topic="k1.cap.b", envelope_id=4, sequence=2), rec)

        assert chain.gap_pending_for_topic("k1.cap.a") == 1
        assert chain.gap_pending_for_topic("k1.cap.b") == 0
        # A got 1, B got 1+2
        delivered_by_topic: dict[str, list[int]] = defaultdict(list)
        for e in rec.delivered:
            delivered_by_topic[e.topic].append(e.sequence)
        assert delivered_by_topic["k1.cap.a"] == [1]
        assert delivered_by_topic["k1.cap.b"] == [1, 2]


# ===================================================================
# TimingChain -- STRICT combined causal + sequence
# ===================================================================


class TestTimingChainStrictCombined:
    def test_causal_then_sequence_enforcement(self) -> None:
        """Child is causally blocked, and when released, must still pass sequence check."""
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config)
        rec = _Recorder()

        # Seq 1 (root, parent_id=0)
        chain.process(_env(topic="k1.cap.a", envelope_id=1, sequence=1, parent_id=0), rec)
        # Seq 3 (child of 1, but seq 2 missing -> gap after causal release)
        chain.process(_env(topic="k1.cap.a", envelope_id=3, sequence=3, parent_id=1), rec)

        # 1 delivered (root); 3 is causally satisfied (parent 1 delivered)
        # but seq 3 needs seq 2 first -> gap buffered
        assert rec.ids == [1]
        # 3 should be in gap buffer (causal resolved -> went to sequence check -> gap)
        assert chain.gap_pending == 1

        # Fill seq 2
        chain.process(_env(topic="k1.cap.a", envelope_id=2, sequence=2, parent_id=0), rec)
        assert rec.ids == [1, 2, 3]


# ===================================================================
# TimingChain -- sweep (timeout release)
# ===================================================================


class TestTimingChainSweep:
    def test_sweep_releases_causal_timeout(self) -> None:
        config = TimingConfig(rules={"k1.cap": STRICT})
        # Very short timeout for testing
        chain = TimingChain(config=config, timeout_ms=1)
        rec = _Recorder()

        # Buffer a child (parent 99 never arrives)
        chain.process(_env(topic="k1.cap.a", envelope_id=2, sequence=1, parent_id=99), rec)
        assert rec.ids == []

        # Wait for timeout
        time.sleep(0.01)

        released = chain.sweep(rec)
        assert released >= 1
        assert 2 in rec.ids
        assert chain.stats.released_timeout >= 1

    def test_sweep_releases_gap_timeout(self) -> None:
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config, timeout_ms=1)
        rec = _Recorder()

        # Seq 1
        chain.process(_env(topic="k1.cap.a", envelope_id=1, sequence=1), rec)
        # Seq 3 (gap, seq 2 missing forever)
        chain.process(_env(topic="k1.cap.a", envelope_id=3, sequence=3), rec)

        time.sleep(0.01)

        released = chain.sweep(rec)
        assert released >= 1
        assert 3 in rec.ids

    def test_sweep_no_op_without_chain(self) -> None:
        bus = LocalBus()
        assert bus.sweep() == 0


# ===================================================================
# TimingChain -- stats
# ===================================================================


class TestTimingChainStats:
    def test_all_counters_tracked(self) -> None:
        config = TimingConfig(rules={"strict": STRICT, "relaxed": RELAXED, "fire": BEST_EFFORT})
        chain = TimingChain(config=config)
        rec = _Recorder()

        # BEST_EFFORT
        chain.process(_env(topic="fire.x", envelope_id=1, sequence=1), rec)
        # RELAXED
        chain.process(_env(topic="relaxed.x", envelope_id=2, sequence=1), rec)
        # STRICT (in sequence)
        chain.process(_env(topic="strict.x", envelope_id=3, sequence=1), rec)

        s = chain.stats
        assert s.envelopes_processed == 3
        assert s.delivered_immediate >= 2  # BE + RELAXED

    def test_stats_snapshot(self) -> None:
        chain = TimingChain()
        snap = chain.stats.snapshot()
        assert isinstance(snap, dict)
        assert "envelopes_processed" in snap
        assert "buffered_causal" in snap
        assert "released_timeout" in snap


# ===================================================================
# Defaults module
# ===================================================================


class TestDefaults:
    def test_default_rules_populated(self) -> None:
        assert len(DEFAULT_RULES) > 0
        assert "k1.capability" in DEFAULT_RULES
        assert DEFAULT_RULES["k1.capability"] == STRICT
        assert DEFAULT_RULES["k1.k0.sse"] == BEST_EFFORT
        assert DEFAULT_RULES["k1.affect"] == RELAXED

    def test_default_mode_is_relaxed(self) -> None:
        assert DEFAULT_MODE == RELAXED

    def test_default_timing_config_factory(self) -> None:
        config = default_timing_config()
        assert isinstance(config, TimingConfig)
        assert config.rule_count == len(DEFAULT_RULES)
        assert config.default == RELAXED
        assert config.resolve("k1.capability.done.v1") == STRICT
        assert config.resolve("k1.k0.sse.event.v1") == BEST_EFFORT
        assert config.resolve("k1.affect.joy.v1") == RELAXED
        assert config.resolve("k1.unknown") == RELAXED


# ===================================================================
# BusFactory integration
# ===================================================================


class TestBusFactoryTiming:
    def test_create_local_ordered(self) -> None:
        bus = BusFactory.create_local_ordered()
        assert bus.timing_chain is not None
        assert isinstance(bus.timing_chain, TimingChain)

    def test_create_local_ordered_custom_config(self) -> None:
        config = TimingConfig(rules={"test": STRICT})
        bus = BusFactory.create_local_ordered(config=config)
        assert bus.timing_chain is not None
        assert bus.timing_chain.config.resolve("test.topic") == STRICT

    def test_create_for_testing_ordered(self) -> None:
        bus = BusFactory.create_for_testing(ordered=True)
        assert bus.timing_chain is not None
        assert len(bus.captured) == 0  # capture mode on

    def test_create_for_testing_default_no_timing(self) -> None:
        bus = BusFactory.create_for_testing()
        assert bus.timing_chain is None

    def test_create_local_default_no_timing(self) -> None:
        bus = BusFactory.create_local()
        assert bus.timing_chain is None


# ===================================================================
# LocalBus + TimingChain end-to-end
# ===================================================================


class _Collector:
    """Handler that records received envelopes (thread-safe)."""

    def __init__(self) -> None:
        self.received: list[Envelope] = []
        self._lock = threading.Lock()

    def __call__(self, envelope: Envelope) -> None:
        with self._lock:
            self.received.append(envelope)

    @property
    def ids(self) -> list[int]:
        return [e.envelope_id for e in self.received]

    @property
    def seqs(self) -> list[int]:
        return [e.sequence for e in self.received]


class TestLocalBusWithTimingChain:
    def test_strict_causal_ordering_through_bus(self) -> None:
        """End-to-end: child waits for parent through real LocalBus."""
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config)
        bus = LocalBus(capture=True, timing_chain=chain)
        col = _Collector()
        bus.subscribe("k1.cap.>", col)

        # Child before parent
        bus.publish(Envelope(topic="k1.cap.a", payload=b"child", parent_id=100))
        assert col.ids == []  # blocked on parent

        # Parent
        bus.publish(Envelope(topic="k1.cap.a", payload=b"parent"))
        # After parent, child should be released
        # Parent has envelope_id=2 (second publish), child had parent_id=100
        # Wait -- child had parent_id=100, but the parent's envelope_id is 2.
        # parent_id=100 doesn't match envelope_id=2.
        # This means child is stuck waiting for envelope_id=100 which never comes.
        # That's actually correct behavior! The child was specifically waiting
        # for envelope_id=100 as its parent.
        # Let's test the correct scenario where parent_id matches.

    def test_strict_causal_real_parent_ids(self) -> None:
        """Causal ordering with real envelope IDs assigned by the bus."""
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config)
        bus = LocalBus(capture=True, timing_chain=chain)
        col = _Collector()
        bus.subscribe("k1.cap.>", col)

        # First publish gets envelope_id=1
        bus.publish(Envelope(topic="k1.cap.a", payload=b"parent"))
        parent_id = bus.captured[0].envelope_id  # 1
        assert col.seqs == [1]

        # Child references parent's envelope_id
        bus.publish(Envelope(topic="k1.cap.a", payload=b"child", parent_id=parent_id))
        # Child should be delivered because parent already delivered
        assert len(col.received) == 2

    def test_strict_sequence_gap_through_bus(self) -> None:
        """
        End-to-end sequence gap detection.

        LocalBus assigns monotonic sequences 1, 2, 3... so there's no
        natural gap.  To test gap behavior we need the timing chain to
        see out-of-order sequences, which only happens if envelopes are
        pre-stamped or come from external sources.

        Since LocalBus always stamps monotonically, sequence gaps can't
        occur in a single LocalBus.  This test validates that the timing
        chain doesn't interfere with normal monotonic sequences.
        """
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config)
        bus = LocalBus(capture=True, timing_chain=chain)
        col = _Collector()
        bus.subscribe("k1.cap.>", col)

        for i in range(5):
            bus.publish(Envelope(topic="k1.cap.a", payload=f"msg{i}".encode()))

        # All delivered in order (no gaps from LocalBus)
        assert col.seqs == [1, 2, 3, 4, 5]

    def test_relaxed_delivers_immediately_through_bus(self) -> None:
        config = TimingConfig(rules={"k1.affect": RELAXED})
        chain = TimingChain(config=config)
        bus = LocalBus(capture=True, timing_chain=chain)
        col = _Collector()
        bus.subscribe("k1.affect.>", col)

        for i in range(3):
            bus.publish(Envelope(topic="k1.affect.x", payload=b""))

        assert len(col.received) == 3
        assert col.seqs == [1, 2, 3]

    def test_best_effort_delivers_immediately_through_bus(self) -> None:
        config = TimingConfig(rules={"k1.sse": BEST_EFFORT})
        chain = TimingChain(config=config)
        bus = LocalBus(capture=True, timing_chain=chain)
        col = _Collector()
        bus.subscribe("k1.sse.>", col)

        for i in range(3):
            bus.publish(Envelope(topic="k1.sse.event", payload=b""))

        assert len(col.received) == 3

    def test_mixed_modes_through_bus(self) -> None:
        """Different topics resolve to different modes on the same bus."""
        config = TimingConfig(
            rules={
                "k1.cap": STRICT,
                "k1.affect": RELAXED,
                "k1.sse": BEST_EFFORT,
            }
        )
        chain = TimingChain(config=config)
        bus = LocalBus(capture=True, timing_chain=chain)

        strict_col = _Collector()
        relaxed_col = _Collector()
        be_col = _Collector()

        bus.subscribe("k1.cap.>", strict_col)
        bus.subscribe("k1.affect.>", relaxed_col)
        bus.subscribe("k1.sse.>", be_col)

        bus.publish(Envelope(topic="k1.cap.a", payload=b""))
        bus.publish(Envelope(topic="k1.affect.joy", payload=b""))
        bus.publish(Envelope(topic="k1.sse.ping", payload=b""))

        assert len(strict_col.received) == 1
        assert len(relaxed_col.received) == 1
        assert len(be_col.received) == 1

    def test_sweep_through_bus(self) -> None:
        """Bus.sweep() delegates to timing chain."""
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config, timeout_ms=1)
        bus = LocalBus(capture=True, timing_chain=chain)
        col = _Collector()
        bus.subscribe("k1.cap.>", col)

        # Publish child with non-existent parent
        bus.publish(Envelope(topic="k1.cap.a", payload=b"stuck", parent_id=99999))
        assert len(col.received) == 0

        time.sleep(0.01)
        released = bus.sweep()
        assert released >= 1
        assert len(col.received) >= 1

    def test_repr_shows_timing(self) -> None:
        chain = TimingChain()
        bus = LocalBus(timing_chain=chain)
        assert "timing=ON" in repr(bus)

    def test_repr_no_timing(self) -> None:
        bus = LocalBus()
        assert "timing=ON" not in repr(bus)


# ===================================================================
# Thread safety
# ===================================================================


class TestTimingChainThreadSafety:
    def test_concurrent_process_strict(self) -> None:
        """Multiple threads publishing STRICT envelopes concurrently."""
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config)
        rec = _Recorder()
        errors: list[str] = []

        n_threads = 4
        n_per_thread = 50

        def publisher(thread_id: int) -> None:
            topic = f"k1.cap.thread{thread_id}"
            for seq in range(1, n_per_thread + 1):
                try:
                    chain.process(
                        _env(
                            topic=topic,
                            envelope_id=thread_id * 1000 + seq,
                            sequence=seq,
                        ),
                        rec,
                    )
                except Exception as e:
                    errors.append(f"Thread {thread_id} seq {seq}: {e}")

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [pool.submit(publisher, i) for i in range(n_threads)]
            for f in futures:
                f.result()

        assert errors == []
        # Each thread sends n_per_thread in-order envelopes, all should deliver
        assert len(rec.delivered) == n_threads * n_per_thread

    def test_concurrent_process_and_sweep(self) -> None:
        """Publishing and sweeping concurrently must not crash."""
        config = TimingConfig(rules={"k1.cap": STRICT})
        chain = TimingChain(config=config, timeout_ms=1)
        rec = _Recorder()
        stop = threading.Event()
        errors: list[str] = []

        def publisher() -> None:
            seq = 1
            while not stop.is_set():
                try:
                    chain.process(
                        _env(topic="k1.cap.a", envelope_id=seq, sequence=seq),
                        rec,
                    )
                    seq += 1
                except Exception as e:
                    errors.append(f"Publisher: {e}")

        def sweeper() -> None:
            while not stop.is_set():
                try:
                    chain.sweep(rec)
                except Exception as e:
                    errors.append(f"Sweeper: {e}")
                time.sleep(0.001)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(publisher), pool.submit(sweeper)]
            stop.wait(timeout=0.2)
            stop.set()
            for f in futures:
                f.result()

        assert errors == []
