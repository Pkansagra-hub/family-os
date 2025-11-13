# K0 Operations Scripts

**Purpose**: Operational scripts for local kernel bootstrapping, traffic generation, deployment automation, and performance validation.

**Layer**: Operations & Automation
**Category**: DevOps scripts and utilities
**Related ADRs**: ADR-0110 (Local Development), ADR-0111 (Traffic Generation), ADR-0112 (Performance Validation)

---

## Overview

The scripts folder contains **operational automation** for:

1. **Local kernel bootstrapping**: Database initialization, schema migrations, device provisioning
2. **Traffic generation**: Burn-in testing with configurable scenarios (baseline, burst, mixed, sustained, comprehensive)
3. **Deployment automation**: PowerShell scripts for staging/Azure deployments
4. **Performance validation**: Recording rules latency comparison for Prometheus optimization

**Usage Context**: Development workflows, CI/CD pipelines, staging burn-in, production validation

---

## Repository Files & Functions

### 1. `bootstrap_local_kernel.py`

**Purpose**: Bootstrap local kernel database with schemas, migrations, and provisioning state.

#### Functions

```python
def bootstrap(database_path: Path) -> None
```

- **Purpose**: Initialize local kernel database for development
- **Steps**:
  1. Load environment overrides from `.env` files
  2. Apply SQLite schema migrations
  3. Register default profile schema
  4. Provision default device with Ed25519 keys
  5. Log provisioning details

**Usage**:

```bash
# Default database path (compose bundle)
python scripts/bootstrap_local_kernel.py

# Custom database path
python scripts/bootstrap_local_kernel.py --database /path/to/k0_kernel.db

# Verbose logging
python scripts/bootstrap_local_kernel.py --verbose
```

**Default Paths**:

```python
DEFAULT_DB_PATH = "k0/deployment/compose/generated/local-single-node/data/k0_kernel.db"
```

**Algorithm**:

```python
def bootstrap(database_path: Path):
    # 1. Load environment overrides
    overrides = load_env_overrides()

    # 2. Create database parent directory
    database_path.parent.mkdir(parents=True, exist_ok=True)

    # 3. Apply migrations
    results = apply_migrations(database_path)
    logger.info(f"Migrations applied: {results}")

    # 4. Load default profile
    profile = default_profile()
    configure_pool(database_path)

    # 5. Provision device
    try:
        with connection_scope() as conn:
            # Register schema
            registry.upsert(SchemaRecord(
                uri=profile.schema_uri,
                version=profile.schema_version,
                sha256=profile.schema_sha,
                status="ACTIVE",
            ), connection=conn)

            # Register device
            ledger.register(ProvisionedDevice(
                device_id=profile.device_id,
                tenant_id=profile.tenant_id,
                space_id=profile.space_id,
                mls_group_id=profile.mls_group_id,
                provisioned_ts=now_ts,
            ), connection=conn)

            # Add device key
            ledger.add_key(DeviceKey(
                device_id=profile.device_id,
                key_version=profile.key_version,
                verify_key=verify_key_b64(profile),
                key_state="ACTIVE",
                registered_ts=now_ts,
                activated_ts=now_ts,
            ), connection=conn)

            conn.commit()
    finally:
        shutdown_pool()

    logger.info("Bootstrap complete. Kernel ready for traffic.")
```

**Dependencies**:

- `k0.automation.migrate.apply_migrations()`: Schema migration engine
- `k0.gate.schema_registry.SchemaRegistry`: Schema registration
- `k0.local.dev_profile.default_profile()`: Default tenant/space/device profile
- `k0.storage.provisioning.ProvisioningLedger`: Device provisioning

**Output**:

```
2025-11-12 10:30:00 | INFO | Bootstrapping local kernel database at /data/k0_kernel.db
2025-11-12 10:30:01 | INFO | Database migrations complete (applied=4, pending=0)
2025-11-12 10:30:02 | INFO | Using profile tenant=tenant_001 space=space_001 device=device_abc
2025-11-12 10:30:03 | INFO | Provisioned device device_abc (tenant=tenant_001 space=space_001) with key version key_v1
2025-11-12 10:30:03 | INFO | Verification key (base64url) YXNkZmFzZGZhc2RmYXNkZg==
2025-11-12 10:30:04 | INFO | Bootstrap complete. Kernel command path is ready for traffic.
```

---

### 2. `traffic_generator.py`

**Purpose**: Traffic generation for staging burn-in with configurable scenarios, endpoint coverage, and outbox cleanup.

