"""PrometheusAdapter -- metrics emission adapter [F33].

Histograms, counters, gauges for observability.
Synchronous, fire-and-forget (MH metrics contract).

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.prometheus_adapter
  -> k1.model_hub.ports      (Layer 1)
  -> stdlib only (no prometheus_client yet)
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class PrometheusAdapter:
    """IMetricsPort adapter for Prometheus-compatible metrics.

    Production: delegates to prometheus_client library.
    Current: in-memory accumulator for single-process operation.

    Error handling: emit failures logged, never crash hub.
    """

    def __init__(self) -> None:
        self._counters: Dict[str, float] = {}

    def emit(
        self,
        metric_name: str,
        value: float,
        labels: Dict[str, Any] | None = None,
    ) -> None:
        """Emit metric value (fire-and-forget).

        Labels: provider, model, consumer, capability, priority.
        """
        try:
            key = metric_name
            if labels:
                label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
                key = f"{metric_name}{{{label_str}}}"
            self._counters[key] = self._counters.get(key, 0.0) + value
        except Exception:
            logger.exception("PrometheusAdapter.emit failed metric=%s", metric_name)


__all__ = ["PrometheusAdapter"]
