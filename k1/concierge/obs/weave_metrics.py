"""
k1.concierge.obs.weave_metrics -- Weave policy effectiveness metrics.

M11 Stub -- placeholder for Weave telemetry subscriber.

WeaveMetricsSubscriber records:
    - Weave invocation count
    - Policy match/miss counters
    - Weave response quality scores

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from k1.concierge.obs.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class WeaveMetricsSubscriber:
    """Subscribes to Weave execution events and emits effectiveness metrics.

    Stub implementation -- production will wire to bus Weave event topics.
    """

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector

    def on_weave_execution(
        self,
        policy_matched: bool,
        quality_score: float = 0.0,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Record a Weave execution event.

        Args:
            policy_matched: Whether a Weave policy matched the context.
            quality_score: Response quality score (0.0-1.0).
            labels: Additional filtering labels.
        """
        if not self._collector or not self._collector.enabled:
            return
        metric_labels = {"policy_matched": str(policy_matched).lower()}
        if labels:
            metric_labels.update({k: str(v) for k, v in labels.items()})
        self._collector.increment("weave.execution.count", metric_labels)
        if quality_score > 0:
            self._collector.observe("weave.quality_score", metric_labels, value=quality_score)
