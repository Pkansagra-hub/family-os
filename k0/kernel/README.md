# Kernel Module

## Overview

The **kernel** module is the FastAPI/ASGI server runtime for K0, providing the HTTP/REST API layer, dependency injection, configuration management, admission control, and graceful lifecycle management. It orchestrates all K0 subsystems and exposes the envelope submission, receipt retrieval, and operational endpoints.

## Purpose

- **API Server**: FastAPI application with envelope submission, receipt queries, health checks
- **Configuration Management**: Pydantic-based settings with YAML loading and validation
- **Dependency Injection**: Managed lifecycle for registries, ledgers, schedulers, and observability
- **Admission Control**: Request throttling and resource limits before gate validation
- **Readiness Checks**: Comprehensive health checks for all subsystems
- **Graceful Shutdown**: Clean shutdown with connection draining and resource cleanup
- **Observability**: Metrics, tracing, and structured logging integration

## Architecture

The kernel follows **layered service architecture**:

```text
HTTP Request → FastAPI Router → Admission Control → Gate → UoW → WAL → Bus → Sinks
                     ↓                                                  ↓
              Dependencies (DI)                                    Outbox Worker
              - SchemaRegistry                                     - Driver fanout
              - ProvisioningLedger
              - IdempotencyLedger
              - QoS Scheduler
              - Metrics/Tracing
```

## Core Components

### 1. `app.py` - FastAPI Application

Defines the FastAPI application with all endpoints and middleware.

**Endpoints:**

- **`POST /v1/envelopes`** - Submit envelope for processing
  - Request: JSON envelope + body (multipart or JSON)
  - Response: Receipt ID (202 Accepted)
  - Flow: Admission → Gate → UoW → WAL → Return receipt

- **`GET /v1/receipts/{receipt_id}`** - Retrieve receipt by ID
  - Response: Receipt metadata (status, wal_pos, timestamp)

- **`GET /health/ready`** - Readiness probe
  - Response: 200 OK if all subsystems ready, 503 otherwise

- **`GET /health/live`** - Liveness probe
  - Response: 200 OK if server responsive

- **`GET /metrics`** - Prometheus metrics endpoint
  - Response: OpenMetrics format metrics

**Middleware:**

- Request ID generation
- Structured logging context
- Exception handling
- CORS (configurable)
- Request timing

### 2. `config.py` - Configuration Management

Pydantic models for kernel settings with YAML loading.

**Class: `KernelSettings`**

Root settings model with nested sections:

```python
class KernelSettings(BaseSettings):
    version: str                     # Config version
    environment: str                 # dev/staging/production
    server: ServerSettings           # Host, port, log_level, timeouts
    retention: RetentionSettings     # WAL retention policies
    qos: QoSSettings                 # Scheduler profile
    security: SecuritySettings       # Key rotation settings
    telemetry: TelemetrySettings     # OTLP, Prometheus, metrics namespace
    database: DatabaseSettings       # Database path, pool settings
```

**Nested Models:**

- **`ServerSettings`**: host, port, log_level, timeout_graceful_shutdown
- **`RetentionSettings`**: wal_days, wal_max_events
- **`QoSSettings`**: scheduler_profile (balanced, high-throughput, low-latency)
- **`SecuritySettings`**: key_rotation_grace_window_hours, key_rotation_max_grace_hours
- **`TelemetrySettings`**: otlp_endpoint, prometheus_enabled, metrics_namespace
- **`DatabaseSettings`**: path, max_connections, timeout

**Loading Configuration:**

```python
from k0.kernel.config import KernelSettings

# Load from default path (config/kernel.yaml)
settings = KernelSettings.load()

# Load from custom path
settings = KernelSettings.load(config_path="config/prod.yaml")

# Load with overrides
settings = KernelSettings.load(overrides={"server.port": 9090})
```

### 3. `dependencies.py` - Dependency Injection

Manages FastAPI dependencies with singleton lifecycle.

**Dependencies:**

- **`get_schema_registry()`** - SchemaRegistry singleton
- **`get_provisioning_ledger()`** - ProvisioningLedger singleton
- **`get_idempotency_ledger()`** - IdempotencyLedger singleton
- **`get_qos_scheduler()`** - Scheduler singleton
- **`get_metrics_exporter()`** - MetricsExporter singleton
- **`get_tracer_factory()`** - TracerFactory singleton
- **`get_minimal_gate()`** - MinimalGate singleton
- **`get_settings()`** - KernelSettings singleton

**Lifecycle Hooks:**

- **`startup_event()`** - Initialize subsystems, load caches, start workers
- **`shutdown_event()`** - Graceful shutdown, close connections, flush metrics

**Example:**

