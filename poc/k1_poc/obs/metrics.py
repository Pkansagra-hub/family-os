"""
poc.k1_poc.obs.metrics -- MetricEnvelope, MetricsCollector, MetricAggregator, TurnTimer.

M11 E11.1.1-11.1.2, E11.2.4

Unified metrics emission and aggregation layer for all K1 subsystems.
Each subsystem emits metrics through MetricsCollector. MetricAggregator
subscribes to metric events and maintains sliding window aggregations
for alert evaluation and dashboard queries.

Metric naming convention: {subsystem}.{component}.{metric_name}
    Examples: react_loop.front.degenerate_count
              backpool.worker.utilization
              phase1.ultrabert.latency_ms

Standard labels:
    session_id  -- always present
    turn_number -- when applicable
    actor       -- "front" / "back" / "fsm" / "phase1"
    mode        -- PromptMode value (Front metrics)
    tier        -- ComplexityTier value (Back metrics)

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================================
# MetricEnvelope -- standardized metric payload (11.1.1)
# =====================================================================


@dataclass(frozen=True)
class MetricEnvelope:
    """Standardized metric payload for all K1 subsystems.

    JSON-serializable. Carries a single metric observation with
    labels for filtering and aggregation.

    Attributes:
        metric_name: Dot-separated metric identifier.
            Convention: {subsystem}.{component}.{metric_name}
        metric_type: One of "counter", "gauge", "histogram", "summary".
        value: Numeric metric value.
        labels: Key-value pairs for filtering (mode, tier, actor, etc.).
        session_id: Session this metric belongs to.
        turn_number: Turn number (0 if not applicable).
        timestamp_ms: Epoch milliseconds when metric was recorded.
        source_event_id: Originating bus event envelope_id (optional).
    """

    metric_name: str
    metric_type: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    session_id: str = ""
    turn_number: int = 0
    timestamp_ms: int = 0
    source_event_id: int | None = None

    def __post_init__(self) -> None:
        if self.metric_type not in ("counter", "gauge", "histogram", "summary"):
            raise ValueError(
                f"Invalid metric_type: {self.metric_type!r}. "
                "Must be counter, gauge, histogram, or summary."
            )
        if self.timestamp_ms == 0:
            # Frozen dataclass -- use object.__setattr__ for post-init
            object.__setattr__(self, "timestamp_ms", _now_ms())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "metric_name": self.metric_name,
            "metric_type": self.metric_type,
            "value": self.value,
            "labels": dict(self.labels),
            "session_id": self.session_id,
            "turn_number": self.turn_number,
            "timestamp_ms": self.timestamp_ms,
            "source_event_id": self.source_event_id,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricEnvelope:
        """Deserialize from dict."""
        return cls(
            metric_name=data["metric_name"],
            metric_type=data["metric_type"],
            value=data["value"],
            labels=data.get("labels", {}),
            session_id=data.get("session_id", ""),
            turn_number=data.get("turn_number", 0),
            timestamp_ms=data.get("timestamp_ms", 0),
            source_event_id=data.get("source_event_id"),
        )


# =====================================================================
# MetricsCollector -- per-session metric emission (11.1.1)
# =====================================================================


class MetricsCollector:
    """Per-session metrics collector with counter, gauge, histogram support.

    All K1 subsystems emit metrics through this collector. The collector
    maintains in-memory state and optionally publishes MetricEnvelopes
    to the bus via emit_all().

    Thread-safety: Single-threaded asyncio. No locks needed.
    """

    def __init__(
        self,
        session_id: str = "",
        bus: Any | None = None,
        enabled: bool = True,
    ) -> None:
        self._session_id = session_id
        self._bus = bus
        self._enabled = enabled
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._pending: list[MetricEnvelope] = []
        self._turn_number: int = 0

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def turn_number(self) -> int:
        return self._turn_number

    @turn_number.setter
    def turn_number(self, value: int) -> None:
        self._turn_number = value

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    # -----------------------------------------------------------------
    # Counter: monotonically increasing value
    # -----------------------------------------------------------------

    def increment(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        value: float = 1.0,
        source_event_id: int | None = None,
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name (e.g., "react_loop.front.degenerate_count").
            labels: Filtering labels.
            value: Increment amount (default 1.0).
            source_event_id: Originating bus event ID.
        """
        if not self._enabled:
            return
        key = _label_key(name, labels)
        self._counters[key] = self._counters.get(key, 0.0) + value
        envelope = MetricEnvelope(
            metric_name=name,
            metric_type="counter",
            value=value,
            labels=labels or {},
            session_id=self._session_id,
            turn_number=self._turn_number,
            source_event_id=source_event_id,
        )
        self._pending.append(envelope)
        logger.debug("metric:increment %s=%s labels=%s", name, value, labels)

    # -----------------------------------------------------------------
    # Gauge: point-in-time value (can go up or down)
    # -----------------------------------------------------------------

    def gauge(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        value: float = 0.0,
        source_event_id: int | None = None,
    ) -> None:
        """Set a gauge metric.

        Args:
            name: Metric name (e.g., "backpool.utilization").
            labels: Filtering labels.
            value: Current gauge value.
            source_event_id: Originating bus event ID.
        """
        if not self._enabled:
            return
        key = _label_key(name, labels)
        self._gauges[key] = value
        envelope = MetricEnvelope(
            metric_name=name,
            metric_type="gauge",
            value=value,
            labels=labels or {},
            session_id=self._session_id,
            turn_number=self._turn_number,
            source_event_id=source_event_id,
        )
        self._pending.append(envelope)
        logger.debug("metric:gauge %s=%s labels=%s", name, value, labels)

    # -----------------------------------------------------------------
    # Histogram: distribution of observed values
    # -----------------------------------------------------------------

    def observe(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        value: float = 0.0,
        source_event_id: int | None = None,
    ) -> None:
        """Record an observation for a histogram metric.

        Args:
            name: Metric name (e.g., "react_loop.front.duration_ms").
            labels: Filtering labels.
            value: Observed value.
            source_event_id: Originating bus event ID.
        """
        if not self._enabled:
            return
        key = _label_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        envelope = MetricEnvelope(
            metric_name=name,
            metric_type="histogram",
            value=value,
            labels=labels or {},
            session_id=self._session_id,
            turn_number=self._turn_number,
            source_event_id=source_event_id,
        )
        self._pending.append(envelope)
        logger.debug("metric:observe %s=%s labels=%s", name, value, labels)

    # -----------------------------------------------------------------
    # Query: read current state
    # -----------------------------------------------------------------

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Return current counter value (cumulative)."""
        return self._counters.get(_label_key(name, labels), 0.0)

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Return current gauge value."""
        return self._gauges.get(_label_key(name, labels), 0.0)

    def get_histogram(self, name: str, labels: dict[str, str] | None = None) -> list[float]:
        """Return histogram observations list."""
        return list(self._histograms.get(_label_key(name, labels), []))

    def get_counter_value(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Alias for get_counter (compatibility)."""
        return self.get_counter(name, labels)

    # -----------------------------------------------------------------
    # Snapshot & Emission
    # -----------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all current metric state.

        Returns dict with "counters", "gauges", "histograms" keys.
        """
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: list(v) for k, v in self._histograms.items()},
        }

    def pending_count(self) -> int:
        """Number of pending metric envelopes not yet emitted."""
        return len(self._pending)

    def drain_pending(self) -> list[MetricEnvelope]:
        """Drain and return all pending envelopes."""
        envelopes = list(self._pending)
        self._pending.clear()
        return envelopes

    def emit_all(self) -> int:
        """Publish all pending MetricEnvelopes to bus.

        Returns number of envelopes published.
        """
        if not self._bus or not self._pending:
            return 0

        count = 0
        for envelope in self._pending:
            try:
                from poc.k1_poc.bus.builders import build_metric_emitted

                bus_env = build_metric_emitted(
                    payload=envelope.to_dict(),
                    parent_id=envelope.source_event_id or 0,
                )
                self._bus.publish(bus_env)
                count += 1
            except Exception:
                logger.debug("Failed to emit metric %s", envelope.metric_name, exc_info=True)
        self._pending.clear()
        logger.info("MetricsCollector.emit_all: published %d metric events", count)
        return count

    def reset(self) -> None:
        """Reset all metric state. Used in testing."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._pending.clear()
        self._turn_number = 0


# =====================================================================
# SlidingWindow -- time-windowed metric storage (11.1.2)
# =====================================================================


class SlidingWindow:
    """Time-windowed metric storage for aggregation.

    Stores (timestamp_ms, value) pairs in a deque. Evicts entries
    older than window_size_ms on every operation.

    Not thread-safe. Designed for single-threaded asyncio.
    """

    def __init__(self, window_size_ms: int = 300_000) -> None:
        self._window_size_ms = window_size_ms
        self._entries: deque[tuple[int, float]] = deque()

    @property
    def window_size_ms(self) -> int:
        return self._window_size_ms

    def add(self, value: float, ts_ms: int | None = None) -> None:
        """Add an observation with timestamp."""
        if ts_ms is None:
            ts_ms = _now_ms()
        self._entries.append((ts_ms, value))
        self._evict_stale(ts_ms)

    def _evict_stale(self, now_ms: int | None = None) -> None:
        """Remove entries older than the window."""
        if now_ms is None:
            now_ms = _now_ms()
        cutoff = now_ms - self._window_size_ms
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()

    def count(self) -> int:
        """Number of entries in window."""
        self._evict_stale()
        return len(self._entries)

    def values(self) -> list[float]:
        """Return all values in window (evicts stale first)."""
        self._evict_stale()
        return [v for _, v in self._entries]

    def sum(self) -> float:
        """Sum of values in window."""
        self._evict_stale()
        return sum(v for _, v in self._entries)

    def mean(self) -> float:
        """Mean of values in window. Returns 0.0 if empty."""
        self._evict_stale()
        if not self._entries:
            return 0.0
        return self.sum() / len(self._entries)

    def rate(self, per_seconds: float = 1.0) -> float:
        """Rate of events per per_seconds interval.

        Computed as count / window_size * per_seconds.
        """
        self._evict_stale()
        if not self._entries:
            return 0.0
        window_s = self._window_size_ms / 1000.0
        return len(self._entries) / window_s * per_seconds

    def percentile(self, p: float) -> float:
        """Compute p-th percentile (0.0-1.0) of values in window.

        Uses nearest-rank method. Returns 0.0 if empty.
        """
        self._evict_stale()
        if not self._entries:
            return 0.0
        vals = sorted(v for _, v in self._entries)
        rank = max(0, min(int(p * len(vals)), len(vals) - 1))
        return vals[rank]

    def p50(self) -> float:
        """50th percentile (median)."""
        return self.percentile(0.50)

    def p95(self) -> float:
        """95th percentile."""
        return self.percentile(0.95)

    def p99(self) -> float:
        """99th percentile."""
        return self.percentile(0.99)

    def is_empty(self) -> bool:
        """Whether the window has entries (after eviction)."""
        self._evict_stale()
        return len(self._entries) == 0

    def clear(self) -> None:
        """Remove all entries."""
        self._entries.clear()


# =====================================================================
# MetricAggregator -- sliding window aggregation (11.1.2)
# =====================================================================


class MetricAggregator:
    """Aggregates raw MetricEnvelope events into sliding window summaries.

    Subscribes to all k1.metrics.emitted.v1 bus events and auto-records
    into windows keyed by (metric_name, frozenset(labels.items())).

    Provides rate(), percentile(), and summary() queries for
    AlertEngine evaluation and dashboard consumption.
    """

    def __init__(self, window_size_s: float = 300.0) -> None:
        self._window_size_ms = int(window_size_s * 1000)
        self._windows: dict[str, SlidingWindow] = {}
        self._latest_gauges: dict[str, float] = {}
        self._total_recorded: int = 0

    @property
    def window_size_ms(self) -> int:
        return self._window_size_ms

    @property
    def total_recorded(self) -> int:
        return self._total_recorded

    def record(self, envelope: MetricEnvelope | dict[str, Any]) -> None:
        """Record a metric observation.

        Accepts MetricEnvelope or raw dict (from bus event payload).
        """
        if isinstance(envelope, dict):
            envelope = MetricEnvelope.from_dict(envelope)

        key = _label_key(envelope.metric_name, envelope.labels)
        if key not in self._windows:
            self._windows[key] = SlidingWindow(window_size_ms=self._window_size_ms)

        self._windows[key].add(envelope.value, ts_ms=envelope.timestamp_ms)
        self._total_recorded += 1

        # Track latest gauge value separately
        if envelope.metric_type == "gauge":
            self._latest_gauges[key] = envelope.value

    def rate(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
        per_seconds: float = 1.0,
    ) -> float:
        """Compute event rate for a metric in the sliding window."""
        key = _label_key(metric_name, labels)
        window = self._windows.get(key)
        if window is None:
            return 0.0
        return window.rate(per_seconds)

    def percentile(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
        p: float = 0.95,
    ) -> float:
        """Compute p-th percentile for a metric in the sliding window."""
        key = _label_key(metric_name, labels)
        window = self._windows.get(key)
        if window is None:
            return 0.0
        return window.percentile(p)

    def count(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
    ) -> int:
        """Count of observations in the sliding window."""
        key = _label_key(metric_name, labels)
        window = self._windows.get(key)
        if window is None:
            return 0
        return window.count()

    def latest_gauge(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Return the latest recorded gauge value."""
        key = _label_key(metric_name, labels)
        return self._latest_gauges.get(key, 0.0)

    def get_window(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
    ) -> SlidingWindow | None:
        """Return the raw SlidingWindow for a metric (for testing)."""
        return self._windows.get(_label_key(metric_name, labels))

    def summary(self) -> dict[str, Any]:
        """Return a summary of all tracked metrics.

        Returns dict keyed by label_key with count, mean, p50, p95, p99
        for each metric.
        """
        result: dict[str, Any] = {}
        for key, window in self._windows.items():
            if window.is_empty():
                continue
            result[key] = {
                "count": window.count(),
                "mean": round(window.mean(), 3),
                "sum": round(window.sum(), 3),
                "p50": round(window.p50(), 3),
                "p95": round(window.p95(), 3),
                "p99": round(window.p99(), 3),
                "rate_per_s": round(window.rate(), 6),
            }
        return result

    def reset(self) -> None:
        """Clear all windows and gauges."""
        self._windows.clear()
        self._latest_gauges.clear()
        self._total_recorded = 0


