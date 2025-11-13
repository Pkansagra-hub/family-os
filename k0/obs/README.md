# Obs (Observability) Module

## Overview

The **obs** module provides comprehensive observability infrastructure for K0, implementing the three pillars of observability: metrics (Prometheus), tracing (OpenTelemetry), and structured logging. It enables production monitoring, debugging, and performance analysis across all K0 subsystems.

## Purpose

- **Metrics**: Prometheus-compatible metrics with counters, gauges, histograms
- **Tracing**: OpenTelemetry distributed tracing with span hierarchies and baggage
- **Logging**: Structured JSON logging with contextual bindings and PII redaction
- **Events**: Generic observability event emitter for custom telemetry
- **Cognitive Traces**: Propagate trace IDs across K0 operations for end-to-end correlation
- **Performance Budgets**: Track P50/P95/P99 latencies against SLO targets

## Architecture

Observability follows **three-pillar pattern** with unified trace ID propagation:

```text
K0 Operation → Cognitive Trace ID → [Metrics, Tracing, Logging]
                      ↓
         Context Propagation (ContextVar)
                      ↓
         Unified Correlation Across Pillars
```

**Integration Flow:**

```text
Application Code
    ↓
MetricsExporter.emit() → Prometheus /metrics endpoint
TracerFactory.span() → OpenTelemetry Collector
Logger.info() → Structured JSON stdout
```

## Core Components

### 1. `metrics.py` - Prometheus Metrics

**Class: `MetricsExporter`**

Thread-safe metrics collection with Prometheus exposition.

**Metric Types:**

- **Counter** - Monotonically increasing (total requests, errors)
- **Gauge** - Current value (active connections, queue depth)
- **Histogram** - Distribution with buckets (latency, payload size)
- **Summary** - Quantiles (P50, P95, P99)

**Key Methods:**

- **`emit(name, value=1.0, **labels)`** - Increment counter or set gauge
  ```python
  metrics.emit("envelopes_submitted_total", tenant="tenant_123")
  ```

- **`observe(name, value, labels={}, buckets=None)`** - Record histogram sample
  ```python
  metrics.observe("gate_latency_seconds", 0.042, labels={"outcome": "success"})
  ```

- **`set_gauge(name, value, **labels)`** - Set gauge value
  ```python
  metrics.set_gauge("outbox_pending_entries", 42, driver="sqlite")
  ```

- **`expose()`** - Generate Prometheus exposition format
  ```python
  metrics_text = metrics.expose()  # OpenMetrics format
  ```

**Example Usage:**

```python
from k0.obs import MetricsExporter

metrics = MetricsExporter(namespace="k0")

# Counter
metrics.emit("requests_total", method="POST", status="200")

# Histogram (latency)
metrics.observe("request_duration_seconds", 0.123, labels={"endpoint": "/v1/envelopes"})

# Gauge
metrics.set_gauge("active_connections", 42)

# Custom buckets
metrics.observe(
    "payload_size_bytes",
    1024,
    buckets=[100, 1000, 10000, 100000, 1000000],
)
```

**Default Histogram Buckets:**

```python
DEFAULT_LATENCY_BUCKETS = [
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
]  # seconds
```

**Metric Naming Convention:**

- Use snake_case
- Include unit suffix: `_seconds`, `_bytes`, `_total`
- Namespace prefix: `k0_` (configurable)

**Common Metrics:**

```text
k0_envelopes_submitted_total{tenant="tenant_123"} - Counter
k0_gate_rejections_total{reason="SIGNATURE_INVALID"} - Counter
k0_gate_latency_seconds{outcome="success"} - Histogram
k0_wal_position{tenant="tenant_123"} - Gauge
k0_outbox_pending_entries{driver="sqlite"} - Gauge
k0_bus_dispatch_latency_seconds{topic="envelopes"} - Histogram
```

**Exposition Endpoint:**

```python
from fastapi import FastAPI
from k0.obs import MetricsExporter

app = FastAPI()
metrics = MetricsExporter()

@app.get("/metrics")
async def get_metrics():
    return metrics.expose()
```

### 2. `tracing.py` - OpenTelemetry Tracing

**Class: `TracerFactory`**

OpenTelemetry span management with cognitive trace ID propagation.

**Key Methods:**

- **`span(name, kind, attributes={})`** - Create span context manager
  ```python
  with tracer.span("gate.validate", kind=SpanKind.INTERNAL):
      outcome = gate.validate(envelope, body)
  ```

- **`new_trace_id()`** - Generate new cognitive trace ID
  ```python
  trace_id = tracer.new_trace_id()  # Returns UUID4 string
  ```

- **`attach_cognitive_trace(trace_id)`** - Set active trace ID in context
  ```python
  token = tracer.attach_cognitive_trace("trace_abc123")
  # ... operations use this trace_id
  tracer.detach(token)
  ```

- **`get_current_trace_id()`** - Retrieve active trace ID
  ```python
  trace_id = tracer.get_current_trace_id()  # From ContextVar
  ```

**Span Attributes:**

