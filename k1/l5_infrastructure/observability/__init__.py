"""
Layer 5 - Observability Module

This module provides comprehensive observability infrastructure for K1:
Prometheus metrics, OpenTelemetry tracing, structured logging, and Grafana dashboards.

Components:
- metrics: Prometheus metrics exporter (50+ metrics, RED method)
- tracing: OpenTelemetry distributed tracing (1% sampling, adaptive)
- logging: Structured JSON logging (6 event types)
- dashboards: Grafana dashboard definitions (7 dashboards)

Observability Pillars:

1. Metrics (Prometheus, ADR-0029):
   - 50+ metrics across all layers
   - RED method: Rate, Error, Duration
   - <10ms emission overhead (<1% CPU)
   - 10s scrape interval

2. Tracing (OpenTelemetry, ADR-0030):
   - cognitive_trace_id propagation (128-bit unique ID)
   - 1% baseline sampling, 100% error sampling
   - Adaptive sampling (NORMAL 1%, DEGRADATION 10%, CRITICAL 50%)
   - <5ms span creation

3. Logging (Structured JSON, ADR-0002d):
   - 6 event types (ACTOR_STARTED, MESSAGE_SENT, CRASH_DETECTED, etc.)
   - cognitive_trace_id in all logs
   - <5ms log write
   - Daily rotation, 7-day retention

4. Dashboards (Grafana, ADR-0029e):
   - 7 dashboards (K1 Overview, Layer 1-5, Actor Fabric)
   - SLO alerts (TTFT >157ms, E2E >2100ms, Error >1%)
   - Alert routing (CRITICAL→PagerDuty, WARNING→Slack)

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
- SLO-based alerting (Google SRE Book)
"""

# __all__ = [
#     "MetricsExporter",
#     "TracingManager",
#     "StructuredLogger",
# ]
