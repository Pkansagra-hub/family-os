# K1 Observability - Thin Adapter to K0 Stack

## Architecture Philosophy

**K1 does NOT implement its own observability infrastructure.** Instead, K1 forwards all telemetry to K0's existing Prometheus/Grafana/Tempo stack via the K0 Bridge Observability Port.

```
┌─────────────────────────────────────────────────────────┐
│ K1 Components                                           │
│ (Orchestrator, Planner, Model Hub, Admission, etc.)    │
└───────────────────┬─────────────────────────────────────┘
                    │ emit_metric()
                    │ trace_span()
                    │ log_event()
                    ▼
┌─────────────────────────────────────────────────────────┐
│ k1.l5_infrastructure.observability                      │
│ (This module - thin adapter)                            │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTP/2
                    │ POST /k0/obs/metrics
                    │ POST /k0/obs/traces
                    │ POST /k0/obs/logs
                    ▼
┌─────────────────────────────────────────────────────────┐
│ k1.bridge_k0.ports.observability_port                   │
│ (K0 Observability Port - receives K1 telemetry)        │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│ K0 Observability Stack (Already Implemented)            │
│ - Prometheus (metrics scraping, alerting)               │
│ - Grafana (dashboards, visualization)                   │
│ - Tempo (distributed tracing)                           │
│ - Loki (log aggregation)                                │
└─────────────────────────────────────────────────────────┘
```

## Benefits

1. **No Duplicate Infrastructure**: K0 already has Prometheus/Grafana/Tempo
2. **Unified Dashboards**: K0+K1 metrics in same dashboard
3. **Simpler Deployment**: No separate observability stack for K1
4. **Cost Efficient**: Reuse existing resources
5. **Single Source of Truth**: All telemetry in K0

## Usage

### Metrics

```python
from k1.l5_infrastructure.observability import emit_counter, emit_gauge, emit_histogram

# Increment counter
emit_counter("k1.orchestrator.agent_hired_total", labels={"agent_type": "planner"})

# Set gauge
emit_gauge("k1.model_hub.active_sessions", value=42)

# Record histogram (latency)
emit_histogram("k1.admission.pipeline_latency_ms", value=8.5)
```

### Tracing

```python
from k1.l5_infrastructure.observability import trace_span

with trace_span("orchestrator.3_phase_coordination", trace_id=trace_id) as span:
    span.set_attribute("agent_type", "planner")
    span.set_attribute("session_id", session_id)
    # ... do work ...
    span.set_status("ok")
```

### Logging

```python
from k1.l5_infrastructure.observability import info, error

info("Agent hire completed", component="orchestrator",
     agent_id="agent_planner_1", latency_ms=150)

error("Tool execution failed", component="tool_runner",
      tool_id="search_web", error="Timeout")
```

## K0 Observability Port Endpoints

The K0 observability stack exposes these endpoints for K1 telemetry:

- **GET /k0/metrics**: Prometheus-compatible metrics (scraped by external Prometheus)
- **GET /k0/traces**: OpenTelemetry trace export (OTLP, pulled by external Tempo)
- **GET /k0/logs**: Structured logs via logging system (pulled by external Loki)
- **GET /k0/obs/health**: Health check (K1 pings every 30s)

## Batching & Performance

- **Metrics**: Batch 100 metrics, flush every 1s
- **Traces**: Batch 50 spans, flush every 500ms
- **Logs**: Batch 200 logs, flush every 1s
- **Latency**: <5ms P95 to K0 port (local HTTP/2)

## Implementation Status

🚧 **STUB - Awaiting Implementation**

All files are stubs with comprehensive documentation. Actual implementation forwards telemetry to K0 via `k1.bridge_k0.ports.observability_port`.

## Files

- `__init__.py`: Module exports, convenience functions
- `k0_client.py`: HTTP/2 client for K0 observability port
- `metrics.py`: Prometheus metric emission
- `tracing.py`: OpenTelemetry trace spans
- `logging.py`: Structured JSON logging

## TODO

- [ ] Implement K0 observability port client (HTTP/2)
- [ ] Implement metric batching and forwarding
- [ ] Implement trace span forwarding (OpenTelemetry format)
- [ ] Implement log forwarding (JSON batches)
- [ ] Add health check loop (30s interval)
- [ ] Integrate cognitive_trace_id propagation
- [ ] Add retry logic for K0 port failures
- [ ] Add metrics for observability client itself (meta-metrics)

## Related ADRs

- **ADR-0001a**: K0 Bridge Architecture (Observability Port)
- **ADR-0002d**: Actor Fabric Observability (metrics/traces/logs pattern)
- **ADR-0004d**: Layer Testing & Observability (per-layer metrics)

## Related Issues

- Epic 5.2: Observability Infrastructure
- Milestone M14: K0 Bridge Integration