# =====================================================================
# TurnTimer -- per-phase latency breakdown (11.2.4)
# =====================================================================


@dataclass
class TurnTimer:
    """Per-turn latency breakdown across all processing phases.

    Instrumented by FSM controller at each phase boundary.
    Emitted at turn end as a structured metric event.

    All fields are epoch milliseconds. Duration = end - start.
    """

    turn_number: int = 0
    phase1_start_ms: int = 0
    phase1_end_ms: int = 0
    arbiter_start_ms: int = 0
    arbiter_end_ms: int = 0
    front_start_ms: int = 0
    front_end_ms: int = 0
    fsm_routing_start_ms: int = 0
    fsm_routing_end_ms: int = 0
    back_start_ms: int = 0
    back_end_ms: int = 0
    weave_decision_ms: int = 0
    weave_delivery_ms: int = 0
    total_start_ms: int = 0
    total_end_ms: int = 0

    @property
    def total_ms(self) -> int:
        """Total turn duration."""
        if self.total_end_ms and self.total_start_ms:
            return self.total_end_ms - self.total_start_ms
        return 0

    @property
    def phase1_ms(self) -> int:
        """Phase 1 classification duration."""
        if self.phase1_end_ms and self.phase1_start_ms:
            return self.phase1_end_ms - self.phase1_start_ms
        return 0

    @property
    def arbiter_ms(self) -> int:
        """Arbiter decision duration."""
        if self.arbiter_end_ms and self.arbiter_start_ms:
            return self.arbiter_end_ms - self.arbiter_start_ms
        return 0

    @property
    def front_ms(self) -> int:
        """Front LLM invocation duration."""
        if self.front_end_ms and self.front_start_ms:
            return self.front_end_ms - self.front_start_ms
        return 0

    @property
    def fsm_routing_ms(self) -> int:
        """FSM routing decision duration."""
        if self.fsm_routing_end_ms and self.fsm_routing_start_ms:
            return self.fsm_routing_end_ms - self.fsm_routing_start_ms
        return 0

    @property
    def back_ms(self) -> int:
        """Back LLM invocation duration."""
        if self.back_end_ms and self.back_start_ms:
            return self.back_end_ms - self.back_start_ms
        return 0

    def to_breakdown(self) -> dict[str, Any]:
        """Structured breakdown for bus emission and SS telemetry."""
        return {
            "turn_number": self.turn_number,
            "total_ms": self.total_ms,
            "phase1_ms": self.phase1_ms,
            "arbiter_ms": self.arbiter_ms,
            "front_ms": self.front_ms,
            "fsm_routing_ms": self.fsm_routing_ms,
            "back_ms": self.back_ms,
            "weave_decision_ms": self.weave_decision_ms,
            "weave_delivery_ms": self.weave_delivery_ms,
            "phase1_start_ms": self.phase1_start_ms,
            "phase1_end_ms": self.phase1_end_ms,
            "arbiter_start_ms": self.arbiter_start_ms,
            "arbiter_end_ms": self.arbiter_end_ms,
            "front_start_ms": self.front_start_ms,
            "front_end_ms": self.front_end_ms,
            "fsm_routing_start_ms": self.fsm_routing_start_ms,
            "fsm_routing_end_ms": self.fsm_routing_end_ms,
            "back_start_ms": self.back_start_ms,
            "back_end_ms": self.back_end_ms,
            "total_start_ms": self.total_start_ms,
            "total_end_ms": self.total_end_ms,
        }

    def emit(self, collector: MetricsCollector) -> None:
        """Emit all phase durations as individual histogram observations."""
        if not collector.enabled:
            return
        base_labels = {"turn": str(self.turn_number)}
        if self.total_ms:
            collector.observe("turn.total_latency_ms", base_labels, float(self.total_ms))
        if self.phase1_ms:
            collector.observe("turn.phase1_latency_ms", base_labels, float(self.phase1_ms))
        if self.arbiter_ms:
            collector.observe("turn.arbiter_latency_ms", base_labels, float(self.arbiter_ms))
        if self.front_ms:
            collector.observe("turn.front_latency_ms", base_labels, float(self.front_ms))
        if self.fsm_routing_ms:
            collector.observe(
                "turn.fsm_routing_latency_ms", base_labels, float(self.fsm_routing_ms)
            )
        if self.back_ms:
            collector.observe("turn.back_latency_ms", base_labels, float(self.back_ms))
        if self.weave_decision_ms:
            collector.observe(
                "turn.weave_decision_latency_ms", base_labels, float(self.weave_decision_ms)
            )
        if self.weave_delivery_ms:
            collector.observe(
                "turn.weave_delivery_latency_ms", base_labels, float(self.weave_delivery_ms)
            )


