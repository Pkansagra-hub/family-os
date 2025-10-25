# K1 Observability Integration

**Status**: ✅ Active (Issue 1.1.3)
**Last Updated**: October 24, 2025

## Purpose

K1 does not run its own observability stack. Every metric and trace generated inside the intelligence module is forwarded to the existing K0 Prometheus + Tempo + Grafana deployment. This README explains the small glue layer that makes that possible and how to hook any K1 service, agent, or actor into it.

## Architecture Overview

```text
┌─────────────────────────────────────────────────┐
│ K1 Intelligence Module (service.name=k1_intelligence) │
│                                                 │
│ ┌─────────────────────────────────────────────┐ │
│ │ K1 Components (agents, bridges, actors, etc.) │ │
│ │   ↳ import k1.l5_infrastructure.observability │ │
│ │      • get_metrics()  → shared MetricsExporter │ │
│ │      • get_tracer()   → shared TracerFactory   │ │
│ └─────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │ emits metrics/spans
                       ↓
┌──────────────────────┴──────────────────────────┐
│ K0 Observability Stack                          │
│                                                 │
│ Prometheus scrape (localhost:9090/metrics)      │
│ Tempo OTLP HTTP (http://localhost:4318/v1/traces)│
│ Grafana dashboards (localhost:3000)             │
└─────────────────────────────────────────────────┘
```

All K1 signals share the `k1_intelligence_*` metric namespace and `service.name="k1_intelligence"`, so dashboards and alerts built for K0 automatically pick them up.

## Provided Modules

| Module | Purpose | Key APIs |
| --- | --- | --- |
| `k1/l5_infrastructure/observability/__init__.py` | Lazy wrappers around K0’s `MetricsExporter` and `TracerFactory`. | `get_metrics()`, `get_tracer()`, `COGNITIVE_TRACE_BAGGAGE_KEY` |
| `k1/l5_infrastructure/observability/tracing.py` | Shared tracing utilities used by the glue layer (e.g., baggage key). | Internal helpers (no direct imports required) |

There are no standalone metrics servers or dashboards in this package. Every new K1 component should call the APIs above directly and rely on the K0 kernel to expose `/metrics` and forward OTLP traces.

## Integration Guide

> ✳️ Use this checklist whenever you instrument a new service, bridge client, agent, or actor inside K1.

1. **Import the glue layer**

    ```python
   from k1.l5_infrastructure.observability import get_metrics, get_tracer
   metrics = get_metrics()
   tracer = get_tracer()
   ```

2. **Define metrics in module scope** using the exporter returned by `get_metrics()` (counters, histograms, gauges). Names are automatically prefixed with `k1_intelligence_`.
3. **Wrap work in spans** using the tracer factory. Always attach a `cognitive_trace_id` before you create spans so Tempo can link requests across K0↔K1.
4. **Propagate the trace** across async boundaries by storing the token returned from `attach_cognitive_trace()` and detaching it in a `finally` block.
5. **Validate** with `python -m ward test --search "observability"` before shipping.

### Metrics Pattern (example: agent mailbox processing)

```python
from k1.l5_infrastructure.observability import get_metrics

metrics = get_metrics()

mailbox_depth = metrics.gauge(
    "agent_mailbox_depth",
    "Current mailbox depth by agent and priority",
    labelnames=["agent_id", "priority"],
)

def record_mailbox_depth(agent_id: str, priority: str, depth: int) -> None:
    mailbox_depth.labels(agent_id=agent_id, priority=priority).set(depth)
```

### Tracing Pattern (example: actor processing loop)

```python
from k1.l5_infrastructure.observability import get_tracer

tracer = get_tracer()

async def handle_message(actor_id: str, message, cognitive_trace_id: str) -> None:
    token = tracer.attach_cognitive_trace(cognitive_trace_id)
    try:
        with tracer.span(
            "actor.handle_message",
            attributes={
                "actor_id": actor_id,
                "message_type": message.type,
            },
        ):
            await process(message)
    finally:
        tracer.detach(token)
```

### Forwarding to K0 Observability

- **Metrics**: `get_metrics()` registers collectors inside the global Prometheus registry owned by K0. As long as K0’s `/metrics` endpoint is running, K1 metrics appear automatically.
- **Traces**: Outside of Ward tests, `get_tracer()` sends spans to Tempo at `http://localhost:4318/v1/traces`. During tests the exporter is disabled so suites do not fail when the collector is offline.
- **Log correlation**: Always include the `cognitive_trace_id` in structured logs so operators can pivot between metrics, traces, and logs.

## Using the Observability APIs

### Counters and Histograms

```python
latency_ms = metrics.histogram(
    "planner_latency_ms",
    "Planner latency per band",
    labelnames=["band"],
    buckets=(10, 25, 50, 100, 200, 500, 1000, 2000, 5000),
)

latency_ms.labels(band="GREEN").observe(72.5)
```

