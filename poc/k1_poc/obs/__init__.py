"""
poc.k1_poc.obs -- Observability & Telemetry package (M11).

Provides unified metrics emission, aggregation, alerting, and
session-level observability for all K1 subsystems.

Submodules:
    metrics     -- MetricEnvelope, MetricsCollector, MetricAggregator, SlidingWindow
    alerts      -- AlertRule, AlertEngine, AlertEvent
    fsm_metrics -- FSMMetricsSubscriber (transition counters, dwell time)
    hitl_metrics -- HITLMetricsSubscriber (lifecycle dashboard)
    arbiter_metrics -- ArbiterMetricsSubscriber (decision distribution)
    weave_metrics -- WeaveMetricsSubscriber (policy effectiveness)
    phase1_metrics -- Phase1MetricsSubscriber (classification health)

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from poc.k1_poc.obs.actor_metrics import (
    BackOutcome,
    FrontOutcome,
    classify_budget_utilization,
    record_back_metrics,
    record_front_metrics,
)
from poc.k1_poc.obs.metrics import (
    MetricAggregator,
    MetricEnvelope,
    MetricsCollector,
    SlidingWindow,
    TurnTimer,
)
from poc.k1_poc.obs.react_metrics import (
    ReactLoopOutcome,
    classify_exit_path,
    record_react_loop_metrics,
)

__all__ = [
    "MetricEnvelope",
    "MetricsCollector",
    "MetricAggregator",
    "SlidingWindow",
    "TurnTimer",
    "ReactLoopOutcome",
    "classify_exit_path",
    "record_react_loop_metrics",
    "FrontOutcome",
    "BackOutcome",
    "record_front_metrics",
    "record_back_metrics",
    "classify_budget_utilization",
]