#### Classes

```python
@dataclass
class TrafficConfig(BaseModel):
    endpoint: HttpUrl
    rate: int  # Requests per second
    duration_seconds: int
    scenario: str
    command_ratio: float = 0.6
    query_ratio: float = 0.3
    sse_ratio: float = 0.1
    output_dir: Path = Path("artifacts/traffic")
```

- **Purpose**: Configuration for traffic generation
- **Scenarios**: baseline, burst, mixed, sustained, comprehensive

```python
@dataclass
class TrafficMetrics:
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    start_time: datetime
    end_time: datetime
    endpoint_requests: dict[str, int]  # Per-endpoint breakdown
    endpoint_successes: dict[str, int]
    endpoint_failures: dict[str, int]
```

- **Purpose**: Track traffic generation metrics
- **Per-endpoint**: Request counts, successes, failures for each HTTP endpoint

```python
class TrafficGenerator:
    def __init__(self, config: TrafficConfig)
    async def start(self)
```

- **Purpose**: Generate traffic patterns for staging burn-in
- **HTTP client**: `httpx.AsyncClient` with 100 max connections, 30s timeout
- **Scenarios**:
  - `baseline`: Steady rate
  - `burst`: 2x rate with periodic spikes
  - `mixed`: Commands (60%), queries (30%), SSE (10%)
  - `sustained`: Long-running soak test
  - `comprehensive`: Tests all endpoints (command, query, SSE, health, metrics, drivers)

#### Functions

```python
def clear_outbox_backlog(db_path: str = "/data/k0_runtime.sqlite3") -> dict
```

- **Purpose**: Clear outbox and DLQ backlog before starting traffic
- **Tables**: `st_outbox`, `st_dlq`
- **Operations**: DELETE, VACUUM
- **Returns**: `{"outbox_cleared": int, "dlq_cleared": int}`

**Usage**:

```bash
# Clear outbox before traffic
python scripts/traffic_generator.py \
    --endpoint http://localhost:8000 \
    --rate 100 \
    --duration 4h \
    --scenario comprehensive \
    --clear-outbox \
    --db-path /data/k0_runtime.sqlite3
```

**Scenarios**:

**Baseline**: Steady rate

```python
async def _run_baseline(self):
    end_time = self._now() + timedelta(seconds=self.config.duration_seconds)
    interval = 1.0 / self.config.rate  # Seconds between requests

    while self._now() < end_time:
        await self._submit_command()
        await asyncio.sleep(interval)
```

**Burst**: 2x rate with periodic spikes

```python
async def _run_burst(self):
    # Burst period: 2x rate for 1 minute
    await self._generate_traffic(self.config.rate * 2, burst_duration=60)

    # Quiet period: Base rate for 5 minutes
    await self._generate_traffic(self.config.rate, quiet_duration=300)
```

**Mixed**: Commands, queries, SSE subscriptions

```python
async def _run_mixed(self):
    rand = random.random()
    if rand < self.config.command_ratio:
        await self._submit_command()
    elif rand < self.config.command_ratio + self.config.query_ratio:
        await self._submit_query()
    else:
        await self._subscribe_sse()
```

**Comprehensive**: All endpoints

```python
async def _run_comprehensive(self):
    endpoint_cycle = [
        self._submit_command,        # POST /k0/command.submit
        self._submit_query,           # POST /k0/query.recall
        self._subscribe_sse,          # GET /k0/sse.subscribe
        self._test_sse_ack,           # POST /k0/sse.ack
        self._test_health_endpoints,  # GET /healthz, /readyz, /metrics
        self._test_driver_handshake,  # POST /k0/driver.handshake
    ]

    for endpoint_func in cycle(endpoint_cycle):
        await endpoint_func()
```

**Command Generation**:

```python
def _build_command_envelope(self, sequence: int) -> dict[str, Any]:
    # REAL memory store operation (triggers WAL → Outbox → SSE)
    memory_id = f"mem_{sequence}_{uuid.uuid4().hex[:8]}"
    body = {
        "operation": "memory.store",
        "memory_id": memory_id,
        "content": {
            "type": "episodic",
            "title": f"Burn-in Test Memory #{sequence}",
            "tags": ["burn-in", "test"],
            "metadata": {"sequence": sequence},
        },
        "embedding": [random.random() for _ in range(384)],  # Fake vector
    }

    # Calculate envelope signature
    envelope = {...}  # Full envelope with fields
    message = canonical_envelope(envelope)
    signature = encode_base64url(self.signing_key.sign(message).signature)
    envelope["sig"] = signature
    envelope["body"] = body
    return envelope
```

