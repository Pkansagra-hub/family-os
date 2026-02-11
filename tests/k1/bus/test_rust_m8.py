"""V2-M8: Async Dispatch + Circuit Breaker + Sweep Timer -- Python tests.

Milestones covered:
  - M8-001: Async dispatch thread (crossbeam channel + GIL batching)
  - M8-002: Sync/async dispatch modes (default=Sync)
  - M8-003: GIL batching in async mode
  - M8-004: Per-topic ordering preservation in async mode
  - M8-005: Per-handler circuit breaker (CircuitBreakerRegistry)
  - M8-006: Configurable failure_threshold + cooldown_ms
  - M8-007: bus.handler_circuits(), bus.reset_circuit()
  - M8-008: Built-in sweep timer (SweepTimer)
  - M8-009: Configurable sweep interval
  - M8-010: bus.sweep() no-op when auto-sweep active
"""

import time
import threading
import pytest

from k1_bus_core import RustBus, RustEnvelope, SweepTimer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_envelope(topic="k1.test.alpha", payload=b"hello", ttl_ms=0):
    return RustEnvelope(topic=topic, payload=payload, ttl_ms=ttl_ms)


class Counter:
    """Thread-safe invocation counter."""
    def __init__(self):
        self.n = 0
        self._lock = threading.Lock()

    def __call__(self, env):
        with self._lock:
            self.n += 1


class FailingHandler:
    """Handler that raises on every call."""
    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, env):
        with self._lock:
            self.calls += 1
        raise RuntimeError("boom")


class FailNTimesHandler:
    """Handler that fails the first N calls, then succeeds."""
    def __init__(self, fail_count):
        self.calls = 0
        self.fail_count = fail_count
        self._lock = threading.Lock()

    def __call__(self, env):
        with self._lock:
            self.calls += 1
            if self.calls <= self.fail_count:
                raise RuntimeError(f"fail #{self.calls}")


class OrderTracker:
    """Records envelope_ids in arrival order."""
    def __init__(self):
        self.ids = []
        self._lock = threading.Lock()

    def __call__(self, env):
        with self._lock:
            self.ids.append(env.envelope_id)


# =========================================================================
# Epic 8.2: Circuit Breaker (M8-005, M8-006, M8-007)
# =========================================================================

