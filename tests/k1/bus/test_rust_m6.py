"""
V2-M6 Python tests: RustTimingConfig and WfqScheduler.

Tests cover:
  - Epic 6.3: RustTimingConfig prefix trie resolve, reload, set_default
  - Epic 6.4: WfqScheduler enqueue/dequeue, deficit round-robin, starvation
  - Parity: RustTimingConfig vs Python TimingConfig resolve behavior
"""

from __future__ import annotations

import threading

import pytest

# --- Conditional import ---

try:
    import k1_bus_core

    HAS_RUST = True
except ImportError:
    HAS_RUST = False
    k1_bus_core = None  # type: ignore[assignment]

from k1.bus.envelope import DeliveryMode
from k1.bus.timing.timing_config import TimingConfig

pytestmark = pytest.mark.skipif(not HAS_RUST, reason="k1_bus_core not installed")

# ==================================================================
# RustTimingConfig tests (Epic 6.3)
# ==================================================================


class TestRustTimingConfigConstruction:
    """V2-M6-007: Prefix trie construction."""

    def test_default_no_rules(self) -> None:
        cfg = k1_bus_core.RustTimingConfig()
        assert cfg.rule_count == 0
        assert cfg.default_mode == 1  # RELAXED

    def test_with_rules(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(
            rules={"k1.capability": 0, "k1.k0.sse": 2},
            default=1,
        )
        assert cfg.rule_count == 2
        assert cfg.default_mode == 1

    def test_custom_default(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(default=0)
        assert cfg.default_mode == 0  # STRICT

    def test_invalid_default_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid default mode"):
            k1_bus_core.RustTimingConfig(default=99)

    def test_invalid_rule_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid mode"):
            k1_bus_core.RustTimingConfig(rules={"k1.test": 99})

    def test_empty_prefix_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty prefix"):
            k1_bus_core.RustTimingConfig(rules={"": 0})

    def test_repr(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(rules={"k1.a": 0}, default=1)
        r = repr(cfg)
        assert "RustTimingConfig" in r
        assert "rules=1" in r
        assert "RELAXED" in r


class TestRustTimingConfigResolve:
    """V2-M6-007: Prefix trie resolve."""

    def test_exact_prefix_match(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(rules={"k1.capability": 0})
        assert cfg.resolve("k1.capability") == 0

    def test_prefix_match_longer_topic(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(rules={"k1.capability": 0})
        assert cfg.resolve("k1.capability.completed.v1") == 0

    def test_longest_prefix_wins(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(
            rules={"k1": 1, "k1.capability": 0},
            default=2,
        )
        assert cfg.resolve("k1.capability.completed.v1") == 0  # STRICT
        assert cfg.resolve("k1.other.stuff") == 1  # RELAXED (k1 prefix)
        assert cfg.resolve("k0.unknown") == 2  # BEST_EFFORT (default)

    def test_no_match_returns_default(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(rules={"k1.capability": 0}, default=1)
        assert cfg.resolve("k1.unknown.topic") == 1

    def test_empty_topic_returns_default(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(default=2)
        assert cfg.resolve("") == 2

    def test_multiple_rules(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(
            rules={
                "k1.capability": 0,
                "k1.k0.sse": 2,
                "k1.session": 1,
            },
            default=1,
        )
        assert cfg.resolve("k1.capability.completed.v1") == 0
        assert cfg.resolve("k1.k0.sse.events") == 2
        assert cfg.resolve("k1.session.update") == 1
        assert cfg.resolve("k1.unknown") == 1


class TestRustTimingConfigReload:
    """V2-M6-008: Runtime reload."""

    def test_reload_replaces_rules(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(rules={"k1.old": 0})
        assert cfg.resolve("k1.old.topic") == 0

        cfg.reload({"k1.new": 2})
        assert cfg.resolve("k1.old.topic") == 1  # default (old rule gone)
        assert cfg.resolve("k1.new.topic") == 2
        assert cfg.rule_count == 1

    def test_reload_empty_prefix_raises(self) -> None:
        cfg = k1_bus_core.RustTimingConfig()
        with pytest.raises(ValueError, match="Empty prefix"):
            cfg.reload({"": 0})

    def test_set_default(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(default=1)
        assert cfg.default_mode == 1
        cfg.set_default(0)
        assert cfg.default_mode == 0
        assert cfg.resolve("k1.unknown") == 0

    def test_rules_getter(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(
            rules={"k1.a": 0, "k1.b": 2},
        )
        rules = cfg.rules
        assert rules["k1.a"] == 0
        assert rules["k1.b"] == 2
        assert len(rules) == 2


class TestRustTimingConfigParity:
    """Parity: RustTimingConfig resolve matches Python TimingConfig resolve."""

    RULES = {
        "k1.capability": DeliveryMode.STRICT,
        "k1.capability.completed": DeliveryMode.RELAXED,
        "k1.k0.sse": DeliveryMode.BEST_EFFORT,
        "k1.session": DeliveryMode.RELAXED,
        "k1.agent": DeliveryMode.STRICT,
    }

    TOPICS = [
        "k1.capability.completed.v1",
        "k1.capability.started.v1",
        "k1.k0.sse.events.heartbeat",
        "k1.session.update",
        "k1.agent.abc.delta.v1",
        "k1.unknown.topic",
        "k1.something.else",
        "",
    ]

    def test_resolve_parity(self) -> None:
        py_cfg = TimingConfig(rules=self.RULES, default=DeliveryMode.RELAXED)
        rust_rules = {k: v.value for k, v in self.RULES.items()}
        rust_cfg = k1_bus_core.RustTimingConfig(rules=rust_rules, default=1)

        for topic in self.TOPICS:
            py_result = py_cfg.resolve(topic).value
            rust_result = rust_cfg.resolve(topic)
            assert py_result == rust_result, (
                f"Parity mismatch for {topic!r}: " f"Python={py_result}, Rust={rust_result}"
            )


class TestRustTimingConfigThreadSafety:
    """Concurrent resolve + reload."""

    def test_concurrent_resolve_and_reload(self) -> None:
        cfg = k1_bus_core.RustTimingConfig(
            rules={"k1.test": 0},
            default=1,
        )
        errors: list[Exception] = []
        stop = threading.Event()

        def resolver() -> None:
            while not stop.is_set():
                try:
                    result = cfg.resolve("k1.test.something")
                    assert result in (0, 1, 2)
                except Exception as e:
                    errors.append(e)

        def reloader() -> None:
            for i in range(200):
                try:
                    cfg.reload({"k1.test": i % 3})
                except Exception as e:
                    errors.append(e)

        resolver_threads = [threading.Thread(target=resolver) for _ in range(4)]
        reloader_thread = threading.Thread(target=reloader)

        for t in resolver_threads:
            t.start()
        reloader_thread.start()
        reloader_thread.join()
        stop.set()
        for t in resolver_threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"


# ==================================================================
# WfqScheduler tests (Epic 6.4)
# ==================================================================


class TestWfqSchedulerConstruction:
    """V2-M6-009: WFQ construction."""

    def test_default_construction(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        assert wfq.is_empty is True
        assert wfq.depth == 0

    def test_custom_weights(self) -> None:
        wfq = k1_bus_core.WfqScheduler(weights=[1, 1, 1, 1])
        assert wfq.get_weight(0) == 1
        assert wfq.get_weight(3) == 1

    def test_invalid_weights_count(self) -> None:
        with pytest.raises(ValueError, match="Expected 4 weights"):
            k1_bus_core.WfqScheduler(weights=[1, 2])

    def test_repr(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        r = repr(wfq)
        assert "WfqScheduler" in r
        assert "depth=0" in r


class TestWfqSchedulerEnqueueDequeue:
    """V2-M6-009: Core enqueue/dequeue."""

    def test_single_item_round_trip(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        wfq.enqueue(42, 0)
        assert wfq.depth == 1
        result = wfq.next()
        assert result == (42, 0)
        assert wfq.is_empty is True

    def test_empty_returns_none(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        assert wfq.next() is None

    def test_fifo_within_priority(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        for i in range(10):
            wfq.enqueue(i, 2)
        for i in range(10):
            tag, priority = wfq.next()
            assert tag == i
            assert priority == 2

    def test_invalid_priority_raises(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        with pytest.raises(ValueError, match="Priority must be"):
            wfq.enqueue(1, 4)


class TestWfqSchedulerDeficitRoundRobin:
    """V2-M6-009: Deficit round-robin behavior."""

    def test_urgent_served_first(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        wfq.enqueue(1, 3)  # BACKGROUND
        wfq.enqueue(2, 0)  # URGENT
        tag, priority = wfq.next()
        assert priority == 0  # URGENT first

    def test_all_priorities_one_each(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        wfq.enqueue(0, 0)  # URGENT
        wfq.enqueue(1, 1)  # REALTIME
        wfq.enqueue(2, 2)  # INTERACTIVE
        wfq.enqueue(3, 3)  # BACKGROUND

        order = []
        while (item := wfq.next()) is not None:
            order.append(item[1])

        # URGENT (deficit=4) > REALTIME (3) > INTERACTIVE (2) > BACKGROUND (1)
        assert order == [0, 1, 2, 3]


class TestWfqSchedulerStarvation:
    """V2-M6-014: BACKGROUND never starved under URGENT flood."""

    def test_background_not_starved(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        # 10K URGENT
        for i in range(10_000):
            wfq.enqueue(i, 0)
        # 100 BACKGROUND
        for i in range(100):
            wfq.enqueue(10_000 + i, 3)

        urgent_count = 0
        bg_count = 0
        while (item := wfq.next()) is not None:
            if item[1] == 0:
                urgent_count += 1
            elif item[1] == 3:
                bg_count += 1

        assert urgent_count == 10_000
        assert bg_count == 100  # All BACKGROUND delivered, not starved

    def test_interleaved_scheduling(self) -> None:
        """With equal enqueue rates, verify BACKGROUND appears within first N dequeues."""
        wfq = k1_bus_core.WfqScheduler()
        wfq.enqueue(1, 0)  # URGENT, deficit=4
        wfq.enqueue(2, 3)  # BACKGROUND, deficit=1

        # First dequeue: URGENT (higher deficit)
        tag, _ = wfq.next()
        assert tag == 1
        # Second dequeue: BACKGROUND (only one left)
        tag, _ = wfq.next()
        assert tag == 2


class TestWfqSchedulerWeights:
    """V2-M6-010: Configurable weights."""

    def test_default_weights(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        assert wfq.get_weight(0) == 4  # URGENT
        assert wfq.get_weight(1) == 3  # REALTIME
        assert wfq.get_weight(2) == 2  # INTERACTIVE
        assert wfq.get_weight(3) == 1  # BACKGROUND

    def test_hot_reload_weight(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        wfq.set_weight(3, 10)
        assert wfq.get_weight(3) == 10


class TestWfqSchedulerStats:
    """V2-M6-009: Stats observable."""

    def test_stats_tracking(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        wfq.enqueue(1, 0)
        wfq.enqueue(2, 3)
        s = wfq.stats
        assert s["total_enqueued"] == 2
        assert s["total_dequeued"] == 0
        assert s["queue_depths"] == [1, 0, 0, 1]
        assert s["weights"] == [4, 3, 2, 1]

        wfq.next()
        s = wfq.stats
        assert s["total_dequeued"] == 1


class TestWfqSchedulerThreadSafety:
    """Concurrent enqueue/dequeue."""

    def test_concurrent_enqueue_dequeue(self) -> None:
        wfq = k1_bus_core.WfqScheduler()
        errors: list[Exception] = []
        stop = threading.Event()
        n_per_thread = 1000

        def enqueuer(priority: int) -> None:
            for i in range(n_per_thread):
                try:
                    wfq.enqueue(i, priority)
                except Exception as e:
                    errors.append(e)

        def dequeuer() -> None:
            while not stop.is_set():
                try:
                    wfq.next()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=enqueuer, args=(p,)) for p in range(4)]
        dq_threads = [threading.Thread(target=dequeuer) for _ in range(2)]

        for t in threads + dq_threads:
            t.start()
        for t in threads:
            t.join()
        stop.set()
        for t in dq_threads:
            t.join()

        # Drain remaining
        while wfq.next() is not None:
            pass

        assert errors == [], f"Thread safety errors: {errors}"