```python
from fastapi import Depends
from k0.kernel.dependencies import get_minimal_gate, get_settings
from k0.gate import MinimalGate
from k0.kernel.config import KernelSettings

@app.post("/v1/envelopes")
async def submit_envelope(
    gate: MinimalGate = Depends(get_minimal_gate),
    settings: KernelSettings = Depends(get_settings),
):
    outcome = gate.validate(envelope, body)
    # ...
```

### 4. `admission.py` - Admission Control

Pre-gate request validation and resource throttling.

**Class: `AdmissionController`**

**Checks:**

1. **Rate Limiting** - Requests per second per tenant
2. **Concurrency Limits** - Max concurrent requests per tenant
3. **Payload Size** - Envelope and body size limits
4. **Content-Type Validation** - Supported media types
5. **Tenant Quotas** - Daily/monthly envelope quotas

**Example:**

```python
from k0.kernel.admission import AdmissionController

controller = AdmissionController(
    max_envelope_bytes=64_000,
    max_body_bytes=4_194_304,
    max_concurrent_per_tenant=100,
)

result = controller.check(envelope, body, tenant_id="tenant_123")
if not result.admitted:
    return {"error": result.reason}, 429  # Too Many Requests
```

**Rejection Reasons:**

- `RATE_LIMIT_EXCEEDED` - Tenant exceeded RPS quota
- `CONCURRENCY_LIMIT_EXCEEDED` - Too many concurrent requests
- `PAYLOAD_TOO_LARGE` - Envelope or body exceeds size limits
- `UNSUPPORTED_CONTENT_TYPE` - Invalid Content-Type header
- `QUOTA_EXCEEDED` - Daily/monthly envelope quota exhausted

### 5. `readiness.py` - Health Checks

Comprehensive readiness checks for all subsystems.

**Class: `ReadinessChecker`**

**Checks:**

1. **Database Connectivity** - SQLite connection test
2. **Schema Registry** - Cache loaded
3. **Provisioning Ledger** - Table accessible
4. **QoS Scheduler** - Scheduler operational
5. **Outbox Worker** - Worker thread alive
6. **Bus Dispatcher** - Dispatcher initialized

**Example:**

```python
from k0.kernel.readiness import ReadinessChecker

checker = ReadinessChecker(
    registry=registry,
    provisioning=provisioning,
    scheduler=scheduler,
)

result = checker.check()
if result.ready:
    return {"status": "ready"}, 200
else:
    return {"status": "not ready", "failures": result.failures}, 503
```

**Readiness Response:**

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "schema_registry": "ok",
    "provisioning_ledger": "ok",
    "qos_scheduler": "ok",
    "outbox_worker": "ok",
    "bus_dispatcher": "ok"
  },
  "uptime_seconds": 123.45
}
```

### 6. `main.py` - Server Entry Point

Uvicorn server launcher with graceful shutdown handling.

**Function: `run(settings, host, port, log_level, timeout_graceful_shutdown)`**

Starts the FastAPI server with Uvicorn ASGI server.

**Features:**

- **Graceful Shutdown** - SIGTERM/SIGINT handling with connection draining
- **Async Workers** - Configurable worker count
- **Access Logging** - Request/response logging
- **Reload** - Auto-reload in development mode

**Example:**

```python
from k0.kernel.main import run
from k0.kernel.config import KernelSettings

settings = KernelSettings.load()
run(
    settings=settings,
    host="0.0.0.0",
    port=8080,
    log_level="info",
    timeout_graceful_shutdown=30,
)
```

**CLI Integration:**

```bash
# Via k0ctl
k0ctl serve --host 0.0.0.0 --port 8080 --log-level debug

# Direct Python
python -m k0.kernel.main
```

## API Endpoints

### POST /v1/envelopes

Submit envelope for processing.

**Request:**

```bash
curl -X POST http://localhost:8080/v1/envelopes \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant_123",
    "space_id": "space_456",
    "device_id": "device_789",
    "schema_uri": "envelope.schema.json",
    "schema_version": "1.0.0",
    "payload_sha256": "abc123...",
    "sig": "signature_base64...",
    "body": "envelope_payload"
  }'
```

**Response (Success):**

```json
{
  "receipt_id": "rcpt_1736934642_abc123",
  "wal_pos": 42,
  "status": "committed"
}
```

**Response (Rejection):**

```json
{
  "error": "SIGNATURE_INVALID",
  "details": "Signature verification failed for device_789"
}
```

### GET /v1/receipts/{receipt_id}

Retrieve receipt metadata.

**Request:**

```bash
curl http://localhost:8080/v1/receipts/rcpt_1736934642_abc123
```

**Response:**

```json
{
  "receipt_id": "rcpt_1736934642_abc123",
  "wal_pos": 42,
  "status": "committed",
  "tenant_id": "tenant_123",
  "space_id": "space_456",
  "committed_ts": "2025-01-15T10:30:42Z"
}
```

### GET /health/ready

Readiness probe for Kubernetes/orchestration.

**Response (Ready):**

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "schema_registry": "ok",
    "provisioning_ledger": "ok"
  }
}
```