# =====================================================================
# Session Summary (11.5.3)
# =====================================================================


def build_session_summary(
    collector: MetricsCollector,
    aggregator: MetricAggregator,
    session_id: str = "",
    total_turns: int = 0,
    total_tasks: int = 0,
) -> dict[str, Any]:
    """Build a comprehensive session-end observability summary.

    Args:
        collector: MetricsCollector with accumulated state.
        aggregator: MetricAggregator with sliding window data.
        session_id: Session identifier.
        total_turns: Total turns in session.
        total_tasks: Total tasks dispatched.

    Returns:
        Dict suitable for bus emission as k1.metrics.session_summary.v1.
    """
    snap = collector.snapshot()
    agg_summary = aggregator.summary()
    return {
        "session_id": session_id or collector.session_id,
        "total_turns": total_turns,
        "total_tasks": total_tasks,
        "counters": snap["counters"],
        "gauges": snap["gauges"],
        "histogram_keys": list(snap["histograms"].keys()),
        "aggregated": agg_summary,
    }


# =====================================================================
# emit_metric helper (11.1.3)
# =====================================================================


def emit_metric(
    collector: MetricsCollector,
    name: str,
    metric_type: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Convenience: record metric via collector based on type.

    Routes to increment/gauge/observe based on metric_type.
    """
    if metric_type == "counter":
        collector.increment(name, labels, value)
    elif metric_type == "gauge":
        collector.gauge(name, labels, value)
    elif metric_type in ("histogram", "summary"):
        collector.observe(name, labels, value)
    else:
        logger.warning("emit_metric: unknown type %r for %s", metric_type, name)


# =====================================================================
# Helpers
# =====================================================================


def _label_key(name: str, labels: dict[str, str] | None = None) -> str:
    """Create a canonical key from metric name and sorted labels.

    Examples:
        _label_key("react_loop.front.count", {"mode": "STANDARD"})
        -> "react_loop.front.count{mode=STANDARD}"
        _label_key("bus.publish_count", None)
        -> "bus.publish_count{}"
    """
    if not labels:
        return f"{name}{{}}"
    sorted_labels = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{name}{{{sorted_labels}}}"


def _now_ms() -> int:
    """Current epoch milliseconds."""
    return int(time.time() * 1000)
