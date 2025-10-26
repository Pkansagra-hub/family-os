"""
Layer 5 - Observability Module

This module provides K1 observability by reusing K0's proven observability infrastructure.
K1 imports and initializes K0's MetricsExporter and TracerFactory with the "k1_intelligence"
namespace, ensuring consistent metrics, traces, and logs across the entire FamilyOS stack.

Architecture:
- K1 uses k0.obs.metrics.MetricsExporter (namespace="k1_intelligence")
- K1 uses k0.obs.tracing.TracerFactory (service_name="k1_intelligence")
- Both export to the same Prometheus (9090) and Tempo (4318) instances as K0
- Grafana dashboards include both k0_kernel and k1_intelligence metrics

Components:
- metrics: K0's MetricsExporter with k1_intelligence namespace
- tracing: K0's TracerFactory with k1_intelligence service name
- logging: Structured logging (structlog) with cognitive_trace_id

Observability Pillars:

1. Metrics (Prometheus via K0, ADR-0029):
   - Reuse k0.obs.metrics.MetricsExporter
   - K1 namespace: k1_intelligence_*
   - RED method: Rate, Error, Duration
   - <10ms emission overhead (<1% CPU)
   - 10s scrape interval (shared with K0)

2. Tracing (OpenTelemetry via K0, ADR-0030):
   - Reuse k0.obs.tracing.TracerFactory
   - cognitive_trace_id propagation (end-to-end K1→K0)
   - Same sampling as K0 (1% baseline, 100% errors)
   - <5ms span creation
   - OTLP export to Tempo (http://localhost:4318/v1/traces)

3. Logging (Structured JSON, ADR-0002d):
   - structlog with cognitive_trace_id in context
   - Compatible with K0 log parsers
   - <5ms log write

Performance (ADR-0024):
- Metric emission: <10ms P95
- Trace span creation: <5ms P95
- Log write: <5ms P95
- Total observability overhead: <1% CPU, <50MB memory

Primary ADRs:
- ADR-0029: Prometheus Metrics (50+ metrics, RED method, alerting)
- ADR-0030: Trace Sampling (cognitive_trace_id, adaptive sampling)
- ADR-0002d: Actor Fabric Observability (structured logs, actor metrics)
- ADR-0024: Performance Budgets (observability <10ms overhead)

Research Foundation:
- RED method (Tom Wilkie, Grafana Labs)
- OpenTelemetry (CNCF distributed tracing standard)
- Structured logging (JSON logs, semantic context)

Example Usage:
```python
from k1.l5_infrastructure.observability import get_metrics, get_tracer

# Get K1 metrics exporter
metrics = get_metrics()
counter = metrics.counter("command_requests_total", "Total commands", labelnames=["band", "status"])
counter.labels(band="GREEN", status="success").inc()

# Get K1 tracer
tracer = get_tracer()
with tracer.span("k1.command_submit", attributes={"band": "GREEN"}):
    # ... operation ...
    pass
```
"""

from prometheus_client import REGISTRY as PROMETHEUS_GLOBAL_REGISTRY
from prometheus_client import CollectorRegistry

from k0.obs.metrics import MetricsExporter
from k0.obs.tracing import COGNITIVE_TRACE_BAGGAGE_KEY, TracerFactory

__all__ = [
    "get_metrics",
    "get_tracer",
    "COGNITIVE_TRACE_BAGGAGE_KEY",
]

# Global K1 metrics exporter (initialized lazily)
_metrics_exporter: MetricsExporter | None = None

# Global K1 tracer factory (initialized lazily)
_tracer_factory: TracerFactory | None = None


def get_metrics(registry: CollectorRegistry | None = None) -> MetricsExporter:
    """
    Get the K1 metrics exporter (k1_intelligence namespace).

    This lazily initializes K0's MetricsExporter with the k1_intelligence namespace.
    All K1 metrics will be prefixed with "k1_intelligence_" and registered with
    the Prometheus global registry (shared with K0).

    Args:
        registry: Optional Prometheus registry to use. If None, uses the global registry
                  which is shared with K0 kernel.

    Returns:
        MetricsExporter configured for K1
    """
    global _metrics_exporter
    if _metrics_exporter is None:
        # Use the global Prometheus registry (shared with K0) by default
        # This ensures K1 metrics appear in K0's /metrics endpoint
        _metrics_exporter = MetricsExporter(
            namespace="k1_intelligence",
            registry=registry or PROMETHEUS_GLOBAL_REGISTRY,
            default_histogram_buckets=(
                0.01,
                0.025,
                0.05,
                0.1,
                0.2,
                0.5,
                1.0,
                2.0,
                5.0,
                10.0,
            ),  # 10ms, 25ms, 50ms, 100ms, 200ms, 500ms, 1s, 2s, 5s, 10s
        )
    return _metrics_exporter


def get_tracer() -> TracerFactory:
    """
    Get the K1 tracer factory (k1_intelligence service name).

    This lazily initializes K0's TracerFactory with the k1_intelligence service name.
    All K1 spans will be tagged with service.name="k1_intelligence" and exported
    to the same Tempo instance as K0.

    During testing (detected by sys.modules containing 'pytest' or 'ward'), OTLP
    export is disabled to avoid connection errors to non-existent collectors.

    Environment Variables:
        OTLP_HTTP_ENDPOINT: OTLP HTTP endpoint (default: http://localhost:4318/v1/traces)
        OTEL_SERVICE_NAME: Service name (default: k1_intelligence)
        ENVIRONMENT: Deployment environment (default: dev)
        OTEL_SAMPLE_RATIO: Trace sampling ratio 0.0-1.0 (default: 1.0 for dev)

    Returns:
        TracerFactory configured for K1

    Example:
        # Development (defaults)
        tracer = get_tracer()

        # Production (via env vars)
        export OTLP_HTTP_ENDPOINT=https://tempo.prod.internal:4318/v1/traces
        export OTEL_SERVICE_NAME=k1_intelligence
        export ENVIRONMENT=production
        export OTEL_SAMPLE_RATIO=0.01  # 1% sampling
    """
    import os
    import sys

    global _tracer_factory
    if _tracer_factory is None:
        # Disable OTLP export during testing to avoid connection errors
        # Check if we're in a test environment
        is_testing = "pytest" in sys.modules or "ward" in sys.modules

        # Environment-based configuration (ADR-0030)
        otlp_endpoint = (
            None
            if is_testing
            else os.getenv("OTLP_HTTP_ENDPOINT", "http://localhost:4318/v1/traces")
        )
        service_name = os.getenv("OTEL_SERVICE_NAME", "k1_intelligence")
        environment = os.getenv("ENVIRONMENT", "dev")
        sample_ratio = float(os.getenv("OTEL_SAMPLE_RATIO", "1.0"))

        _tracer_factory = TracerFactory(
            service_name=service_name,
            service_version="1.0.0",
            environment=environment,
            otlp_endpoint=otlp_endpoint,  # Tempo OTLP HTTP endpoint (None during tests)
            sample_ratio=sample_ratio,  # 100% sampling for development (adjust for production)
        )
    return _tracer_factory
