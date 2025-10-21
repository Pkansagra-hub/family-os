# Observability Contracts

**Source ADRs:** ADR-0016, ADR-0016a-d

## Overview

This directory contains observability contracts for K1, including structured logging, metrics (Prometheus), distributed tracing (OpenTelemetry), and alerting.

## Research Foundation

- **Observability Pillars:** Logs, Metrics, Traces (Charity Majors)
- **OpenTelemetry:** Unified observability standard
- **SRE Principles:** SLIs, SLOs, Error Budgets

## Contracts Included

### 1. Structured Logging Contract (`structured_logging.yaml`)
- **Source:** ADR-0016a
- Log format (JSON)
- Log levels and filtering
- PII redaction

### 2. Metrics Contract (`metrics.yaml`)
- **Source:** ADR-0016b
- Prometheus metrics
- Metric naming conventions
- Cardinality management

### 3. Distributed Tracing Contract (`distributed_tracing.yaml`)
- **Source:** ADR-0016c
- OpenTelemetry integration
- Span structure
- cognitive_trace_id propagation

### 4. Alerting Contract (`alerting.yaml`)
- **Source:** ADR-0016d
- Alert definitions
- Severity levels
- On-call escalation

## Structured Logging

**Source:** ADR-0016a

```yaml
structured_logging:
  format: JSON

  log_entry:
    timestamp: iso8601
    level: DEBUG | INFO | WARNING | ERROR | CRITICAL
    logger: string (module.component)
    message: string
    trace_id: string (cognitive_trace_id)
    span_id: string | null
    session_id: string | null
    actor_id: string | null
    metadata: object
    error: object | null

  log_levels:
    DEBUG:
      description: Detailed diagnostic information
      use_case: Development only
      enabled_in_production: false

    INFO:
      description: General informational messages
      use_case: Normal operations, audit trail
      enabled_in_production: true
      examples:
        - Agent state transitions
        - Task assignments
        - API requests

    WARNING:
      description: Potentially harmful situations
      use_case: Degraded performance, retry attempts
      enabled_in_production: true
      examples:
        - Budget exceeded
        - Timeout warnings
        - Rate limit approaching

    ERROR:
      description: Error events that might still allow continued operation
      use_case: Recoverable errors, retries exhausted
      enabled_in_production: true
      examples:
        - Tool call failures
        - Validation errors
        - Protocol violations

    CRITICAL:
      description: Severe errors requiring immediate attention
      use_case: System instability, data loss risk
      enabled_in_production: true
      alert: page_on_call_team
      examples:
        - System crash
        - Data corruption
        - Security breach

  pii_redaction:
    enabled: true
    patterns:
      email: "[EMAIL_REDACTED]"
      phone: "[PHONE_REDACTED]"
      ssn: "[SSN_REDACTED]"
      credit_card: "[CC_REDACTED]"
      ip_address: "[IP_REDACTED]"

    redaction_library: presidio or custom regex

  log_aggregation:
    destination: Elasticsearch or CloudWatch Logs
    retention: 30 days
    indexing: By timestamp, trace_id, session_id, actor_id
```

## Metrics (Prometheus)

**Source:** ADR-0016b

```yaml
prometheus_metrics:
  metric_types:
    counter:
      description: Monotonically increasing value
      examples:
        - request_total{endpoint, status}
        - error_total{component, error_type}
        - agent_transition_total{from_state, to_state}

    gauge:
      description: Arbitrary value that can go up or down
      examples:
        - active_sessions{node}
        - memory_usage_bytes{component}
        - queue_size{queue_name}

    histogram:
      description: Distribution of values (latency, sizes)
      examples:
        - request_duration_ms{endpoint}
        - batch_size{operation}
        - response_size_bytes{endpoint}
      buckets: [10, 50, 100, 250, 500, 1000, 2000, 5000]

    summary:
      description: Percentiles calculated client-side
      examples:
        - request_latency_ms{component, quantile}
      quantiles: [0.5, 0.95, 0.99]

  naming_conventions:
    format: <namespace>_<subsystem>_<name>_<unit>
    namespace: k1
    examples:
      - k1_orchestrator_task_duration_ms
      - k1_agent_warmup_latency_ms
      - k1_kv_cache_hit_rate
      - k1_sessionstate_size_bytes

  label_best_practices:
    - Use consistent label names across metrics
    - Avoid high cardinality labels (e.g., user_id, session_id)
    - Limit label values to bounded sets
    - Use label for filtering, not identification

  cardinality_management:
    max_label_values: 1000 per label
    high_cardinality_labels:
      - session_id: Use sampling (1% of sessions)
      - trace_id: Don't use in Prometheus (use tracing instead)
      - user_id: Don't use in Prometheus (aggregate by user_type)

  scraping:
    endpoint: /metrics
    port: 9090
    interval: 15s
    timeout: 10s
```

## Distributed Tracing (OpenTelemetry)

**Source:** ADR-0016c