**Response (Not Ready):**

```json
{
  "status": "not ready",
  "failures": ["schema_registry: cache not loaded"]
}
```

### GET /metrics

Prometheus metrics endpoint.

**Response:**

```text
# HELP k0_envelopes_submitted_total Total envelopes submitted
# TYPE k0_envelopes_submitted_total counter
k0_envelopes_submitted_total{tenant="tenant_123"} 1234

# HELP k0_gate_rejections_total Total gate rejections
# TYPE k0_gate_rejections_total counter
k0_gate_rejections_total{reason="SIGNATURE_INVALID",tenant="tenant_123"} 5
```

## Configuration Integration

### Loading Settings

```python
from k0.kernel.config import KernelSettings

# Default path (config/kernel.yaml)
settings = KernelSettings.load()

# Custom path
settings = KernelSettings.load(config_path="config/prod.yaml")

# With overrides
settings = KernelSettings.load(overrides={
    "server.port": 9090,
    "qos.scheduler_profile": "high-throughput",
})
```

### Environment Variables

Settings can reference environment variables:

```yaml
# config/kernel.yaml
database:
  path: "${K0_DB_PATH}"  # Resolved from environment
```

### Validation

Pydantic validates all settings at load time:

```python
try:
    settings = KernelSettings.load()
except ValidationError as e:
    print(f"Invalid configuration: {e}")
```

## Integration Points

### With Gate & UoW

```python
from k0.kernel.app import app
from k0.gate import MinimalGate
from k0.uow import UnitOfWork
from fastapi import Depends

@app.post("/v1/envelopes")
async def submit_envelope(
    envelope: dict,
    body: bytes,
    gate: MinimalGate = Depends(get_minimal_gate),
    uow: UnitOfWork = Depends(get_unit_of_work),
):
    # Validate
    outcome = gate.validate(envelope, body)
    if not outcome.accepted:
        return {"error": outcome.reason}, 400

    # Commit to WAL
    with uow.begin() as conn:
        receipt = uow.append_wal_entry(envelope, body, conn)
        conn.commit()

    return {"receipt_id": receipt.receipt_id}, 202
```

### With Observability

```python
from k0.obs import configure_structured_logging, MetricsExporter, TracerFactory

# Configure logging
configure_structured_logging(level="INFO", force=True)

# Initialize metrics
metrics = MetricsExporter(namespace="k0")

# Initialize tracing
tracer_factory = TracerFactory(service_name="k0-kernel")
```

### With Scheduler

```python
from k0.qos import Scheduler

scheduler = Scheduler(profile="balanced")
# Used by BusDispatcher for rate limiting
```

## Testing

**Unit Tests:**

- Configuration loading and validation
- Dependency injection lifecycle
- Admission control logic
- Readiness check behavior

**Integration Tests:**

- End-to-end envelope submission flow
- Health check responses
- Metrics emission
- Graceful shutdown

**Example Test:**

```python
from fastapi.testclient import TestClient
from k0.kernel.app import app

client = TestClient(app)

def test_submit_envelope():
    response = client.post("/v1/envelopes", json={
        "tenant_id": "tenant_123",
        # ... envelope fields
    })
    assert response.status_code == 202
    assert "receipt_id" in response.json()
```

## Related Modules

- **k0.gate**: Envelope validation
- **k0.uow**: Unit of work and transactions
- **k0.obs**: Observability (metrics, tracing, logging)
- **k0.qos**: QoS scheduler
- **k0.cli**: CLI integration (k0ctl serve)
- **k0.storage**: Receipts, WAL, outbox

## Related ADRs

- **K0 README §5**: API surface contract
- **K0 README §8**: Graceful shutdown
- **ADR-003**: FastAPI server architecture
- **Gap 8**: Admission control

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "k0.cli.k0ctl", "serve", "--host", "0.0.0.0", "--port", "8080"]
```

### Kubernetes

```yaml
apiVersion: v1
kind: Service
metadata:
  name: k0-kernel
spec:
  selector:
    app: k0-kernel
  ports:
  - port: 8080
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k0-kernel
spec:
  replicas: 3
  selector:
    matchLabels:
      app: k0-kernel
  template:
    metadata:
      labels:
        app: k0-kernel
    spec:
      containers:
      - name: k0-kernel
        image: k0-kernel:latest
        ports:
        - containerPort: 8080
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
```
