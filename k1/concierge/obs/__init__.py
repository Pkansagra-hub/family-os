"""
k1.concierge.obs -- Observability & Telemetry package (M11).

Provides unified metrics emission, aggregation, alerting, and
session-level observability for all K1 subsystems.

Submodules:
    metrics     -- MetricEnvelope, MetricsCollector, MetricAggregator, SlidingWindow
    alerts      -- AlertRule, AlertEngine, AlertEvent
    fsm_metrics -- FSMMetricsSubscriber (transition counters, dwell time)
    hitl_metrics -- HITLMetricsSubscriber (lifecycle dashboard)
    arbiter_metrics -- ArbiterMetricsSubscriber (decision distribution)
    weave_metrics -- WeaveMetricsSubscriber (policy effectiveness)

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from k1.concierge.obs.actor_metrics import (
    BackOutcome,
    FrontOutcome,
    classify_budget_utilization,
    record_back_metrics,
    record_front_metrics,
)

# --- Stub submodules (M11 placeholders) ---
from k1.concierge.obs.alerts import AlertEngine, AlertEvent, AlertRule
from k1.concierge.obs.arbiter_metrics import ArbiterMetricsSubscriber
from k1.concierge.obs.fsm_metrics import FSMMetricsSubscriber
from k1.concierge.obs.hitl_metrics import HITLMetricsSubscriber
from k1.concierge.obs.metrics import (
    MetricAggregator,
    MetricEnvelope,
    MetricsCollector,
    SlidingWindow,
    TurnTimer,
)
from k1.concierge.obs.react_metrics import (
    ReactLoopOutcome,
    classify_exit_path,
    record_react_loop_metrics,
)
from k1.concierge.obs.weave_metrics import WeaveMetricsSubscriber

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
    # Stub submodules
    "AlertRule",
    "AlertEngine",
    "AlertEvent",
    "FSMMetricsSubscriber",
    "HITLMetricsSubscriber",
    "ArbiterMetricsSubscriber",
    "WeaveMetricsSubscriber",
]
