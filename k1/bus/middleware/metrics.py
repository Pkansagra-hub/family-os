"""
k1.bus.middleware.metrics -- Prometheus metrics middleware.

Tracks bus envelope throughput and latency using Prometheus counters
and histograms.  Metrics are labeled by topic prefix (first two segments)
to avoid high-cardinality explosions from full topic strings.

Graceful degradation: if ``prometheus_client`` is not installed, the
middleware becomes a no-op pass-through.  Zero overhead when disabled.

Metrics exported:
    k1_bus_envelopes_total          Counter   {topic_prefix, priority}
    k1_bus_envelope_latency_seconds Histogram {topic_prefix}
        (latency = time from envelope.created_ns to middleware processing)

Usage::

    from k1.bus.middleware.metrics import MetricsMiddleware

    # Auto-detects prometheus_client availability
    mw = MetricsMiddleware()

    # Custom metric prefix
    mw = MetricsMiddleware(prefix="k1_custom_bus")

    # Force disabled (testing)
    mw = MetricsMiddleware(enabled=False)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from k1.bus.envelope import Envelope, Priority

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Prometheus import (graceful degradation)
# ---------------------------------------------------------------------------

_HAS_PROMETHEUS = False
_Counter: Any = None
_Histogram: Any = None

try:
    from prometheus_client import Counter as _PromCounter
    from prometheus_client import Histogram as _PromHistogram

    _Counter = _PromCounter
    _Histogram = _PromHistogram
    _HAS_PROMETHEUS = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Priority label mapping
# ---------------------------------------------------------------------------

_PRIORITY_LABELS = {
    Priority.URGENT: "urgent",
    Priority.REALTIME: "realtime",
    Priority.INTERACTIVE: "interactive",
    Priority.BACKGROUND: "background",
}


def _topic_prefix(topic: str) -> str:
    """
    Extract the topic prefix (first two segments) for metric labeling.

    Examples:
        "k1.capability.completed.v1" -> "k1.capability"
        "k1.agent.abc.delta.v1"      -> "k1.agent"
        "k1"                         -> "k1"
        ""                           -> "unknown"
    """
    if not topic:
        return "unknown"
    parts = topic.split(".", 2)
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return parts[0]


class MetricsMiddleware:
    """
    Prometheus metrics middleware for the K1 bus.

    Increments a counter for every published envelope and records
    envelope processing latency in a histogram.  Both are labeled by
    topic prefix to keep cardinality bounded.

    When ``prometheus_client`` is not installed or metrics are explicitly
    disabled, ``process()`` returns the envelope unchanged with zero overhead.

    Thread-safe: Prometheus metrics objects are inherently thread-safe.
    """

    __slots__ = ("_enabled", "_counter", "_histogram")

    def __init__(
        self,
        *,
        prefix: str = "k1_bus",
        enabled: bool = True,
    ) -> None:
        """
        Create a MetricsMiddleware.

        Args:
            prefix:  Metric name prefix (default "k1_bus").
            enabled: If False, metrics are completely disabled regardless
                     of whether prometheus_client is installed.
        """
        self._enabled = enabled and _HAS_PROMETHEUS
        self._counter: Any = None
        self._histogram: Any = None

        if self._enabled and _Counter is not None:
            self._counter = _Counter(
                f"{prefix}_envelopes_total",
                "Total envelopes published through the K1 bus",
                ["topic_prefix", "priority"],
            )
            self._histogram = _Histogram(
                f"{prefix}_envelope_latency_seconds",
                "Envelope processing latency (publish to middleware)",
                ["topic_prefix"],
                buckets=(
                    0.0001,  # 100us
                    0.0005,  # 500us
                    0.001,  # 1ms
                    0.005,  # 5ms
                    0.01,  # 10ms
                    0.05,  # 50ms
                    0.1,  # 100ms
                    0.5,  # 500ms
                    1.0,  # 1s
                ),
            )

    def process(self, envelope: Envelope) -> Optional[Envelope]:
        """
        Record metrics for the envelope and return it unchanged.

        Never drops envelopes (always returns the envelope).
        Never reads payload.

        Args:
            envelope: Stamped bus envelope.

        Returns:
            The same envelope, unchanged.
        """
        if not self._enabled:
            return envelope

        prefix = _topic_prefix(envelope.topic)
        try:
            priority_label = _PRIORITY_LABELS[Priority(envelope.priority)]
        except (ValueError, KeyError):
            priority_label = f"unknown_{envelope.priority}"

        # Increment envelope counter
        self._counter.labels(
            topic_prefix=prefix,
            priority=priority_label,
        ).inc()

        # Record latency (created_ns is monotonic nanoseconds from time.monotonic_ns)
        if envelope.created_ns > 0:
            now_ns = time.monotonic_ns()
            latency_s = (now_ns - envelope.created_ns) / 1_000_000_000
            if latency_s >= 0:
                self._histogram.labels(topic_prefix=prefix).observe(latency_s)

        return envelope

    @property
    def enabled(self) -> bool:
        """True if metrics collection is active."""
        return self._enabled

    def __repr__(self) -> str:
        state = "enabled" if self._enabled else "disabled"
        return f"MetricsMiddleware({state})"


__all__ = ["MetricsMiddleware", "_topic_prefix"]
