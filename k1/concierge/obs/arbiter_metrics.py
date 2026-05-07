"""
k1.concierge.obs.arbiter_metrics -- Arbiter decision distribution metrics.

M11 Stub -- placeholder for Arbiter telemetry subscriber.

ArbiterMetricsSubscriber records:
    - Decision counts per outcome (approve, reject, defer)
    - Decision latency histogram
    - Policy violation counters

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from k1.concierge.obs.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class ArbiterMetricsSubscriber:
    """Subscribes to Arbiter decision events and emits distribution metrics.

    Stub implementation -- production will wire to bus Arbiter event topics.
    """

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector

    def on_decision(
        self,
        outcome: str,
        latency_ms: float = 0.0,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Record an Arbiter decision event.

        Args:
            outcome: Decision outcome (approve, reject, defer).
            latency_ms: Decision latency in milliseconds.
            labels: Additional filtering labels.
        """
        if not self._collector or not self._collector.enabled:
            return
        metric_labels = {"outcome": outcome}
        if labels:
            metric_labels.update({k: str(v) for k, v in labels.items()})
        self._collector.increment("arbiter.decision.count", metric_labels)
        if latency_ms > 0:
            self._collector.observe("arbiter.decision.latency_ms", metric_labels, value=latency_ms)