**Metrics Report**:

```json
{
  "scenario": "comprehensive",
  "duration_seconds": 14400.0,
  "total_requests": 1440000,
  "successful_requests": 1438500,
  "failed_requests": 1500,
  "error_rate_percent": 0.104,
  "throughput_req_per_sec": 100.0,
  "latency_ms": {
    "avg": 45.2,
    "min": 12.0,
    "max": 1250.0
  },
  "endpoint_breakdown": {
    "POST /k0/command.submit": {
      "total_requests": 240000,
      "successful": 239800,
      "failed": 200,
      "success_rate_percent": 99.92
    },
    "POST /k0/query.recall": {
      "total_requests": 240000,
      "successful": 239900,
      "failed": 100,
      "success_rate_percent": 99.96
    }
  }
}
```

**CLI**:

```bash
# Baseline: 100 req/s for 4 hours
python scripts/traffic_generator.py \
    --endpoint http://staging.k0.local \
    --rate 100 \
    --duration 4h \
    --scenario baseline

# Burst: 200 req/s spikes, 100 req/s base, 4 hours
python scripts/traffic_generator.py \
    --endpoint http://staging.k0.local \
    --rate 100 \
    --duration 4h \
    --scenario burst

# Mixed: 60% commands, 30% queries, 10% SSE
python scripts/traffic_generator.py \
    --endpoint http://staging.k0.local \
    --rate 100 \
    --duration 4h \
    --scenario mixed \
    --command-ratio 0.6 \
    --query-ratio 0.3 \
    --sse-ratio 0.1

# Comprehensive: Test all endpoints
python scripts/traffic_generator.py \
    --endpoint http://staging.k0.local \
    --rate 50 \
    --duration 2h \
    --scenario comprehensive
```

---

### 3. `validate_recording_rules_performance.py`

**Purpose**: Compare query execution time between raw histogram queries and pre-aggregated recording rules (Prometheus optimization).

#### Functions

```python
def execute_query(query: str, runs: int = 5) -> Dict[str, Any]
```

- **Purpose**: Execute Prometheus query and measure latency
- **Runs**: Average of 5 iterations for accuracy
- **Returns**: `{"query_time_ms": float, "min_ms": float, "max_ms": float, "error": str | None}`

```python
def main() -> None
```

- **Purpose**: Run performance comparison for recording rules
- **Query pairs**: Old (raw histogram) vs. new (recording rule)
- **Expected**: 50-80% latency reduction

**Query Pairs**:

```python
QUERY_PAIRS = [
    (
        "Command Latency p95",
        # OLD: Raw histogram_quantile (slow)
        'histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket{route="/k0/command.submit"}[5m])) by (le))',
        # NEW: Pre-aggregated recording rule (fast)
        "job:k0_command_latency_seconds:p95:5m",
    ),
    (
        "Query Latency p95",
        'histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket{route="/k0/query.execute"}[5m])) by (le))',
        "job:k0_query_latency_seconds:p95:5m",
    ),
    (
        "API Availability",
        '1 - (sum(rate(k0_kernel_http_requests_total{status=~"5.."}[5m])) / sum(rate(k0_kernel_http_requests_total[5m])))',
        "job:k0_api_availability:ratio5m",
    ),
]
```

**Output**:

```
🔬 Recording Rules Performance Validation
================================================================================

📊 Testing: Command Latency p95
   OLD: histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_...
   NEW: job:k0_command_latency_seconds:p95:5m

   Running OLD query (5 iterations)... ✅ Avg: 125.50ms
   Running NEW query (5 iterations)... ✅ Avg: 18.20ms
   📈 Improvement: 85.5% faster (6.90x speedup)

================================================================================
📈 SUMMARY
================================================================================

Queries Tested: 3
Average Improvement: 78.3% faster
Average Speedup: 4.62x

Detailed Results:
Metric                           OLD (ms)     NEW (ms)     Improvement
--------------------------------------------------------------------------------
Command Latency p95                125.50        18.20         85.5%
Query Latency p95                  132.40        22.10         83.3%
API Availability                    98.70        35.50         64.0%

✅ SUCCESS: Recording rules achieved >50% query latency reduction!
```

**CLI**:

```bash
# Default Prometheus URL (localhost:9090)
python scripts/validate_recording_rules_performance.py

# Custom Prometheus URL
PROMETHEUS_URL=http://prometheus.staging:9090 python scripts/validate_recording_rules_performance.py
```