```python
attributes = {
    "k0.tenant_id": "tenant_123",
    "k0.space_id": "space_456",
    "k0.device_id": "device_789",
    "k0.schema_uri": "envelope.schema.json",
    "k0.wal_position": 42,
    "http.method": "POST",
    "http.status_code": 202,
}

with tracer.span("envelope.submit", attributes=attributes):
    # ... operation
```

**Span Kinds:**

- `SpanKind.INTERNAL` - Internal operation
- `SpanKind.SERVER` - HTTP server request
- `SpanKind.CLIENT` - HTTP client request
- `SpanKind.PRODUCER` - Message producer (bus dispatch)
- `SpanKind.CONSUMER` - Message consumer (outbox worker)

**Example Usage:**

```python
from k0.obs import TracerFactory
from opentelemetry.trace import SpanKind

tracer = TracerFactory(service_name="k0-kernel")

# Create span
with tracer.span("gate.validate", kind=SpanKind.INTERNAL) as span:
    span.set_attribute("envelope.size_bytes", 1024)
    outcome = gate.validate(envelope, body)
    span.set_attribute("gate.outcome", "accepted" if outcome.accepted else "rejected")

# Nested spans
with tracer.span("envelope.submit", kind=SpanKind.SERVER):
    with tracer.span("gate.validate"):
        # ... gate validation
    with tracer.span("wal.append"):
        # ... WAL write
    with tracer.span("bus.dispatch", kind=SpanKind.PRODUCER):
        # ... bus fan-out
```

**Cognitive Trace Propagation:**

```python
# Generate trace ID at API boundary
trace_id = tracer.new_trace_id()
token = tracer.attach_cognitive_trace(trace_id)

try:
    # All operations inherit trace_id
    outcome = gate.validate(envelope, body)  # trace_id in logs/spans
    receipt = uow.append_wal_entry(...)     # trace_id in WAL
    bus.dispatch(messages)                  # trace_id in bus context
finally:
    tracer.detach(token)
```

**OpenTelemetry Configuration:**

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure OTLP exporter
provider = TracerProvider()
exporter = OTLPSpanExporter(endpoint="http://otel-collector:4317")
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)

# Use TracerFactory
tracer = TracerFactory(service_name="k0-kernel")
```

### 3. `logging.py` - Structured Logging

**Function: `configure_structured_logging(level, sensitive_keys, mask, force)`**

Configure Python logging with structured JSON output.

**Parameters:**

- `level` - Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `sensitive_keys` - List of keys to redact from logs (e.g., `["password", "secret"]`)
- `mask` - Replacement string for redacted values (default: `"***REDACTED***"`)
- `force` - Force reconfiguration even if already configured

**Example:**

```python
from k0.obs import configure_structured_logging

configure_structured_logging(
    level="INFO",
    sensitive_keys=["password", "api_key", "hmac_secret"],
    mask="***REDACTED***",
    force=True,
)
```

**Structured Log Format:**

```json
{
  "timestamp": "2025-01-15T10:30:42.123Z",
  "level": "INFO",
  "logger": "k0.gate.minimal_gate",
  "message": "Envelope validated successfully",
  "cognitive_trace_id": "trace_abc123",
  "tenant_id": "tenant_123",
  "device_id": "device_789",
  "outcome": "accepted"
}
```

**Context Binding:**

```python
from k0.obs.logging import bind_log_context, reset_log_context
import structlog

# Bind context for all subsequent logs
token = bind_log_context(
    cognitive_trace_id="trace_abc123",
    tenant_id="tenant_123",
    device_id="device_789",
)

logger = structlog.get_logger()
logger.info("Processing envelope")  # Includes context

reset_log_context(token)
```

**PII Redaction:**

```python
# Configure sensitive keys
configure_structured_logging(
    level="INFO",
    sensitive_keys=["email", "phone", "ssn", "credit_card"],
)

# Logs automatically redact
logger.info("User registered", email="user@example.com")
# Output: {"email": "***REDACTED***", "message": "User registered"}
```

**Logger Usage:**

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Gate validation started", envelope_size=1024)
logger.info("Envelope accepted", receipt_id="rcpt_123")
logger.warning("Schema deprecated", schema_uri="old.schema.json")
logger.error("Signature verification failed", device_id="device_789")
logger.critical("Database connection lost")
```

### 4. `events.py` - Observability Events

**Class: `ObservabilityEmitter`**

Generic event emitter for custom telemetry.

**Key Methods:**

- **`emit(payload)`** - Emit structured event
  ```python
  emitter.emit({
      "event": "envelope_submitted",
      "tenant_id": "tenant_123",
      "wal_pos": 42,
  })
  ```

- **`configure_sink(sink)`** - Set event sink (stdout, Kafka, SQS, etc.)
  ```python
  emitter.configure_sink(lambda event: print(json.dumps(event)))
  ```

**Example Usage:**