```yaml
distributed_tracing:
  protocol: OpenTelemetry (OTLP)

  trace_structure:
    trace_id: cognitive_trace_id (UUID)
    span_id: unique per operation (UUID)
    parent_span_id: parent operation span_id

  span_attributes:
    service.name: k1_intelligence
    service.version: 1.0.0
    component: string (e.g., "orchestrator", "planner")
    operation: string (e.g., "3_phase_orchestration", "plan_generation")
    session_id: string
    actor_id: string
    privacy_band: GREEN | AMBER | RED

  span_events:
    - event_name: string
    - timestamp: iso8601
    - attributes: object

  span_lifecycle:
    start: Record span start time
    add_attributes: Add metadata during execution
    add_events: Record important milestones
    set_status: OK | ERROR
    end: Record span end time

  trace_sampling:
    strategy: adaptive_sampling

    rules:
      - Sample 100% of traces with errors
      - Sample 100% of traces > 2000ms (slow)
      - Sample 10% of normal traces
      - Sample 1% of traces for specific endpoints

    head_sampling: Decision at trace start
    tail_sampling: Decision after trace completion (recommended)

  trace_propagation:
    headers:
      - traceparent: {version}-{trace_id}-{span_id}-{flags}
      - tracestate: vendor-specific data

    propagation_across:
      - HTTP requests (K0-K1 Bridge)
      - WebSocket messages
      - SSE events
      - Internal actor messages

  trace_backend:
    exporter: Jaeger or Tempo
    endpoint: http://jaeger:14268/api/traces
    batch_size: 512
    timeout_ms: 5000
```

## Alerting

**Source:** ADR-0016d

```yaml
alerting:
  alert_manager: Prometheus Alertmanager

  severity_levels:
    INFO:
      description: Informational, no action required
      notification: Slack (info channel)
      escalation: none

    WARNING:
      description: Issue detected, monitor closely
      notification: Slack (alerts channel)
      escalation: none
      examples:
        - High latency (P95 > budget but < critical)
        - Cache hit rate low
        - Queue size elevated

    ERROR:
      description: Service degradation, action required
      notification: Slack (alerts channel) + Email
      escalation: After 30 minutes
      examples:
        - Error rate > 5%
        - Component timeout
        - Backpressure active

    CRITICAL:
      description: Service outage, immediate action required
      notification: PagerDuty + Slack + Email + SMS
      escalation: Immediate
      examples:
        - Service down
        - Data loss risk
        - Security breach
        - Thermal critical

  alert_definitions:
    LatencyBudgetExceeded:
      severity: WARNING
      condition: p95_latency > budget for 5 minutes
      notification: Slack

    LatencyCritical:
      severity: ERROR
      condition: p95_latency > budget * 2 for 2 minutes
      notification: Slack + Email

    ErrorRateHigh:
      severity: ERROR
      condition: error_rate > 5% for 5 minutes
      notification: Slack + Email

    ServiceDown:
      severity: CRITICAL
      condition: up == 0 for 1 minute
      notification: PagerDuty + Slack + Email

    MemoryCritical:
      severity: CRITICAL
      condition: memory_usage > 95% for 2 minutes
      notification: PagerDuty + Slack

    ThermalCritical:
      severity: CRITICAL
      condition: thermal_state == CRITICAL for 1 minute
      notification: PagerDuty + Slack

  alert_routing:
    receiver: on_call_engineer
    group_by: [alertname, severity, component]
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h

  on_call_schedule:
    primary: Engineer A (Mon-Wed)
    secondary: Engineer B (Thu-Fri)
    backup: Manager (Sat-Sun)
    escalation_after: 15 minutes
```

## SLIs, SLOs, Error Budgets

```yaml
sli_slo_error_budgets:
  service_level_indicators:
    availability:
      definition: Percentage of successful requests
      measurement: (successful_requests / total_requests) * 100

    latency:
      definition: Percentage of requests < budget
      measurement: (requests_under_budget / total_requests) * 100

    error_rate:
      definition: Percentage of failed requests
      measurement: (failed_requests / total_requests) * 100

  service_level_objectives:
    availability_slo: 99.9% (three nines)
    latency_slo: 95% of requests < 150ms TTFT
    error_rate_slo: < 1% error rate

  error_budgets:
    availability:
      slo: 99.9%
      budget: 0.1% downtime
      monthly_budget: 43 minutes

    latency:
      slo: 95% under budget
      budget: 5% over budget allowed

    error_rate:
      slo: < 1%
      budget: 1% errors allowed

  budget_tracking:
    - Track SLI hourly
    - Calculate remaining error budget
    - Alert if budget < 20% remaining
    - Freeze releases if budget exhausted
```

## Observability Dashboard

```yaml
observability_dashboard:
  platform: Grafana

  dashboards:
    overview:
      - Request rate (req/s)
      - Error rate (%)
      - P95 latency (ms)
      - Active sessions
      - Memory usage

    kernel:
      - Agent lifecycle states
      - Orchestration latency
      - Planner latency
      - Protocol violations

    execution:
      - Tool call latency
      - Tool error rate
      - Model inference latency
      - Circuit breaker states

    state:
      - SessionState size
      - K0 read/write latency
      - Storage tier distribution
      - Coherence violations

    infrastructure:
      - KV cache hit rate
      - Thermal state
      - Backpressure active
      - Resource utilization
```

## Related Contracts

- Performance: `../performance/`
- Error Recovery: `../error_recovery/`
- Security: `../security/audit_logging.yaml`

---

**Last Updated:** 2025-10-13
