"""
k1.concierge.obs.fsm_metrics -- FSM transition counters and dwell time.

M11 Stub -- placeholder for FSM telemetry subscriber.

FSMMetricsSubscriber subscribes to FSM state-change events and records:
    - Transition counts per (from_state, to_state) pair
    - Dwell time per state (ms between entry and exit)
    - Anomalous transition alerts

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from k1.concierge.obs.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class FSMMetricsSubscriber:
    """Subscribes to FSM events and emits transition/dwell metrics.

    Stub implementation -- production will wire to bus FSM event topics.
    """

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector

    def on_transition(
        self,
        from_state: str,
        to_state: str,
        dwell_ms: float = 0.0,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Record an FSM state transition.

        Args:
            from_state: State being exited.
            to_state: State being entered.
            dwell_ms: Time spent in from_state (milliseconds).
            labels: Additional filtering labels.
        """
        if not self._collector or not self._collector.enabled:
            return
        metric_labels = {"from_state": from_state, "to_state": to_state}
        if labels:
            metric_labels.update({k: str(v) for k, v in labels.items()})
        self._collector.increment("fsm.transition.count", metric_labels)
        if dwell_ms > 0:
            self._collector.observe("fsm.state.dwell_ms", {"state": from_state}, value=dwell_ms)
