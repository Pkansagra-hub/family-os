"""
tests.poc.test_m11_obs_e111 -- E11.1 Unified Metrics Emission Layer

Covers issues 11.1.1 through 11.1.4:
    11.1.1  MetricEnvelope schema and MetricsCollector
    11.1.2  MetricAggregator with sliding windows
    11.1.3  Metric bus topics and builders
    11.1.4  MetricsCollector bootstrap wiring (bus subscriber)

Acceptance criteria from v3_milestones.md:
    - MetricEnvelope is JSON-serializable via to_dict()
    - MetricsCollector tracks counters, gauges, histograms
    - snapshot() returns all pending metrics
    - emit_all() publishes MetricEnvelopes to bus
    - SlidingWindow correctly evicts stale entries
    - rate() returns events/second for a counter
    - percentile() returns p50/p95/p99 for histograms
    - Tests with synthetic data verify sliding window math
    - Metric bus topics registered in ALL_TOPICS
    - Builders produce correct Envelope objects
    - TurnTimer emits per-phase durations
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from poc.k1_poc.obs.metrics import (
    MetricAggregator,
    MetricEnvelope,
    MetricsCollector,
    SlidingWindow,
    TurnTimer,
    _label_key,
    _now_ms,
    build_session_summary,
    emit_metric,
)

# =====================================================================
# 11.1.1 -- MetricEnvelope
# =====================================================================


class TestMetricEnvelope:
    """MetricEnvelope schema and serialization tests."""

    def test_envelope_counter_creation(self) -> None:
        env = MetricEnvelope(
            metric_name="react_loop.front.degenerate_count",
            metric_type="counter",
            value=1.0,
            labels={"mode": "STANDARD", "actor": "front"},
            session_id="s1",
            turn_number=3,
        )
        assert env.metric_name == "react_loop.front.degenerate_count"
        assert env.metric_type == "counter"
        assert env.value == 1.0
        assert env.labels == {"mode": "STANDARD", "actor": "front"}
        assert env.session_id == "s1"
        assert env.turn_number == 3
        assert env.timestamp_ms > 0  # auto-filled

    def test_envelope_gauge_creation(self) -> None:
        env = MetricEnvelope(
            metric_name="backpool.worker.utilization",
            metric_type="gauge",
            value=0.75,
            session_id="s2",
        )
        assert env.metric_type == "gauge"
        assert env.value == 0.75

    def test_envelope_histogram_creation(self) -> None:
        env = MetricEnvelope(
            metric_name="phase1.ultrabert.latency_ms",
            metric_type="histogram",
            value=18.5,
            labels={"actor": "phase1"},
        )
        assert env.metric_type == "histogram"
        assert env.value == 18.5

    def test_envelope_summary_type(self) -> None:
        env = MetricEnvelope(
            metric_name="turn.summary",
            metric_type="summary",
            value=42.0,
        )
        assert env.metric_type == "summary"

    def test_envelope_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid metric_type"):
            MetricEnvelope(
                metric_name="bad",
                metric_type="unknown",
                value=1.0,
            )

    def test_envelope_frozen(self) -> None:
        env = MetricEnvelope(
            metric_name="test.frozen",
            metric_type="counter",
            value=1.0,
        )
        with pytest.raises(AttributeError):
            env.value = 2.0  # type: ignore[misc]

    def test_to_dict(self) -> None:
        env = MetricEnvelope(
            metric_name="bus.publish_count",
            metric_type="counter",
            value=5.0,
            labels={"topic": "user.input"},
            session_id="s1",
            turn_number=2,
            timestamp_ms=1000,
            source_event_id=42,
        )
        d = env.to_dict()
        assert d["metric_name"] == "bus.publish_count"
        assert d["metric_type"] == "counter"
        assert d["value"] == 5.0
        assert d["labels"] == {"topic": "user.input"}
        assert d["session_id"] == "s1"
        assert d["turn_number"] == 2
        assert d["timestamp_ms"] == 1000
        assert d["source_event_id"] == 42

    def test_to_json(self) -> None:
        import json

        env = MetricEnvelope(
            metric_name="test.json",
            metric_type="gauge",
            value=3.14,
            timestamp_ms=5000,
        )
        parsed = json.loads(env.to_json())
        assert parsed["metric_name"] == "test.json"
        assert parsed["value"] == 3.14

    def test_from_dict_roundtrip(self) -> None:
        original = MetricEnvelope(
            metric_name="roundtrip.test",
            metric_type="histogram",
            value=99.9,
            labels={"actor": "back", "tier": "HIGH"},
            session_id="s5",
            turn_number=7,
            timestamp_ms=12345,
            source_event_id=100,
        )
        d = original.to_dict()
        restored = MetricEnvelope.from_dict(d)
        assert restored == original

    def test_from_dict_minimal(self) -> None:
        env = MetricEnvelope.from_dict(
            {
                "metric_name": "min.test",
                "metric_type": "counter",
                "value": 1.0,
            }
        )
        assert env.metric_name == "min.test"
        assert env.session_id == ""
        assert env.turn_number == 0

    def test_auto_timestamp(self) -> None:
        before = _now_ms()
        env = MetricEnvelope(
            metric_name="ts.auto",
            metric_type="counter",
            value=1.0,
        )
        after = _now_ms()
        assert before <= env.timestamp_ms <= after

    def test_explicit_timestamp_preserved(self) -> None:
        env = MetricEnvelope(
            metric_name="ts.explicit",
            metric_type="counter",
            value=1.0,
            timestamp_ms=42000,
        )
        assert env.timestamp_ms == 42000

    def test_labels_default_empty_dict(self) -> None:
        env = MetricEnvelope(
            metric_name="labels.default",
            metric_type="gauge",
            value=0.0,
        )
        assert env.labels == {}

    def test_source_event_id_default_none(self) -> None:
        env = MetricEnvelope(
            metric_name="src.default",
            metric_type="counter",
            value=1.0,
        )
        assert env.source_event_id is None


# =====================================================================
# 11.1.1 -- MetricsCollector
# =====================================================================


class TestMetricsCollector:
    """MetricsCollector counter, gauge, histogram, emission tests."""

    def test_increment_counter(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("react_loop.front.degenerate_count", {"mode": "STANDARD"})
        assert mc.get_counter("react_loop.front.degenerate_count", {"mode": "STANDARD"}) == 1.0
        mc.increment("react_loop.front.degenerate_count", {"mode": "STANDARD"})
        assert mc.get_counter("react_loop.front.degenerate_count", {"mode": "STANDARD"}) == 2.0

    def test_increment_different_labels(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("count", {"mode": "A"})
        mc.increment("count", {"mode": "B"})
        assert mc.get_counter("count", {"mode": "A"}) == 1.0
        assert mc.get_counter("count", {"mode": "B"}) == 1.0

    def test_increment_custom_value(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("big_counter", value=10.0)
        assert mc.get_counter("big_counter") == 10.0

    def test_gauge_set(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.gauge("backpool.utilization", value=0.5)
        assert mc.get_gauge("backpool.utilization") == 0.5
        mc.gauge("backpool.utilization", value=0.9)
        assert mc.get_gauge("backpool.utilization") == 0.9

    def test_observe_histogram(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.observe("latency_ms", value=100.0)
        mc.observe("latency_ms", value=200.0)
        mc.observe("latency_ms", value=150.0)
        hist = mc.get_histogram("latency_ms")
        assert hist == [100.0, 200.0, 150.0]

    def test_pending_count(self) -> None:
        mc = MetricsCollector(session_id="s1")
        assert mc.pending_count() == 0
        mc.increment("c")
        mc.gauge("g", value=1.0)
        mc.observe("h", value=2.0)
        assert mc.pending_count() == 3

    def test_drain_pending(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("c1")
        mc.gauge("g1", value=5.0)
        drained = mc.drain_pending()
        assert len(drained) == 2
        assert mc.pending_count() == 0
        assert all(isinstance(e, MetricEnvelope) for e in drained)

    def test_snapshot(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("c1", value=3.0)
        mc.gauge("g1", value=7.7)
        mc.observe("h1", value=10.0)
        mc.observe("h1", value=20.0)
        snap = mc.snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert "histograms" in snap
        assert snap["counters"][_label_key("c1")] == 3.0
        assert snap["gauges"][_label_key("g1")] == 7.7
        assert snap["histograms"][_label_key("h1")] == [10.0, 20.0]

    def test_session_id_property(self) -> None:
        mc = MetricsCollector(session_id="abc")
        assert mc.session_id == "abc"

    def test_turn_number_property(self) -> None:
        mc = MetricsCollector(session_id="s1")
        assert mc.turn_number == 0
        mc.turn_number = 5
        assert mc.turn_number == 5

    def test_disabled_collector_no_ops(self) -> None:
        mc = MetricsCollector(session_id="s1", enabled=False)
        mc.increment("c1")
        mc.gauge("g1", value=1.0)
        mc.observe("h1", value=1.0)
        assert mc.get_counter("c1") == 0.0
        assert mc.get_gauge("g1") == 0.0
        assert mc.get_histogram("h1") == []
        assert mc.pending_count() == 0

    def test_enable_disable_toggle(self) -> None:
        mc = MetricsCollector(session_id="s1", enabled=False)
        mc.increment("c1")
        assert mc.get_counter("c1") == 0.0
        mc.enabled = True
        mc.increment("c1")
        assert mc.get_counter("c1") == 1.0

    def test_reset(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("c")
        mc.gauge("g", value=1.0)
        mc.observe("h", value=2.0)
        mc.turn_number = 3
        mc.reset()
        assert mc.get_counter("c") == 0.0
        assert mc.get_gauge("g") == 0.0
        assert mc.get_histogram("h") == []
        assert mc.pending_count() == 0
        assert mc.turn_number == 0

    def test_get_counter_value_alias(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("c1", value=3.0)
        assert mc.get_counter_value("c1") == mc.get_counter("c1")

    def test_get_nonexistent_counter_zero(self) -> None:
        mc = MetricsCollector(session_id="s1")
        assert mc.get_counter("does.not.exist") == 0.0

    def test_get_nonexistent_gauge_zero(self) -> None:
        mc = MetricsCollector(session_id="s1")
        assert mc.get_gauge("does.not.exist") == 0.0

    def test_get_nonexistent_histogram_empty(self) -> None:
        mc = MetricsCollector(session_id="s1")
        assert mc.get_histogram("does.not.exist") == []

    def test_envelopes_carry_session_id(self) -> None:
        mc = MetricsCollector(session_id="s42")
        mc.increment("c1")
        drained = mc.drain_pending()
        assert drained[0].session_id == "s42"

    def test_envelopes_carry_turn_number(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.turn_number = 7
        mc.gauge("g1", value=1.0)
        drained = mc.drain_pending()
        assert drained[0].turn_number == 7

    def test_envelopes_carry_source_event_id(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("c1", source_event_id=99)
        drained = mc.drain_pending()
        assert drained[0].source_event_id == 99

    def test_emit_all_no_bus_returns_zero(self) -> None:
        mc = MetricsCollector(session_id="s1", bus=None)
        mc.increment("c1")
        assert mc.emit_all() == 0

    def test_emit_all_with_bus(self) -> None:
        bus = MagicMock()
        mc = MetricsCollector(session_id="s1", bus=bus)
        mc.increment("c1")
        mc.gauge("g1", value=1.0)

        with patch("poc.k1_poc.bus.builders.build_metric_emitted") as mock_builder:
            mock_builder.return_value = MagicMock()
            count = mc.emit_all()
            assert count == 2
            assert bus.publish.call_count == 2
            assert mc.pending_count() == 0

    def test_emit_all_handles_builder_error(self) -> None:
        bus = MagicMock()
        mc = MetricsCollector(session_id="s1", bus=bus)
        mc.increment("c1")

        with patch(
            "poc.k1_poc.bus.builders.build_metric_emitted", side_effect=RuntimeError("boom")
        ):
            count = mc.emit_all()
            assert count == 0
            assert mc.pending_count() == 0  # cleared anyway


# =====================================================================
# 11.1.2 -- SlidingWindow
# =====================================================================


class TestSlidingWindow:
    """SlidingWindow time-based eviction and statistical operations."""

    def test_add_and_count(self) -> None:
        sw = SlidingWindow(window_size_ms=10_000)
        now = _now_ms()
        sw.add(1.0, now)
        sw.add(2.0, now + 100)
        sw.add(3.0, now + 200)
        assert sw.count() == 3

    def test_eviction(self) -> None:
        sw = SlidingWindow(window_size_ms=1000)
        base = _now_ms()
        sw.add(1.0, base)
        sw.add(2.0, base + 500)
        sw.add(3.0, base + 1500)  # this evicts base entry (1500 - 1000 = 500 cutoff)
        # After adding ts=1500, entries with ts < 500 are evicted
        # base(=base) < base+500 -- base gets evicted
        vals = sw.values()
        assert 2.0 in vals
        assert 3.0 in vals

    def test_empty_window(self) -> None:
        sw = SlidingWindow(window_size_ms=1000)
        assert sw.count() == 0
        assert sw.is_empty()
        assert sw.sum() == 0.0
        assert sw.mean() == 0.0
        assert sw.p50() == 0.0
        assert sw.p95() == 0.0
        assert sw.p99() == 0.0
        assert sw.rate() == 0.0

    def test_sum(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        now = _now_ms()
        sw.add(10.0, now)
        sw.add(20.0, now + 1)
        sw.add(30.0, now + 2)
        assert sw.sum() == 60.0

    def test_mean(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        now = _now_ms()
        for v in [10.0, 20.0, 30.0]:
            sw.add(v, now)
            now += 1
        assert sw.mean() == 20.0

    def test_percentile_p50(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        now = _now_ms()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
            sw.add(v, now)
            now += 1
        p50 = sw.p50()
        # nearest rank: index 5 of sorted 10 elements = 6.0
        assert p50 == 6.0

    def test_percentile_p95(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        now = _now_ms()
        for i in range(100):
            sw.add(float(i), now + i)
        p95 = sw.p95()
        assert p95 >= 90.0  # should be around 95

    def test_percentile_p99(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        now = _now_ms()
        for i in range(100):
            sw.add(float(i), now + i)
        p99 = sw.p99()
        assert p99 >= 95.0

    def test_rate(self) -> None:
        sw = SlidingWindow(window_size_ms=10_000)
        now = _now_ms()
        # Add 10 events in a 10-second window
        for i in range(10):
            sw.add(1.0, now + i)
        r = sw.rate(per_seconds=1.0)
        # 10 events / 10 seconds = 1.0 per second
        assert r == pytest.approx(1.0, abs=0.01)

    def test_rate_per_minute(self) -> None:
        sw = SlidingWindow(window_size_ms=10_000)
        now = _now_ms()
        for i in range(10):
            sw.add(1.0, now + i)
        r = sw.rate(per_seconds=60.0)
        assert r == pytest.approx(60.0, abs=0.5)

    def test_clear(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        sw.add(1.0)
        sw.add(2.0)
        sw.clear()
        assert sw.is_empty()
        assert sw.count() == 0

    def test_window_size_property(self) -> None:
        sw = SlidingWindow(window_size_ms=5000)
        assert sw.window_size_ms == 5000

    def test_values_returns_copy(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        now = _now_ms()
        sw.add(1.0, now)
        vals = sw.values()
        vals.append(999.0)  # mutate the returned list
        assert sw.count() == 1  # original unaffected

    def test_auto_timestamp(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        sw.add(42.0)  # no explicit ts
        assert sw.count() == 1

    def test_percentile_single_value(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        sw.add(7.7)
        assert sw.p50() == 7.7
        assert sw.p95() == 7.7
        assert sw.p99() == 7.7

    def test_percentile_boundary_zero(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        sw.add(5.0)
        sw.add(10.0)
        p0 = sw.percentile(0.0)
        assert p0 == 5.0  # min value

    def test_percentile_boundary_one(self) -> None:
        sw = SlidingWindow(window_size_ms=60_000)
        sw.add(5.0)
        sw.add(10.0)
        p100 = sw.percentile(1.0)
        assert p100 == 10.0  # max value


# =====================================================================
# 11.1.2 -- MetricAggregator
# =====================================================================


class TestMetricAggregator:
    """MetricAggregator sliding window aggregation tests."""

    def test_record_from_envelope(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        env = MetricEnvelope(
            metric_name="test.counter",
            metric_type="counter",
            value=1.0,
            timestamp_ms=_now_ms(),
        )
        agg.record(env)
        assert agg.total_recorded == 1
        assert agg.count("test.counter") == 1

    def test_record_from_dict(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        agg.record(
            {
                "metric_name": "test.dict",
                "metric_type": "counter",
                "value": 2.0,
                "timestamp_ms": _now_ms(),
            }
        )
        assert agg.total_recorded == 1
        assert agg.count("test.dict") == 1

    def test_rate_calculation(self) -> None:
        agg = MetricAggregator(window_size_s=10.0)
        now = _now_ms()
        for i in range(10):
            agg.record(
                MetricEnvelope(
                    metric_name="events",
                    metric_type="counter",
                    value=1.0,
                    timestamp_ms=now + i,
                )
            )
        rate = agg.rate("events", per_seconds=1.0)
        # 10 events / 10 seconds = 1.0/s
        assert rate == pytest.approx(1.0, abs=0.01)

    def test_percentile_calculation(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        now = _now_ms()
        for i in range(100):
            agg.record(
                MetricEnvelope(
                    metric_name="latency",
                    metric_type="histogram",
                    value=float(i),
                    timestamp_ms=now + i,
                )
            )
        p95 = agg.percentile("latency", p=0.95)
        assert p95 >= 90.0

    def test_count_by_labels(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        now = _now_ms()
        agg.record(
            MetricEnvelope(
                metric_name="count",
                metric_type="counter",
                value=1.0,
                labels={"mode": "A"},
                timestamp_ms=now,
            )
        )
        agg.record(
            MetricEnvelope(
                metric_name="count",
                metric_type="counter",
                value=1.0,
                labels={"mode": "B"},
                timestamp_ms=now,
            )
        )
        assert agg.count("count", {"mode": "A"}) == 1
        assert agg.count("count", {"mode": "B"}) == 1
        assert agg.count("count", {"mode": "C"}) == 0

    def test_latest_gauge(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        now = _now_ms()
        agg.record(
            MetricEnvelope(
                metric_name="util",
                metric_type="gauge",
                value=0.5,
                timestamp_ms=now,
            )
        )
        agg.record(
            MetricEnvelope(
                metric_name="util",
                metric_type="gauge",
                value=0.9,
                timestamp_ms=now + 100,
            )
        )
        assert agg.latest_gauge("util") == 0.9

    def test_latest_gauge_nonexistent(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        assert agg.latest_gauge("nope") == 0.0

    def test_get_window(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        now = _now_ms()
        agg.record(
            MetricEnvelope(
                metric_name="w",
                metric_type="counter",
                value=1.0,
                timestamp_ms=now,
            )
        )
        win = agg.get_window("w")
        assert win is not None
        assert isinstance(win, SlidingWindow)
        assert win.count() == 1

    def test_get_window_nonexistent(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        assert agg.get_window("nope") is None

    def test_summary(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        now = _now_ms()
        for i in range(10):
            agg.record(
                MetricEnvelope(
                    metric_name="s",
                    metric_type="histogram",
                    value=float(i * 10),
                    timestamp_ms=now + i,
                )
            )
        summary = agg.summary()
        key = _label_key("s")
        assert key in summary
        assert summary[key]["count"] == 10
        assert summary[key]["mean"] > 0
        assert "p50" in summary[key]
        assert "p95" in summary[key]
        assert "p99" in summary[key]
        assert "rate_per_s" in summary[key]

    def test_summary_empty(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        assert agg.summary() == {}

    def test_reset(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        agg.record(
            MetricEnvelope(
                metric_name="r",
                metric_type="counter",
                value=1.0,
                timestamp_ms=_now_ms(),
            )
        )
        assert agg.total_recorded == 1
        agg.reset()
        assert agg.total_recorded == 0
        assert agg.count("r") == 0
        assert agg.summary() == {}

    def test_window_size_property(self) -> None:
        agg = MetricAggregator(window_size_s=60.0)
        assert agg.window_size_ms == 60_000

    def test_rate_nonexistent_metric(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        assert agg.rate("nope") == 0.0

    def test_percentile_nonexistent_metric(self) -> None:
        agg = MetricAggregator(window_size_s=300.0)
        assert agg.percentile("nope") == 0.0


# =====================================================================
# 11.2.4 -- TurnTimer
# =====================================================================


class TestTurnTimer:
    """TurnTimer per-phase latency breakdown tests."""

    def test_total_ms(self) -> None:
        tt = TurnTimer(
            turn_number=1,
            total_start_ms=1000,
            total_end_ms=2000,
        )
        assert tt.total_ms == 1000

    def test_phase1_ms(self) -> None:
        tt = TurnTimer(phase1_start_ms=100, phase1_end_ms=120)
        assert tt.phase1_ms == 20

    def test_arbiter_ms(self) -> None:
        tt = TurnTimer(arbiter_start_ms=200, arbiter_end_ms=201)
        assert tt.arbiter_ms == 1

    def test_front_ms(self) -> None:
        tt = TurnTimer(front_start_ms=300, front_end_ms=800)
        assert tt.front_ms == 500

    def test_fsm_routing_ms(self) -> None:
        tt = TurnTimer(fsm_routing_start_ms=800, fsm_routing_end_ms=801)
        assert tt.fsm_routing_ms == 1

    def test_back_ms(self) -> None:
        tt = TurnTimer(back_start_ms=900, back_end_ms=5900)
        assert tt.back_ms == 5000

    def test_zero_when_not_set(self) -> None:
        tt = TurnTimer()
        assert tt.total_ms == 0
        assert tt.phase1_ms == 0
        assert tt.arbiter_ms == 0
        assert tt.front_ms == 0
        assert tt.fsm_routing_ms == 0
        assert tt.back_ms == 0

    def test_to_breakdown(self) -> None:
        tt = TurnTimer(
            turn_number=3,
            total_start_ms=1000,
            total_end_ms=6000,
            phase1_start_ms=1000,
            phase1_end_ms=1020,
            arbiter_start_ms=1020,
            arbiter_end_ms=1021,
            front_start_ms=1021,
            front_end_ms=1521,
            fsm_routing_start_ms=1521,
            fsm_routing_end_ms=1522,
            back_start_ms=1522,
            back_end_ms=5500,
            weave_decision_ms=2,
            weave_delivery_ms=498,
        )
        breakdown = tt.to_breakdown()
        assert breakdown["turn_number"] == 3
        assert breakdown["total_ms"] == 5000
        assert breakdown["phase1_ms"] == 20
        assert breakdown["arbiter_ms"] == 1
        assert breakdown["front_ms"] == 500
        assert breakdown["fsm_routing_ms"] == 1
        assert breakdown["back_ms"] == 3978
        assert breakdown["weave_decision_ms"] == 2
        assert breakdown["weave_delivery_ms"] == 498
        # raw timestamps also present
        assert breakdown["total_start_ms"] == 1000
        assert breakdown["total_end_ms"] == 6000

    def test_emit(self) -> None:
        mc = MetricsCollector(session_id="s1")
        tt = TurnTimer(
            turn_number=1,
            total_start_ms=100,
            total_end_ms=200,
            phase1_start_ms=100,
            phase1_end_ms=120,
            front_start_ms=120,
            front_end_ms=180,
            weave_decision_ms=5,
        )
        tt.emit(mc)
        # Should have emitted total, phase1, front, weave_decision
        drained = mc.drain_pending()
        names = [e.metric_name for e in drained]
        assert "turn.total_latency_ms" in names
        assert "turn.phase1_latency_ms" in names
        assert "turn.front_latency_ms" in names
        assert "turn.weave_decision_latency_ms" in names
        # arbiter/back/fsm_routing not set, should not be emitted
        assert "turn.arbiter_latency_ms" not in names
        assert "turn.back_latency_ms" not in names
        assert "turn.fsm_routing_latency_ms" not in names

    def test_emit_disabled_collector(self) -> None:
        mc = MetricsCollector(session_id="s1", enabled=False)
        tt = TurnTimer(total_start_ms=100, total_end_ms=200)
        tt.emit(mc)
        assert mc.pending_count() == 0

    def test_emit_labels_contain_turn(self) -> None:
        mc = MetricsCollector(session_id="s1")
        tt = TurnTimer(turn_number=5, total_start_ms=100, total_end_ms=200)
        tt.emit(mc)
        drained = mc.drain_pending()
        for e in drained:
            assert e.labels.get("turn") == "5"


# =====================================================================
# 11.1.3 -- Bus Topics and Builders
# =====================================================================


class TestMetricBusTopics:
    """Metric bus topic registration and builder correctness."""

    def test_topics_in_all_topics(self) -> None:
        from poc.k1_poc.bus.topics import (
            ALL_TOPICS,
            TOPIC_METRIC_ALERT,
            TOPIC_METRIC_EMITTED,
            TOPIC_METRIC_SESSION_SUMMARY,
        )

        assert TOPIC_METRIC_EMITTED in ALL_TOPICS
        assert TOPIC_METRIC_ALERT in ALL_TOPICS
        assert TOPIC_METRIC_SESSION_SUMMARY in ALL_TOPICS

    def test_topics_are_relaxed(self) -> None:
        from poc.k1_poc.bus.topics import (
            RELAXED_TOPICS,
            TOPIC_METRIC_ALERT,
            TOPIC_METRIC_EMITTED,
            TOPIC_METRIC_SESSION_SUMMARY,
        )

        assert TOPIC_METRIC_EMITTED in RELAXED_TOPICS
        assert TOPIC_METRIC_ALERT in RELAXED_TOPICS
        assert TOPIC_METRIC_SESSION_SUMMARY in RELAXED_TOPICS

    def test_topics_not_strict(self) -> None:
        from poc.k1_poc.bus.topics import (
            STRICT_TOPICS,
            TOPIC_METRIC_ALERT,
            TOPIC_METRIC_EMITTED,
            TOPIC_METRIC_SESSION_SUMMARY,
        )

        assert TOPIC_METRIC_EMITTED not in STRICT_TOPICS
        assert TOPIC_METRIC_ALERT not in STRICT_TOPICS
        assert TOPIC_METRIC_SESSION_SUMMARY not in STRICT_TOPICS

    def test_topic_strings(self) -> None:
        from poc.k1_poc.bus.topics import (
            TOPIC_METRIC_ALERT,
            TOPIC_METRIC_EMITTED,
            TOPIC_METRIC_SESSION_SUMMARY,
        )

        assert TOPIC_METRIC_EMITTED == "k1.metrics.emitted.v1"
        assert TOPIC_METRIC_ALERT == "k1.metrics.alert.v1"
        assert TOPIC_METRIC_SESSION_SUMMARY == "k1.metrics.session_summary.v1"

    def test_topic_priority_background(self) -> None:
        from poc.k1_poc.bus.topics import (
            TOPIC_METRIC_ALERT,
            TOPIC_METRIC_EMITTED,
            TOPIC_METRIC_SESSION_SUMMARY,
            get_priority,
        )

        assert get_priority(TOPIC_METRIC_EMITTED) == 3  # BACKGROUND
        assert get_priority(TOPIC_METRIC_ALERT) == 3
        assert get_priority(TOPIC_METRIC_SESSION_SUMMARY) == 3


class TestMetricBuilders:
    """Builder functions for metric bus topics."""

    def test_build_metric_emitted(self) -> None:
        from poc.k1_poc.bus.builders import build_metric_emitted
        from poc.k1_poc.bus.topics import TOPIC_METRIC_EMITTED

        env = build_metric_emitted(
            payload={"metric_name": "test", "metric_type": "counter", "value": 1.0},
            parent_id=0,
        )
        assert env.topic == TOPIC_METRIC_EMITTED

    def test_build_metric_alert(self) -> None:
        from poc.k1_poc.bus.builders import build_metric_alert
        from poc.k1_poc.bus.topics import TOPIC_METRIC_ALERT

        env = build_metric_alert(
            payload={"rule": "high_degenerate_rate", "value": 0.5, "threshold": 0.3},
            parent_id=0,
        )
        assert env.topic == TOPIC_METRIC_ALERT

    def test_build_metric_session_summary(self) -> None:
        from poc.k1_poc.bus.builders import build_metric_session_summary
        from poc.k1_poc.bus.topics import TOPIC_METRIC_SESSION_SUMMARY

        env = build_metric_session_summary(
            payload={"session_id": "s1", "total_turns": 5},
            parent_id=0,
        )
        assert env.topic == TOPIC_METRIC_SESSION_SUMMARY

    def test_builders_in_registry(self) -> None:
        from poc.k1_poc.bus.builders import BUILDERS
        from poc.k1_poc.bus.topics import (
            TOPIC_METRIC_ALERT,
            TOPIC_METRIC_EMITTED,
            TOPIC_METRIC_SESSION_SUMMARY,
        )

        assert TOPIC_METRIC_EMITTED in BUILDERS
        assert TOPIC_METRIC_ALERT in BUILDERS
        assert TOPIC_METRIC_SESSION_SUMMARY in BUILDERS


# =====================================================================
# Helpers & emit_metric
# =====================================================================


class TestLabelKey:
    """_label_key canonical key generation."""

    def test_no_labels(self) -> None:
        assert _label_key("metric") == "metric{}"

    def test_with_labels(self) -> None:
        key = _label_key("m", {"b": "2", "a": "1"})
        assert key == "m{a=1,b=2}"  # sorted

    def test_empty_labels_same_as_none(self) -> None:
        assert _label_key("m", {}) == _label_key("m", None)


class TestEmitMetric:
    """emit_metric convenience function."""

    def test_emit_counter(self) -> None:
        mc = MetricsCollector(session_id="s1")
        emit_metric(mc, "c", "counter", 3.0)
        assert mc.get_counter("c") == 3.0

    def test_emit_gauge(self) -> None:
        mc = MetricsCollector(session_id="s1")
        emit_metric(mc, "g", "gauge", 7.0)
        assert mc.get_gauge("g") == 7.0

    def test_emit_histogram(self) -> None:
        mc = MetricsCollector(session_id="s1")
        emit_metric(mc, "h", "histogram", 42.0)
        assert mc.get_histogram("h") == [42.0]

    def test_emit_summary(self) -> None:
        mc = MetricsCollector(session_id="s1")
        emit_metric(mc, "s", "summary", 99.0)
        assert mc.get_histogram("s") == [99.0]

    def test_emit_unknown_type(self) -> None:
        mc = MetricsCollector(session_id="s1")
        emit_metric(mc, "x", "bogus", 1.0)
        assert mc.pending_count() == 0


class TestBuildSessionSummary:
    """build_session_summary function tests."""

    def test_basic_summary(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.increment("c1", value=5.0)
        mc.gauge("g1", value=2.5)
        agg = MetricAggregator()
        summary = build_session_summary(mc, agg, session_id="s1", total_turns=3, total_tasks=2)
        assert summary["session_id"] == "s1"
        assert summary["total_turns"] == 3
        assert summary["total_tasks"] == 2
        assert "counters" in summary
        assert "gauges" in summary
        assert "aggregated" in summary

    def test_summary_uses_collector_session_id(self) -> None:
        mc = MetricsCollector(session_id="s42")
        agg = MetricAggregator()
        summary = build_session_summary(mc, agg)
        assert summary["session_id"] == "s42"

    def test_summary_with_aggregated_data(self) -> None:
        mc = MetricsCollector(session_id="s1")
        agg = MetricAggregator(window_size_s=300.0)
        now = _now_ms()
        for i in range(5):
            agg.record(
                MetricEnvelope(
                    metric_name="lat",
                    metric_type="histogram",
                    value=float(i * 10),
                    timestamp_ms=now + i,
                )
            )
        summary = build_session_summary(mc, agg, session_id="s1")
        assert len(summary["aggregated"]) > 0


# =====================================================================
# 11.1.1 & 11.1.2 -- Package import test
# =====================================================================


class TestObsPackageImport:
    """Verify obs package exports all expected symbols."""

    def test_import_from_obs(self) -> None:
        from poc.k1_poc.obs import (
            MetricAggregator,
            MetricEnvelope,
            MetricsCollector,
            SlidingWindow,
            TurnTimer,
        )

        assert MetricEnvelope is not None
        assert MetricsCollector is not None
        assert MetricAggregator is not None
        assert SlidingWindow is not None
        assert TurnTimer is not None
