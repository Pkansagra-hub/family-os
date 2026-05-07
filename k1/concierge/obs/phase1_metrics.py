"""
k1.concierge.obs.phase1_metrics -- Phase1 classification health metrics.

M11 Stub -- placeholder for Phase1 (UltraBERT) telemetry subscriber.

Phase1MetricsSubscriber records:
    - Classification count per predicted label
    - Classification latency histogram
    - Confidence score distribution
    - Low-confidence alert rate

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from k1.concierge.obs.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class Phase1MetricsSubscriber:
    """Subscribes to Phase1 classification events and emits health metrics.

    Stub implementation -- production will wire to bus Phase1 event topics.
    """

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector

    def on_classification(
        self,
        label: str,
        confidence: float = 0.0,
        latency_ms: float = 0.0,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Record a Phase1 classification event.

        Args:
            label: Predicted classification label.
            confidence: Model confidence score (0.0-1.0).
            latency_ms: Classification latency in milliseconds.
            labels: Additional filtering labels.
        """
        if not self._collector or not self._collector.enabled:
            return
        metric_labels = {"label": label}
        if labels:
            metric_labels.update({k: str(v) for k, v in labels.items()})
        self._collector.increment("phase1.classification.count", metric_labels)
        if confidence > 0:
            self._collector.observe(
                "phase1.classification.confidence", metric_labels, value=confidence
            )
        if latency_ms > 0:
            self._collector.observe(
                "phase1.classification.latency_ms", metric_labels, value=latency_ms
            )