### Span Context Helpers

```python
token = tracer.attach_cognitive_trace(envelope.cognitive_trace_id)
try:
    with tracer.span("k1.command_submit", attributes={"topic": envelope.topic}):
        await _post_command(envelope)
finally:
    tracer.detach(token)
```

## Metrics & Traces in the Stack

- **Metric prefix**: `k1_intelligence_*`
- **Common labels**: `band`, `status`, `agent_id`, `priority`, `tenant_id`, `space_id`
- **Tempo filters**: `service.name = "k1_intelligence"`, `baggage.cognitive_trace_id = "<id>"`

Example PromQL queries:

```promql
# Success rate by privacy band
rate(k1_intelligence_command_requests_total{status="success"}[5m])
  / rate(k1_intelligence_command_requests_total[5m])

# Actor latency P95
histogram_quantile(
  0.95,
  rate(k1_intelligence_actor_handle_latency_ms_bucket[5m])
)
```

## Prometheus Setup & Alerting

- **Compose files**: `k0/deployment/compose/generated/local-single-node/docker-compose.yml` (kernel) and `k0/deployment/compose/generated/local-single-node/local-single-node-telemetry.yml` (Prometheus, Tempo, Grafana, Alertmanager).
- **Configuration**: `k0/deployment/compose/generated/local-single-node/telemetry/prometheus.yml`
- **Alert rules**: `k0/deployment/compose/generated/local-single-node/generated/rules/*.yaml`

1. **Start the stack** from the repo root so K0 + telemetry services share the `k0-local` network:

     ```powershell
     docker compose -f k0/deployment/compose/generated/local-single-node/docker-compose.yml `
         -f k0/deployment/compose/generated/local-single-node/local-single-node-telemetry.yml up -d
     ```

2. **Verify scrape targets** at `http://localhost:9090/targets`. The `k1_intelligence` job (defined in `telemetry/prometheus.yml`) should be `UP`. If you relocate the K1 process or expose metrics on a different port, update that file and run `docker compose restart prometheus`.
3. **Tune alerting rules** by editing the YAML files under `generated/rules/`. Prometheus automatically reloads rule files; confirm they compiled via `http://localhost:9090/rules`.
4. **Check live alerts** via either `http://localhost:9090/alerts` (Prometheus view) or the bundled Alertmanager UI at `http://localhost:9093`. Filter by `service="k1_intelligence"` labels to see K1-specific pages.
5. **Smoke-test metrics emission** by running a workload, then executing a quick query such as `rate(k1_intelligence_command_requests_total[1m])` in the Prometheus expression browser to ensure fresh samples arrive.

## Grafana Dashboards for K1

- **Provisioning**: `k0/deployment/compose/generated/local-single-node/telemetry/grafana/provisioning` (data sources, folders)
- **Dashboards on disk**: `k0/deployment/compose/generated/local-single-node/generated/dashboards/`

1. **Sign in** to Grafana at `http://localhost:3000` (`admin` / `ChangeMe!` by default).
2. **Verify data sources**: the `Prometheus` source points to `http://prometheus:9090` and the `Tempo` source to `http://tempo:3200`; both are provisioned automatically.
3. **Clone an existing panel** (e.g., `Services / command_latency`) or start a blank dashboard. Use PromQL queries scoped to the shared namespace, such as:

    ```promql
    rate(k1_intelligence_agent_mailbox_depth_sum[5m])
    ```

    For span visualizations, switch the panel data source to `Tempo` and apply filters like `service.name="k1_intelligence"` and `cognitive_trace_id` baggage fields.
4. **Save dashboards back to Git** by exporting them as JSON and placing the file under `generated/dashboards/services/` with a descriptive name (for example, `k1_intelligence_overview.json`). Commit alongside any updated provisioning manifests so Grafana loads them automatically on the next start.
5. **Link panels to alerts** by embedding the Prometheus rules you created earlier—Grafana automatically tags panels that reference alerting queries, making it easier to pivot from firing alerts to detailed metric or trace panels.

## Testing

Run the focused Ward suite whenever you add or update instrumentation:

```powershell
python -m ward test --search "observability"
```

This validates the glue layer, metrics wiring, and trace propagation without requiring the Tempo collector to be present.

## References

- [ADR-0029](../../../docs/architecture/decisions/0029-prometheus-metrics-red-method.md) — Prometheus metrics strategy
- [ADR-0030](../../../docs/architecture/decisions/0030-intelligent-trace-sampling.md) — Trace sampling and `cognitive_trace_id`
- [ADR-0002d](../../../docs/architecture/decisions/0002d-observability-schema-actor-messaging.md) — Actor observability schema
- `k0/obs/metrics.py` & `k0/obs/tracing.py` — Source implementation reused by this module
