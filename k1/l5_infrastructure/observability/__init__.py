"""
K1 Observability - Thin Adapter to K0 Observability Stack

Layer: L5 Infrastructure
Component: Observability (Metrics, Traces, Logs)
Priority: 🔴 CRITICAL (Required for debugging, monitoring, alerting)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Philosophy:
    - K1 does NOT implement its own observability stack
    - K1 reuses K0's existing Prometheus/Grafana/Tempo infrastructure
    - K1 forwards all telemetry to K0 via Bridge Observability Port
    - Shared metrics/traces across K0+K1 for unified monitoring

K0 Observability Stack (Already Implemented):
    - Prometheus: Metrics scraping, alerting (port 9090)
    - Grafana: Dashboards, visualization (port 3000)
    - Tempo: Distributed tracing (OpenTelemetry backend)
    - Loki: Log aggregation (structured logs)
    - AlertManager: Alert routing, notifications

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Architecture (Observability Port)
    - ADR-0002d: Actor Fabric Observability (metrics/traces/logs pattern)
    - ADR-0004d: Layer Testing & Observability (per-layer metrics)

K1 → K0 Observability Flow:
    1. K1 component emits metric/trace/log (using this module)
    2. L5 observability adapter forwards to K0 Bridge Observability Port
    3. K0 Bridge routes to appropriate backend (Prometheus/Tempo/Loki)
    4. Unified dashboards show K0+K1 telemetry together

Components:
    - metrics.py: Prometheus metric client (forwards to K0)
    - tracing.py: OpenTelemetry trace client (forwards to K0)
    - logging.py: Structured log client (forwards to K0)
    - k0_client.py: HTTP/2 client for K0 Observability Port

Integration Points:
    - k1.bridge_k0.ports.observability_port: K0 Observability Port client
    - k0.obs.prometheus: K0 Prometheus exporter (receives K1 metrics)
    - k0.obs.tempo: K0 Tempo collector (receives K1 traces)
    - k0.obs.loki: K0 Loki agent (receives K1 logs)

Performance Budgets:
    - Metric emission: <1ms P95 (async batching)
    - Trace span creation: <0.5ms P95 (zero-copy)
    - Log emission: <0.3ms P95 (async queue)
    - K0 port latency: <5ms P95 (local HTTP/2)

Dependencies:
    Internal:
        - k1.bridge_k0.ports.observability_port (K0 observability client)
    External:
        - opentelemetry-api (trace instrumentation)
        - opentelemetry-sdk (trace exporter)
        - structlog (structured logging)

Module Exports:
    - emit_metric(name, value, labels, timestamp)
    - start_trace_span(name, parent_span_id, trace_id)
    - end_trace_span(span_id, status, attributes)
    - log_event(level, message, context, trace_id)
    - MetricType enum (Counter, Gauge, Histogram, Summary)
    - LogLevel enum (DEBUG, INFO, WARNING, ERROR, CRITICAL)

Example Usage:
    ```python
    from k1.l5_infrastructure.observability import emit_metric, start_trace_span, log_event

    # Emit counter metric (forwards to K0 Prometheus)
    emit_metric(
        name="k1.orchestrator.agent_hired_total",
        value=1,
        labels={"agent_type": "planner", "session_id": "sess_123"},
        metric_type=MetricType.COUNTER
    )

    # Start trace span (forwards to K0 Tempo)
    span_id = start_trace_span(
        name="orchestrator.3_phase_coordination",
        parent_span_id="span_abc",
        trace_id="trace_xyz"
    )
    # ... do work ...
    end_trace_span(span_id, status="ok", attributes={"latency_ms": 245})

    # Log structured event (forwards to K0 Loki)
    log_event(
        level=LogLevel.INFO,
        message="Agent hire completed",
        context={"agent_id": "agent_planner_1", "latency_ms": 150},
        trace_id="trace_xyz"
    )
    ```

Zero-Implementation Philosophy:
    - K1 does NOT run Prometheus/Grafana/Tempo locally
    - K1 does NOT scrape its own metrics
    - K1 does NOT store traces/logs locally
    - K1 forwards everything to K0 (single source of truth)
    - Benefits: No duplicate infra, unified dashboards, simpler deployment

TODO List:
    - TODO(@observability-team): Implement K0 observability port client (k0_client.py)
    - TODO(@observability-team): Implement metric forwarding (metrics.py)
    - TODO(@observability-team): Implement trace forwarding (tracing.py)
    - TODO(@observability-team): Implement log forwarding (logging.py)
    - TODO(@observability-team): Add batching for metrics (100 metrics/batch, 1s flush)
    - TODO(@observability-team): Add async queueing for logs (1000 log buffer)
    - TODO(@observability-team): Implement cognitive_trace_id propagation
    - TODO(@observability-team): Add Prometheus metric registry
    - TODO(@observability-team): Integrate OpenTelemetry context propagation
    - TODO(@observability-team): Add K0 port health check (ping every 30s)

Issue References:
    - Epic 5.2: Observability Infrastructure
    - Milestone M14: K0 Bridge Integration (includes observability port)

Last Updated: 2025-10-28
"""

from enum import Enum
from typing import Any, Dict, Optional

# Enums will be imported from submodules once implemented
__all__ = [
    # Functions
    'emit_metric',
    'start_trace_span',
    'end_trace_span',
    'log_event',

    # Enums
    'MetricType',
    'LogLevel',

    # Classes (future)
    # 'K0ObservabilityClient',
    # 'MetricBatcher',
    # 'TraceSpan',
]


class MetricType(Enum):
    """Prometheus metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class LogLevel(Enum):
    """Log severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# Stub implementations - forward to K0
def emit_metric(
    name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
    metric_type: MetricType = MetricType.COUNTER,
    timestamp: Optional[int] = None
) -> None:
    """
    Emit metric to K0 Prometheus via Observability Port.

    Args:
        name: Metric name (e.g., "k1.orchestrator.agent_hired_total")
        value: Metric value
        labels: Label dict (e.g., {"agent_type": "planner"})
        metric_type: Counter/Gauge/Histogram/Summary
        timestamp: Unix timestamp in milliseconds (optional)

    TODO(@observability-team): Forward to k1.bridge_k0.ports.observability_port
    """
    pass


def start_trace_span(
    name: str,
    parent_span_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
) -> str:
    """
    Start OpenTelemetry trace span (forwards to K0 Tempo).

    Args:
        name: Span name (e.g., "orchestrator.3_phase_coordination")
        parent_span_id: Parent span ID for nesting
        trace_id: Trace ID (cognitive_trace_id from SessionState)
        attributes: Span attributes

    Returns:
        span_id: Generated span ID

    TODO(@observability-team): Forward to k1.bridge_k0.ports.observability_port
    """
    return "span_stub"


def end_trace_span(
    span_id: str,
    status: str = "ok",
    attributes: Optional[Dict[str, Any]] = None
) -> None:
    """
    End trace span (forwards to K0 Tempo).

    Args:
        span_id: Span ID from start_trace_span()
        status: "ok" or "error"
        attributes: Additional attributes (e.g., latency_ms)

    TODO(@observability-team): Forward to k1.bridge_k0.ports.observability_port
    """
    pass


def log_event(
    level: LogLevel,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None
) -> None:
    """
    Emit structured log (forwards to K0 Loki).

    Args:
        level: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        message: Log message
        context: Structured context dict
        trace_id: Trace ID for correlation

    TODO(@observability-team): Forward to k1.bridge_k0.ports.observability_port
    """
    pass


# Module metadata
__version__ = '0.1.0'
__status__ = 'STUB'