class TestCircuitBreakerSyncIntegration:
    """Circuit breaker in sync dispatch mode."""

    def test_failing_handler_opens_circuit(self):
        """After failure_threshold failures, circuit opens and skips handler."""
        bus = RustBus(capture=False, failure_threshold=3, cooldown_ms=60000)
        handler = FailingHandler()
        bus.subscribe("k1.test.*", handler)

        # 3 failures should open the circuit
        for _ in range(3):
            bus.publish(make_envelope())

        assert handler.calls == 3
        stats = bus.stats
        assert stats["handler_errors"] == 3

        # Next publish should skip handler (circuit open)
        bus.publish(make_envelope())
        assert handler.calls == 3  # Not invoked -- circuit is open
        assert bus.stats["handler_errors"] == 4  # Counted as error (circuit reject)

    def test_circuit_open_skips_all_publishes(self):
        """Once open, all publishes are skipped until cooldown."""
        bus = RustBus(capture=False, failure_threshold=1, cooldown_ms=60000)
        handler = FailingHandler()
        bus.subscribe("k1.test.*", handler)

        bus.publish(make_envelope())  # Opens after 1 failure
        assert handler.calls == 1

        for _ in range(10):
            bus.publish(make_envelope())

        assert handler.calls == 1  # Still 1 -- all skipped

    def test_handler_circuits_returns_states(self):
        """handler_circuits() returns {pattern: state} dict."""
        bus = RustBus(capture=False, failure_threshold=2, cooldown_ms=60000)
        counter = Counter()
        fail = FailingHandler()

        bus.subscribe("k1.ok.*", counter)
        bus.subscribe("k1.fail.*", fail)

        # Publish to both
        bus.publish(make_envelope("k1.ok.alpha"))
        bus.publish(make_envelope("k1.fail.beta"))
        bus.publish(make_envelope("k1.fail.beta"))

        circuits = bus.handler_circuits()
        assert circuits["k1.ok.*"] == "CLOSED"
        assert circuits["k1.fail.*"] == "OPEN"

    def test_reset_circuit(self):
        """reset_circuit() closes an open circuit."""
        bus = RustBus(capture=False, failure_threshold=1, cooldown_ms=60000)
        handler = FailNTimesHandler(fail_count=1)
        bus.subscribe("k1.test.*", handler)

        bus.publish(make_envelope())  # Fails -> opens
        assert handler.calls == 1

        circuits = bus.handler_circuits()
        assert circuits["k1.test.*"] == "OPEN"

        # Reset
        assert bus.reset_circuit("k1.test.*") is True
        circuits = bus.handler_circuits()
        assert circuits["k1.test.*"] == "CLOSED"

        # Publish again -- handler should be called (and succeed this time)
        bus.publish(make_envelope())
        assert handler.calls == 2

    def test_reset_circuit_unknown_pattern(self):
        """reset_circuit() returns False for unknown pattern."""
        bus = RustBus()
        assert bus.reset_circuit("k1.nonexistent.*") is False

    def test_circuit_halfopen_after_cooldown(self):
        """After cooldown, circuit transitions to HALF_OPEN and allows probe."""
        bus = RustBus(capture=False, failure_threshold=1, cooldown_ms=1)
        handler = FailNTimesHandler(fail_count=1)
        bus.subscribe("k1.test.*", handler)

        bus.publish(make_envelope())  # Fails -> opens
        assert handler.calls == 1

        # Wait for cooldown (1ms + buffer)
        time.sleep(0.01)

        # Next publish should probe (HALF_OPEN)
        bus.publish(make_envelope())
        assert handler.calls == 2  # Probe allowed, succeeds

        # Circuit should be CLOSED again
        circuits = bus.handler_circuits()
        assert circuits["k1.test.*"] == "CLOSED"

    def test_halfopen_failure_reopens(self):
        """If probe fails in HALF_OPEN, circuit reopens."""
        bus = RustBus(capture=False, failure_threshold=1, cooldown_ms=1)
        handler = FailingHandler()  # Always fails
        bus.subscribe("k1.test.*", handler)

        bus.publish(make_envelope())  # Fails -> OPEN
        assert handler.calls == 1

        time.sleep(0.01)  # Wait for cooldown

        bus.publish(make_envelope())  # Probe allowed (HALF_OPEN), fails -> OPEN again
        assert handler.calls == 2

        circuits = bus.handler_circuits()
        assert circuits["k1.test.*"] == "OPEN"

    def test_success_handler_stays_closed(self):
        """A handler that always succeeds keeps circuit CLOSED."""
        bus = RustBus(capture=False, failure_threshold=5)
        counter = Counter()
        bus.subscribe("k1.test.*", counter)

        for _ in range(20):
            bus.publish(make_envelope())

        assert counter.n == 20
        circuits = bus.handler_circuits()
        assert circuits["k1.test.*"] == "CLOSED"

    def test_unsubscribe_cleans_up_circuit(self):
        """Unsubscribing removes the handler's circuit breaker entry."""
        bus = RustBus(capture=False, failure_threshold=1, cooldown_ms=60000)
        handler = FailingHandler()
        sub_id = bus.subscribe("k1.test.*", handler)

        bus.publish(make_envelope())  # Opens circuit
        circuits = bus.handler_circuits()
        assert len(circuits) > 0

        bus.unsubscribe(sub_id)
        circuits = bus.handler_circuits()
        # Circuit entry should be cleaned up
        assert "k1.test.*" not in circuits

    def test_configurable_thresholds(self):
        """Different threshold values work correctly."""
        bus = RustBus(capture=False, failure_threshold=10, cooldown_ms=60000)
        handler = FailingHandler()
        bus.subscribe("k1.test.*", handler)

        # 9 failures should NOT open (threshold is 10)
        for _ in range(9):
            bus.publish(make_envelope())
        assert handler.calls == 9

        # 10th should trigger open
        bus.publish(make_envelope())
        assert handler.calls == 10

        # 11th should be skipped
        bus.publish(make_envelope())
        assert handler.calls == 10  # Circuit open, skipped

    def test_multiple_handlers_independent_circuits(self):
        """Each handler has its own circuit breaker."""
        bus = RustBus(capture=False, failure_threshold=2, cooldown_ms=60000)
        fail1 = FailingHandler()
        ok = Counter()

        bus.subscribe("k1.test.*", fail1)
        bus.subscribe("k1.test.*", ok)

        # Both receive (fail1 fails, ok succeeds)
        bus.publish(make_envelope())
        bus.publish(make_envelope())

        assert fail1.calls == 2
        assert ok.n == 2  # Both called

        # fail1 circuit now open, ok stays closed
        bus.publish(make_envelope())
        assert fail1.calls == 2  # Skipped
        assert ok.n == 3  # Still called


# =========================================================================
# Epic 8.1: Async Dispatch (M8-001, M8-002, M8-003, M8-004)
# =========================================================================

