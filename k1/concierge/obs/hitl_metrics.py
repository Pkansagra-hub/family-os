"""
k1.concierge.obs.hitl_metrics -- HITL lifecycle dashboard metrics.

M11 Stub -- placeholder for HITL (Human-In-The-Loop) telemetry subscriber.

HITLMetricsSubscriber records:
    - HITL request count (by type: RELAY, RESOLVE, CONFIRM)
    - HITL response latency (user response time)
    - HITL timeout/abandon rate
    - Active HITL session gauge

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from k1.concierge.obs.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class HITLMetricsSubscriber:
    """Subscribes to HITL lifecycle events and emits dashboard metrics.

    Stub implementation -- production will wire to bus HITL event topics.
    """

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector

    def on_hitl_request(
        self,
        hitl_type: str,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Record a HITL request event.

        Args:
            hitl_type: HITL request type (RELAY, RESOLVE, CONFIRM).
            labels: Additional filtering labels.
        """
        if not self._collector or not self._collector.enabled:
            return
        metric_labels = {"hitl_type": hitl_type}
        if labels:
            metric_labels.update({k: str(v) for k, v in labels.items()})
        self._collector.increment("hitl.request.count", metric_labels)

    def on_hitl_response(
        self,
        hitl_type: str,
        latency_ms: float = 0.0,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Record a HITL response event.

        Args:
            hitl_type: HITL request type.
            latency_ms: User response time in milliseconds.
            labels: Additional filtering labels.
        """
        if not self._collector or not self._collector.enabled:
            return
        metric_labels = {"hitl_type": hitl_type}
        if labels:
            metric_labels.update({k: str(v) for k, v in labels.items()})
        self._collector.increment("hitl.response.count", metric_labels)
        if latency_ms > 0:
            self._collector.observe("hitl.response.latency_ms", metric_labels, value=latency_ms)
