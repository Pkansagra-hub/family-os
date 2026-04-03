"""Model Hub metric definitions [F05].

Module-level metric constants for observability. All metrics prefixed
with ``model_hub.``.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.model_hub.metrics
  -> stdlib only

NEVER import from any service, port, adapter, or plugin module.

References
----------
- model_hub.mmd: PERF_BASELINES, Metrics section
- ADR-0001b: Model Hub Architecture
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

# ===========================================================================
# Metric type enum (lightweight -- no prometheus dependency in Layer 0)
# ===========================================================================


class MetricType(str, Enum):
    """Metric type for definition only. Actual recording in adapters."""

    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"


# ===========================================================================
# Metric definition dataclass
# ===========================================================================


@dataclass(frozen=True)
class MetricDef:
    """Metric definition -- name, type, labels, description."""

    name: str
    type: MetricType
    description: str
    labels: List[str]
    buckets: Optional[List[float]] = None


# ===========================================================================
# Default histogram buckets
# ===========================================================================

LATENCY_BUCKETS: List[float] = [
    1.0,
    2.0,
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1000.0,
    2500.0,
    5000.0,
    10000.0,
    30000.0,
]

TOKEN_BUCKETS: List[float] = [
    10.0,
    50.0,
    100.0,
    500.0,
    1000.0,
    5000.0,
    10000.0,
    50000.0,
    100000.0,
]

COST_BUCKETS: List[float] = [
    0.0001,
    0.001,
    0.005,
    0.01,
    0.05,
    0.1,
    0.5,
    1.0,
]


# ===========================================================================
# Standard labels
# ===========================================================================

STANDARD_LABELS: List[str] = [
    "provider",
    "model",
    "consumer",
    "capability",
    "priority",
]


# ===========================================================================
# Counter Definitions (5 counters)
# ===========================================================================

hub_requests_total = MetricDef(
    name="model_hub.requests_total",
    type=MetricType.COUNTER,
    description="Total number of requests received by Model Hub",
    labels=STANDARD_LABELS,
)

hub_errors_total = MetricDef(
    name="model_hub.errors_total",
    type=MetricType.COUNTER,
    description="Total number of errors in Model Hub",
    labels=STANDARD_LABELS + ["error_type"],
)

hub_cache_hits_total = MetricDef(
    name="model_hub.cache_hits_total",
    type=MetricType.COUNTER,
    description="Total number of response cache hits",
    labels=["capability"],
)

hub_fallbacks_total = MetricDef(
    name="model_hub.fallbacks_total",
    type=MetricType.COUNTER,
    description="Total number of provider fallback events",
    labels=["from_provider", "to_provider", "capability"],
)

hub_budget_rejections_total = MetricDef(
    name="model_hub.budget_rejections_total",
    type=MetricType.COUNTER,
    description="Total number of requests rejected due to budget limits",
    labels=["capability", "consumer"],
)


# ===========================================================================
# Histogram Definitions (4 histograms)
# ===========================================================================

hub_latency_ms = MetricDef(
    name="model_hub.latency_ms",
    type=MetricType.HISTOGRAM,
    description="End-to-end hub latency in milliseconds (excluding LLM inference)",
    labels=STANDARD_LABELS,
    buckets=LATENCY_BUCKETS,
)

provider_latency_ms = MetricDef(
    name="model_hub.provider_latency_ms",
    type=MetricType.HISTOGRAM,
    description="Provider plugin execution latency in milliseconds",
    labels=["provider", "model", "capability"],
    buckets=LATENCY_BUCKETS,
)

hub_tokens_used = MetricDef(
    name="model_hub.tokens_used",
    type=MetricType.HISTOGRAM,
    description="Token usage per request",
    labels=STANDARD_LABELS,
    buckets=TOKEN_BUCKETS,
)

hub_cost_usd = MetricDef(
    name="model_hub.cost_usd",
    type=MetricType.HISTOGRAM,
    description="Cost per request in USD",
    labels=STANDARD_LABELS,
    buckets=COST_BUCKETS,
)


# ===========================================================================
# Gauge Definitions (3 gauges)
# ===========================================================================

hub_active_requests = MetricDef(
    name="model_hub.active_requests",
    type=MetricType.GAUGE,
    description="Number of currently active requests",
    labels=[],
)

provider_circuit_state = MetricDef(
    name="model_hub.provider_circuit_state",
    type=MetricType.GAUGE,
    description="Circuit breaker state per provider (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
    labels=["provider"],
)

hub_budget_pct = MetricDef(
    name="model_hub.budget_pct",
    type=MetricType.GAUGE,
    description="Daily budget usage percentage",
    labels=[],
)


# ===========================================================================
# All metrics registry (for adapter iteration)
# ===========================================================================

ALL_METRICS: Dict[str, MetricDef] = {
    m.name: m
    for m in [
        hub_requests_total,
        hub_errors_total,
        hub_cache_hits_total,
        hub_fallbacks_total,
        hub_budget_rejections_total,
        hub_latency_ms,
        provider_latency_ms,
        hub_tokens_used,
        hub_cost_usd,
        hub_active_requests,
        provider_circuit_state,
        hub_budget_pct,
    ]
}


__all__ = [
    # Types
    "MetricType",
    "MetricDef",
    # Buckets
    "LATENCY_BUCKETS",
    "TOKEN_BUCKETS",
    "COST_BUCKETS",
    "STANDARD_LABELS",
    # Counters
    "hub_requests_total",
    "hub_errors_total",
    "hub_cache_hits_total",
    "hub_fallbacks_total",
    "hub_budget_rejections_total",
    # Histograms
    "hub_latency_ms",
    "provider_latency_ms",
    "hub_tokens_used",
    "hub_cost_usd",
    # Gauges
    "hub_active_requests",
    "provider_circuit_state",
    "hub_budget_pct",
    # Registry
    "ALL_METRICS",
]