---

### 4. PowerShell Deployment Scripts

**Purpose**: Deployment automation for staging and Azure environments.

#### `deploy_staging.ps1`

- **Purpose**: Deploy K0 kernel to staging environment
- **Actions**: Docker build, push to registry, kubectl apply
- **Usage**: `./scripts/deploy_staging.ps1`

#### `deploy_azure_burnin.ps1`

- **Purpose**: Deploy Azure burn-in stack with traffic generation
- **Actions**: AKS provisioning, kernel deployment, traffic generator job
- **Usage**: `./scripts/deploy_azure_burnin.ps1 -ResourceGroup k0-burnin`

#### `run_traffic_external.ps1`

- **Purpose**: Run traffic generator against external endpoint
- **Actions**: Spawn traffic generator process, monitor metrics
- **Usage**: `./scripts/run_traffic_external.ps1 -Endpoint http://staging.k0.local -Rate 100`

#### `audit_dashboards.ps1`

- **Purpose**: Validate Grafana dashboards for completeness
- **Actions**: Check panel queries, data sources, alerting rules
- **Usage**: `./scripts/audit_dashboards.ps1`

---

## Usage Examples

### Local Development Setup

```bash
# 1. Bootstrap local kernel
python scripts/bootstrap_local_kernel.py --verbose

# 2. Start kernel
docker-compose up -d

# 3. Run baseline traffic (100 req/s for 10 minutes)
python scripts/traffic_generator.py \
    --endpoint http://localhost:8000 \
    --rate 100 \
    --duration 10m \
    --scenario baseline
```

### Staging Burn-in

```bash
# 1. Deploy to staging
./scripts/deploy_staging.ps1

# 2. Clear outbox backlog
python scripts/traffic_generator.py \
    --endpoint http://staging.k0.local \
    --rate 100 \
    --duration 4h \
    --scenario comprehensive \
    --clear-outbox

# 3. Validate recording rules
python scripts/validate_recording_rules_performance.py
```

### CI/CD Pipeline

```yaml
# .github/workflows/burn-in.yml
- name: Bootstrap kernel
  run: python scripts/bootstrap_local_kernel.py

- name: Run burn-in traffic
  run: |
    python scripts/traffic_generator.py \
      --endpoint http://localhost:8000 \
      --rate 50 \
      --duration 30m \
      --scenario comprehensive \
      --output-dir artifacts/traffic

- name: Validate metrics
  run: python scripts/validate_recording_rules_performance.py
```

---

## Performance & Observability

### Traffic Generator Metrics

- **Total requests**: Count of all HTTP requests
- **Success rate**: `(successful_requests / total_requests) * 100`
- **Error rate**: `(failed_requests / total_requests) * 100`
- **Throughput**: `total_requests / duration_seconds`
- **Latency**: avg, min, max across all requests
- **Per-endpoint breakdown**: Requests, successes, failures for each endpoint

### Recording Rules Validation

- **Query latency**: Average execution time for raw vs. recording rule queries
- **Improvement %**: `((old_latency - new_latency) / old_latency) * 100`
- **Speedup factor**: `old_latency / new_latency`
- **Success criteria**: >50% latency reduction

---

## Related Modules

- **`k0.automation.migrate`**: Schema migration engine
- **`k0.local.dev_profile`**: Default profile for local development
- **`k0.storage.provisioning`**: Device provisioning ledger
- **`k0.security.crypto`**: Canonical envelope signing
- **`k0.ports.*`**: HTTP endpoints tested by traffic generator

---

## Related ADRs

- **ADR-0110**: Local Development Environment
- **ADR-0111**: Traffic Generation for Burn-in Testing
- **ADR-0112**: Performance Validation and Recording Rules

---

## Key Design Decisions

1. **Bootstrap idempotency**: Re-running bootstrap is safe (upserts schema/device)
2. **REAL memory operations**: Traffic generator creates actual memories (triggers full pipeline)
3. **Outbox cleanup**: Clear backlog before burn-in to isolate test traffic
4. **Comprehensive scenario**: Tests all implemented endpoints for coverage
5. **Per-endpoint metrics**: Track success/failure rates for each HTTP route
6. **Recording rules validation**: Automated comparison for Prometheus optimization
7. **Async traffic generation**: Use `asyncio` for high concurrency (100 req/s+)
8. **Report artifacts**: JSON reports saved to `artifacts/traffic/` for CI/CD
