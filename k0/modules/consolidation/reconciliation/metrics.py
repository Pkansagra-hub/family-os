"""DecisionMetrics -- per-batch Prometheus emission (M9.4).

Created per P03 cycle, not a singleton. Wraps a metrics registry
(``MetricsExporter`` or ``P03MetricsRegistry``) and emits counters,
gauges, and histograms for reconciliation decisions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from k0.pipelines.p03.event_state import ReconciliationAction

if TYPE_CHECKING:
    from k0.modules.consolidation.reconciliation.result import ReconciliationResult


class MetricsRegistry(Protocol):
    """Minimal protocol for any metrics backend."""

    def counter(self, name: str, *, labels: dict[str, str]) -> None: ...
    def observe(self, name: str, value: float, *, labels: dict[str, str]) -> None: ...
    def gauge(self, name: str, value: float, *, labels: dict[str, str]) -> None: ...


class DecisionMetrics:
    """Per-batch Prometheus emission for reconciliation decisions."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def record_decision(self, result: ReconciliationResult) -> None:
        """Record a single decision to Prometheus counters."""
        self._registry.counter(
            "reconciliation_decisions_total",
            labels={"layer": result.layer, "action": result.action.value},
        )

        self._registry.observe(
            "reconciliation_decision_confidence",
            value=result.confidence,
            labels={"layer": result.layer, "action": result.action.value},
        )

        if result.tier == 2 and result.similarity > 0.0:
            self._registry.observe(
                "reconciliation_similarity_score",
                value=result.similarity,
                labels={"layer": result.layer, "action": result.action.value},
            )

        self._registry.observe(
            "reconciliation_decision_latency_ms",
            value=result.decision_time_ms,
            labels={"layer": result.layer},
        )

        if result.tier == 1:
            signal_type = (
                "correction" if result.action == ReconciliationAction.EVOLVE else "contradiction"
            )
            self._registry.counter(
                "reconciliation_k1_bypass_total",
                labels={"signal_type": signal_type},
            )

    def record_batch_summary(
        self,
        layer: str,
        batch_size: int,
        identity_filtered: int,
        results: dict[str, ReconciliationResult],
    ) -> None:
        """Record batch-level aggregates after decide_batch()."""
        self._registry.gauge(
            "reconciliation_batch_size",
            value=batch_size,
            labels={"layer": layer},
        )

        if batch_size > 0:
            self._registry.gauge(
                "reconciliation_identity_filter_ratio",
                value=identity_filtered / batch_size,
                labels={"layer": layer},
            )

        action_counts: dict[str, int] = {}
        for r in results.values():
            action_counts[r.action.value] = action_counts.get(r.action.value, 0) + 1
        for action_name, count in action_counts.items():
            self._registry.gauge(
                "reconciliation_batch_action_count",
                value=count,
                labels={"layer": layer, "action": action_name},
            )
