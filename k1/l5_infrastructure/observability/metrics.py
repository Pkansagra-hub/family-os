"""
Prometheus Metrics Exporter

Purpose: Export 50+ Prometheus metrics for K1 observability
Location: k1/l5_infrastructure/observability/metrics.py
Performance: <10ms metric emission

Primary ADRs:
- ADR-0029: Prometheus Metrics (50+ metrics across all layers)
- ADR-0029a: RED Method (rate, error, duration metrics)
- ADR-0029d: Infrastructure (thermal, CPU, cost metrics)
- ADR-0029e: Alerting (SLO alerts, routing, dashboards)
- ADR-0002d: Actor Fabric Observability (mailbox, router, supervisor metrics)

Related ADRs:
- ADR-0024: Performance Budgets (metric emission <10ms)
- ADR-0024a: Turn-Level Budgets (TTFT <150ms, E2E <2000ms)

Key Responsibilities:

1. Metric Types:
   - Counters: agent_hire_count, tool_execution_count, crash_count, error_total
   - Gauges: mailbox_depth, active_agent_count, kv_cache_hit_rate, thermal_state
   - Histograms: layer1_latency_ms, model_hub_inference_ms, tool_execution_ms

2. Metric Emission:
   - Push to Prometheus Pushgateway (HTTP POST to :9091/metrics)
   - Scrape endpoint: Prometheus scrapes K1 at :9090/metrics (pull model)
   - Scrape interval: 10s
   - <10ms emission overhead (<1% CPU)
   - Batch metrics every 10s

3. Metrics Catalog (50+ metrics):
   - Layer 1 (5 metrics): layer1_ttft_ms, layer1_vad_latency_ms, layer1_intent_classification_ms
   - Layer 2 (8 metrics): layer2_planning_latency_ms, layer2_orchestration_latency_ms, layer2_protocol_validation_ms
   - Layer 3 (12 metrics): layer3_agent_lifecycle_ms, layer3_model_hub_inference_ms, layer3_tool_execution_ms
   - Layer 4 (10 metrics): layer4_session_state_size_bytes, layer4_mailbox_depth, layer4_learning_cycle_ms
   - Layer 5 (15 metrics): layer5_event_bus_delivery_ms, layer5_thermal_temperature_celsius, layer5_circuit_breaker_state

4. RED Method (Rate, Error, Duration):
   - Rate: Requests per second (15 rate counters across layers)
   - Error: Errors per second (15 error counters)
   - Duration: P50/P95/P99 latency (15 histogram metrics)
   - RED metrics for: Turn execution, agent lifecycle, tool calls, K0 operations

5. Infrastructure Metrics:
   - Thermal: thermal_state gauge (0-4: COOL/WARM/HOT/CRITICAL/EMERGENCY), thermal_temperature_celsius, throttling_events_total
   - CPU: cpu_utilization_percent gauge, per-core tracking, throttling detection
   - Cost: cost_per_turn_usd histogram, budget_exceeded_total counter, monthly_burn_rate_usd gauge
   - Memory: memory_usage_mb gauge, kv_cache_size_mb, session_state_size_mb

6. Alerting (ADR-0029e):
   - SLO Alerts (10 alert rule groups):
     * TTFT >157ms (5% SLO buffer above 150ms target)
     * E2E latency >2100ms (5% buffer above 2000ms)
     * Error rate >1%
     * Backpressure events >10/min
     * Circuit breaker OPEN >5min
   - Alert Routing:
     * CRITICAL → PagerDuty (24/7 on-call)
     * WARNING → Slack (#k1-alerts)
     * INFO → Grafana (dashboard annotations)
   - Dashboards (4 dashboards):
     * Turn Overview: TTFT, E2E latency, error rate
     * Component Health: Circuit breaker, backpressure, thermal
     * Infrastructure: CPU, memory, thermal, cost
     * Incident Response: Error logs, slow traces, RED metrics

Performance Metrics:
- Metric emission: <10ms P95 (<5ms typical)
- Scrape interval: 10s
- Metric overhead: <1% CPU, <20MB memory
- Total metrics: 50+ (extensible)
- Cardinality: <1000 unique time series (label combinations)

Implementation Notes:
- Use prometheus_client library (Python)
- Push model: HTTP POST to Pushgateway for batch metrics
- Pull model: Prometheus scrapes /metrics endpoint
- Metric naming: layer{N}_{component}_{metric}_{unit}
- Label cardinality: Keep <10 labels per metric (prevent explosion)
- Histogram buckets: [10, 50, 100, 250, 500, 1000, 2000] ms

Example Usage:
    from k1.l5_infrastructure.observability import metrics

    # Increment counter
    metrics.agent_hire_count.labels(agent_type="planner").inc()

    # Set gauge
    metrics.mailbox_depth.labels(actor_id="planner_001").set(42)

    # Observe histogram
    metrics.layer1_ttft_ms.observe(140.5)

    # Record with context manager
    with metrics.layer2_planning_latency_ms.time():
        result = planner.plan(task)

Research Foundation:
- RED method (Tom Wilkie, Grafana Labs)
- Prometheus best practices (metric naming, cardinality, alerting)
- Google SRE Book (SLO-based alerting, error budgets)
- USE method (Brendan Gregg: Utilization, Saturation, Errors)

TODO:
- [ ] Implement MetricsExporter class with prometheus_client
- [ ] Define 50+ metrics (counters, gauges, histograms)
- [ ] Implement RED method metrics (rate, error, duration)
- [ ] Implement infrastructure metrics (thermal, CPU, cost, memory)
- [ ] Add Prometheus Pushgateway integration (HTTP POST)
- [ ] Add /metrics endpoint for Prometheus scraping (pull model)
- [ ] Implement metric batching (10s interval)
- [ ] Add SLO alert rule definitions (TTFT >157ms, E2E >2100ms, Error >1%)
- [ ] Add alert routing configuration (PagerDuty, Slack, Grafana)
- [ ] Add histogram bucket configuration (10-2000ms range)
- [ ] Add label validation (prevent cardinality explosion)
- [ ] Add unit tests for metric emission and batching
- [ ] Add integration tests with Prometheus scraping
"""

# TODO: Implement MetricsExporter with 50+ Prometheus metrics