```python
from k0.obs import ObservabilityEmitter

emitter = ObservabilityEmitter()

# Emit custom event
emitter.emit({
    "event": "gate_rejection",
    "reason": "SIGNATURE_INVALID",
    "tenant_id": "tenant_123",
    "device_id": "device_789",
    "timestamp": "2025-01-15T10:30:42Z",
})
```

**Common Events:**

```python
# Gate validation
{"event": "signature_verification", "outcome": "success"}
{"event": "schema_validation", "outcome": "failure", "reason": "SCHEMA_BLOCKED"}

# Provisioning
{"event": "device_provisioned", "device_id": "device_123"}
{"event": "key_rotated", "device_id": "device_123", "key_version": "v2"}

# Idempotency
{"event": "duplicate_detected", "idem_key": "idem:abc123"}

# Outbox
{"event": "driver_applied", "driver": "sqlite", "wal_pos": 42}
```

## Integration Points

### With Gate

```python
from k0.gate import MinimalGate
from k0.obs import MetricsExporter, TracerFactory, configure_structured_logging

configure_structured_logging(level="INFO")
metrics = MetricsExporter(namespace="k0")
tracer = TracerFactory(service_name="k0-gate")

gate = MinimalGate(metrics=metrics, observability=emitter)

with tracer.span("gate.validate"):
    outcome = gate.validate(envelope, body)
    if outcome.accepted:
        metrics.emit("gate_accepted_total", tenant=tenant_id)
    else:
        metrics.emit("gate_rejections_total", reason=outcome.reason)
```

### With Bus

```python
from k0.bus import BusDispatcher, latency_metrics_middleware, tracing_middleware
from k0.obs import MetricsExporter, TracerFactory

metrics = MetricsExporter()
tracer = TracerFactory()

dispatcher = BusDispatcher(scheduler=scheduler)
dispatcher.register_middleware(latency_metrics_middleware(metrics))
dispatcher.register_middleware(tracing_middleware(tracer_factory=tracer))
```

### With UoW

```python
from k0.uow import UnitOfWork
from k0.obs import MetricsExporter

metrics = MetricsExporter()
uow = UnitOfWork(metrics=metrics)

with uow.begin() as conn:
    metrics.emit("wal_append_started")
    receipt = uow.append_wal_entry(envelope, body, conn)
    metrics.observe("wal_append_latency_seconds", duration)
    conn.commit()
```

## Performance Considerations

**Metrics:**

- Counter increment: O(1) (atomic operation)
- Histogram sample: O(log n) (binary search in buckets)
- Exposition: O(m) where m = number of metrics

**Tracing:**

- Span creation: ~1-5 µs overhead per span
- Attribute addition: O(1) per attribute
- Batch export: Asynchronous, non-blocking

**Logging:**

- Structured log: ~10-50 µs per log statement
- Context binding: O(1) (ContextVar)
- PII redaction: O(k) where k = number of sensitive keys

**Best Practices:**

- Use sampling for high-volume tracing (e.g., 1% sample rate)
- Avoid excessive logging in hot paths
- Batch metrics when possible
- Use gauge for current state, counter for totals

## Configuration

### Metrics

```python
from k0.obs import MetricsExporter

metrics = MetricsExporter(
    namespace="k0",                    # Metric prefix
    observability_emitter=emitter,     # Optional event emitter
)
```

### Tracing

```python
from k0.obs import TracerFactory

tracer = TracerFactory(
    service_name="k0-kernel",          # Service identifier
    otlp_endpoint="http://localhost:4317",  # OTLP collector
)
```

### Logging

```python
from k0.obs import configure_structured_logging

configure_structured_logging(
    level="INFO",                      # Log level
    sensitive_keys=["password"],       # PII redaction
    mask="***REDACTED***",             # Redaction string
    force=True,                        # Reconfigure
)
```

## Testing

**Unit Tests:**

- Metrics emission correctness
- Span attribute propagation
- Log context binding
- PII redaction

**Integration Tests:**

- End-to-end trace propagation
- Metrics exposition format
- Structured log output

**Example Test:**

```python
from k0.obs import MetricsExporter

def test_metrics_counter():
    metrics = MetricsExporter()
    metrics.emit("test_counter", label="value")

    exposition = metrics.expose()
    assert "test_counter{label=\"value\"}" in exposition
```

## Related Modules

- **k0.gate**: Observability integration for validation
- **k0.bus**: Middleware for metrics/tracing
- **k0.kernel**: Metrics endpoint `/metrics`
- **k0.uow**: Transaction observability

## Related ADRs

- **K0 README §9**: Observability architecture
- **ADR-004**: Structured logging standards
- **Gap 43**: Schema cache metrics
- **Gap 47**: Gate rejection metrics

## Grafana Dashboards

**Sample Metrics Queries:**

```promql
# Envelope submission rate
rate(k0_envelopes_submitted_total[5m])

# Gate rejection rate by reason
rate(k0_gate_rejections_total[5m]) by (reason)

# P95 gate latency
histogram_quantile(0.95, rate(k0_gate_latency_seconds_bucket[5m]))

# Active outbox entries
k0_outbox_pending_entries

# WAL position growth
rate(k0_wal_position[5m])
```