class TestAsyncDispatch:
    """Async dispatch mode: publisher returns immediately, handler called from background thread."""

    def test_default_is_sync(self):
        """Default dispatch_mode is 0 (Sync)."""
        bus = RustBus()
        assert bus.dispatch_mode_value == 0

    def test_async_mode_construction(self):
        """dispatch_mode=1 creates an async bus."""
        bus = RustBus(dispatch_mode=1)
        assert bus.dispatch_mode_value == 1
        bus.close()

    def test_async_publish_delivers(self):
        """Handler is eventually called in async mode."""
        bus = RustBus(dispatch_mode=1, capture=False)
        counter = Counter()
        bus.subscribe("k1.test.*", counter)

        bus.publish(make_envelope())

        # Wait for async delivery
        deadline = time.monotonic() + 2.0
        while counter.n < 1 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert counter.n == 1
        bus.close()

    def test_async_multiple_publishes(self):
        """Multiple publishes are all delivered in async mode."""
        bus = RustBus(dispatch_mode=1, capture=False)
        counter = Counter()
        bus.subscribe("k1.test.*", counter)

        for _ in range(50):
            bus.publish(make_envelope())

        deadline = time.monotonic() + 2.0
        while counter.n < 50 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert counter.n == 50
        bus.close()

    def test_async_ordering_preserved(self):
        """Envelope IDs arrive in order in async mode."""
        bus = RustBus(dispatch_mode=1, capture=False)
        tracker = OrderTracker()
        bus.subscribe("k1.test.*", tracker)

        for _ in range(100):
            bus.publish(make_envelope())

        deadline = time.monotonic() + 2.0
        while len(tracker.ids) < 100 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert len(tracker.ids) == 100
        # IDs should be monotonically increasing
        for i in range(1, len(tracker.ids)):
            assert tracker.ids[i] > tracker.ids[i - 1], (
                f"Order violation at index {i}: {tracker.ids[i-1]} >= {tracker.ids[i]}"
            )
        bus.close()

    def test_async_error_isolation(self):
        """Failing handler in async mode doesn't block other handlers."""
        bus = RustBus(dispatch_mode=1, capture=False, failure_threshold=100)
        fail = FailingHandler()
        ok = Counter()
        bus.subscribe("k1.test.*", fail)
        bus.subscribe("k1.test.*", ok)

        for _ in range(10):
            bus.publish(make_envelope())

        deadline = time.monotonic() + 2.0
        while ok.n < 10 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert ok.n == 10  # All delivered despite failures
        assert fail.calls == 10
        bus.close()

    def test_async_circuit_breaker(self):
        """Circuit breaker works in async mode too."""
        bus = RustBus(
            dispatch_mode=1,
            capture=False,
            failure_threshold=3,
            cooldown_ms=60000,
        )
        handler = FailingHandler()
        bus.subscribe("k1.test.*", handler)

        for _ in range(10):
            bus.publish(make_envelope())

        # Wait for async processing
        deadline = time.monotonic() + 2.0
        while bus.stats["handler_errors"] < 10 and time.monotonic() < deadline:
            time.sleep(0.01)

        # Only 3 actual calls (first 3 failures open circuit)
        assert handler.calls == 3
        bus.close()

    def test_async_stats_accurate(self):
        """Stats are properly updated in async mode."""
        bus = RustBus(dispatch_mode=1, capture=False)
        counter = Counter()
        bus.subscribe("k1.test.*", counter)

        for _ in range(20):
            bus.publish(make_envelope())

        deadline = time.monotonic() + 2.0
        while counter.n < 20 and time.monotonic() < deadline:
            time.sleep(0.01)

        stats = bus.stats
        assert stats["envelopes_published"] == 20
        assert stats["envelopes_delivered"] == 20
        assert stats["handler_errors"] == 0
        bus.close()

    def test_async_close_stops_dispatch(self):
        """Closing the bus stops async dispatch."""
        bus = RustBus(dispatch_mode=1, capture=False)
        counter = Counter()
        bus.subscribe("k1.test.*", counter)

        bus.publish(make_envelope())
        deadline = time.monotonic() + 2.0
        while counter.n < 1 and time.monotonic() < deadline:
            time.sleep(0.01)

        bus.close()
        before = counter.n

        # Publishes after close should fail
        with pytest.raises(RuntimeError):
            bus.publish(make_envelope())

        # No more deliveries after close
        time.sleep(0.2)
        assert counter.n == before


# =========================================================================
# Epic 8.3: Sweep Timer (M8-008, M8-009, M8-010)
# =========================================================================

