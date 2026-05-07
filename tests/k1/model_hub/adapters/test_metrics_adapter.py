"""TestMetricsAdapter -- test adapter for IMetricsPort [6.1.4].

Captures all emitted metrics for post-test assertion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class CapturedMetric:
    """A captured emit() call."""

    metric_name: str
    value: float
    labels: Dict[str, Any]


class TestMetricsAdapter:
    """Deterministic IMetricsPort for testing.

    Capture:
      - metrics: All (metric_name, value, labels) triples from emit().

    isinstance(adapter, IMetricsPort) == True.
    """

    def __init__(self) -> None:
        self._metrics: List[CapturedMetric] = []

    def emit(
        self,
        metric_name: str,
        value: float,
        labels: Dict[str, Any] | None = None,
    ) -> None:
        """Capture metric emission (synchronous, fire-and-forget)."""
        self._metrics.append(
            CapturedMetric(
                metric_name=metric_name,
                value=value,
                labels=labels or {},
            )
        )

    # -- Test inspection -------------------------------------------------------

    @property
    def metrics(self) -> List[CapturedMetric]:
        return list(self._metrics)

    def metrics_for(self, metric_name: str) -> List[CapturedMetric]:
        """Get all emissions for a specific metric name."""
        return [m for m in self._metrics if m.metric_name == metric_name]

    @property
    def count(self) -> int:
        return len(self._metrics)

    def reset(self) -> None:
        self._metrics.clear()


__all__ = ["CapturedMetric", "TestMetricsAdapter"]