class TestSweepTimer:
    """Built-in sweep timer for periodic maintenance tasks."""

    def test_construction(self):
        """SweepTimer can be created with a Python callback."""
        counter = {"n": 0}
        def tick():
            counter["n"] += 1

        timer = SweepTimer(tick, interval_ms=100)
        assert timer.is_running is True
        assert timer.interval == 100
        timer.stop()

    def test_ticks_periodically(self):
        """Callback is invoked at the configured interval."""
        counter = {"n": 0}
        lock = threading.Lock()

        def tick():
            with lock:
                counter["n"] += 1

        timer = SweepTimer(tick, interval_ms=30)
        time.sleep(0.25)
        timer.stop()

        with lock:
            count = counter["n"]
        # ~8 ticks in 250ms at 30ms interval (conservative: >= 4)
        assert count >= 4, f"Expected >= 4 ticks, got {count}"

    def test_stop(self):
        """Timer stops ticking after stop()."""
        counter = {"n": 0}
        lock = threading.Lock()

        def tick():
            with lock:
                counter["n"] += 1

        timer = SweepTimer(tick, interval_ms=20)
        time.sleep(0.1)
        timer.stop()
        assert timer.is_running is False

        with lock:
            count_at_stop = counter["n"]

        time.sleep(0.1)
        with lock:
            count_after = counter["n"]

        assert count_after == count_at_stop, "Timer ticked after stop"

    def test_configurable_interval(self):
        """set_interval() changes tick frequency."""
        timer = SweepTimer(lambda: None, interval_ms=500)
        assert timer.interval == 500

        timer.set_interval(100)
        assert timer.interval == 100
        timer.stop()

    def test_interval_zero_rejected(self):
        """interval_ms=0 raises ValueError."""
        with pytest.raises(ValueError):
            SweepTimer(lambda: None, interval_ms=0)

    def test_set_interval_zero_rejected(self):
        """set_interval(0) raises ValueError."""
        timer = SweepTimer(lambda: None, interval_ms=100)
        with pytest.raises(ValueError):
            timer.set_interval(0)
        timer.stop()

    def test_repr(self):
        """__repr__ shows running state and interval."""
        timer = SweepTimer(lambda: None, interval_ms=200)
        r = repr(timer)
        assert "running=true" in r
        assert "interval_ms=200" in r
        timer.stop()

    def test_default_interval(self):
        """Default interval is 1000ms."""
        timer = SweepTimer(lambda: None)
        assert timer.interval == 1000
        timer.stop()


# =========================================================================
# Backward Compatibility
# =========================================================================

class TestBackwardCompatibility:
    """Existing sync-mode behavior is unchanged."""

    def test_sync_default(self):
        """Default RustBus is sync mode with circuit breaker defaults."""
        bus = RustBus()
        assert bus.dispatch_mode_value == 0

    def test_sync_publish_subscribe(self):
        """Basic publish/subscribe still works in sync mode."""
        bus = RustBus(capture=True)
        received = []
        bus.subscribe("k1.test.*", lambda e: received.append(e.topic))
        bus.publish(make_envelope())

        assert len(received) == 1
        assert received[0] == "k1.test.alpha"
        assert bus.stats["envelopes_published"] == 1
        assert bus.stats["envelopes_delivered"] == 1

    def test_sync_unsubscribe(self):
        """Unsubscribe still works."""
        bus = RustBus()
        counter = Counter()
        sub_id = bus.subscribe("k1.test.*", counter)
        bus.publish(make_envelope())
        assert counter.n == 1

        bus.unsubscribe(sub_id)
        bus.publish(make_envelope())
        assert counter.n == 1  # Not called after unsubscribe

    def test_lifecycle_events_still_fire(self):
        """Subscription lifecycle events still work."""
        bus = RustBus(capture=False)
        events = []
        bus.subscribe("k1.bus.subscription.>", lambda e: events.append(e.topic))

        sub_id = bus.subscribe("k1.test.*", lambda e: None)
        # Should have received a lifecycle event
        assert len(events) >= 1

        bus.unsubscribe(sub_id)
        assert len(events) >= 2


# =========================================================================
# Edge Cases
# =========================================================================

class TestEdgeCases:
    """Edge cases and stress tests."""

    def test_async_empty_bus(self):
        """Async bus with no subscribers doesn't crash."""
        bus = RustBus(dispatch_mode=1)
        for _ in range(10):
            bus.publish(make_envelope())
        time.sleep(0.1)
        assert bus.stats["envelopes_published"] == 10
        bus.close()

    def test_high_throughput_sync(self):
        """Sync mode handles many publishes without issue."""
        bus = RustBus(capture=False)
        counter = Counter()
        bus.subscribe("k1.test.*", counter)

        n = 1000
        for _ in range(n):
            bus.publish(make_envelope())

        assert counter.n == n
        assert bus.stats["envelopes_published"] == n
        assert bus.stats["envelopes_delivered"] == n
