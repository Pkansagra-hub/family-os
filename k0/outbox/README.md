# K0 Outbox Pattern Implementation

**Purpose**: Reliable, at-least-once delivery of WAL events to external driver systems via outbox pattern with retry scheduling, fingerprinting, and dead-letter queue fallback.

**Layer**: Infrastructure (Layer 5)
**Category**: Post-commit coordination
**Related ADRs**: ADR-0021 (Outbox Pattern), ADR-0042 (Driver Abstraction)

---

## Overview

The outbox module implements the **Transactional Outbox Pattern** for reliable event delivery after WAL commit. It guarantees at-least-once delivery semantics by:

1. **Atomic commit**: Events written to outbox table in same transaction as WAL
2. **Worker polling**: Background workers dequeue and apply entries to external drivers
3. **Retry scheduling**: Exponential backoff (2^n seconds) for transient failures
4. **Fingerprinting**: BLAKE3-based deduplication to ensure idempotent application
5. **Dead-letter queue**: Quarantine entries exceeding max retry attempts for manual intervention

**Flow**: WAL commit → Outbox insert → Worker dequeue → Driver apply → Mark applied or retry/quarantine

---

## Repository Files & Functions

### 1. `fingerprint.py`
**Purpose**: Deterministic BLAKE3 fingerprint generation for outbox entries to ensure idempotent replay.

#### Functions
```python
def compute_fingerprint(driver: str, op_kind: str, payload: bytes) -> str
```
- **Inputs**: Driver alias, operation kind, raw payload bytes
- **Algorithm**: BLAKE3 digest of `driver\x00op_kind\x00payload`
- **Output**: Hex-encoded fingerprint string
- **Guarantees**: Same inputs always produce same fingerprint (enables deduplication)
- **Validation**: Rejects empty driver or op_kind

**Usage**:
```python
from k0.outbox import compute_fingerprint

fp = compute_fingerprint("neo4j_indexer", "INSERT_ENVELOPE", envelope_bytes)
# fp: "a7f3c2e8b1d9f4a6..."
```

---

### 2. `scheduler.py`
**Purpose**: Exponential backoff retry scheduling with dead-letter quarantine logic.

#### Classes
```python
@dataclass(frozen=True)
class RetryDecision:
    action: str                     # "retry" or "quarantine"
    retries: int                    # Updated retry count
    requeue_seq: int                # DEPRECATED - legacy backoff steps
    next_attempt_ts: str | None     # ISO8601 timestamp for next retry
    backoff_exp: int                # Exponent for 2^n backoff (capped at 6)
    status: str                     # PENDING/PROCESSING/FAILED/DEAD
```

```python
class RetryScheduler:
    def __init__(self, *, max_attempts: int = 5, backoff_steps: Sequence[int] | None = None)
    def decide(self, entry: OutboxEntry) -> RetryDecision
```
- **Backoff algorithm**: Exponential `2^backoff_exp` seconds (1s, 2s, 4s, 8s, 16s, 32s, 64s max)
- **Max attempts**: Configurable, default 5
- **Quarantine logic**: If `next_retry >= max_attempts`, return `action="quarantine"` with `status="DEAD"`
- **Timestamp tracking**: Calculates next attempt time as `now + 2^backoff_exp` seconds
- **Backward compatibility**: Preserves legacy `requeue_seq` field for existing systems

**Usage**:
```python
scheduler = RetryScheduler(max_attempts=10)
decision = scheduler.decide(failed_entry)

if decision.action == "retry":
    # Requeue with next_attempt_ts and backoff_exp
    outbox_store.record_failure(entry, decision.retries, decision.next_attempt_ts)
else:
    # Quarantine to DLQ
    dead_letter_queue.record(entry, reason="max_retries_exceeded")
```

---

### 3. `worker.py`
**Purpose**: Core outbox worker that drains driver queues, applies entries, and handles retry/DLQ fallback.

#### Protocols & Loaders
```python
class MetricsEmitter(Protocol):
    def __call__(self, metric_name: str, value: float, **labels: str) -> None

class OutboxDriver(Protocol):
    def apply(self, entry: OutboxEntry) -> None
```

```python
def load_driver_from_alias_map(alias_map: AliasMap) -> Callable[[str], OutboxDriver]
```
- **Purpose**: Factory that resolves driver aliases to Python modules
- **Resolution**: Reads `k0/drivers/alias_map.yaml`, imports `k0.drivers.<driver_key>`
- **Discovery**: Looks for `build_driver()`, `Driver` class, or `driver` instance in module
- **Validation**: Ensures driver exposes `apply(entry: OutboxEntry)` method
- **Error**: Raises `RuntimeError` if driver module doesn't expose valid factory

**Example**:
```yaml
# alias_map.yaml
aliases:
  neo4j_indexer: neo4j_driver
  faiss_indexer: faiss
```
```python
loader = load_driver_from_alias_map(alias_map)
driver = loader("neo4j_indexer")  # Imports k0.drivers.neo4j_driver, calls build_driver()
```

#### Main Worker Class
```python
class OutboxWorker:
    def __init__(
        self,
        *,
        outbox_store: OutboxStore,
        dead_letter_queue: DeadLetterQueue,
        retry_scheduler: RetryScheduler,
        driver_loader: Callable[[str], OutboxDriver],
        metrics_emitter: MetricsEmitter | None = None,
        clock: Callable[[], datetime] | None = None,
        batch_size: int = 128,
        max_retry_attempts: int = 10,
    )

    def process_driver(self, alias: str, *, limit: int | None = None) -> None
    def register_driver(self, alias: str, driver: OutboxDriver) -> None
    def unregister_driver(self, alias: str) -> None
```

**Key Methods**:
1. **`process_driver(alias, limit)`**: Main processing loop
   - Dequeues `batch_size` entries for driver alias using `outbox_store.dequeue_ready_batch()`
   - Applies entries via `driver.apply(entry)`
   - On success: Marks applied with `outbox_store.mark_applied(entry.id)`
   - On failure: Calls `_handle_failure()` for retry or quarantine

2. **`_handle_failure(alias, entry, error)`**: Error handling with retry/DLQ logic
   - Truncates error message to 512 chars
   - Calls `retry_scheduler.decide(entry)` to get retry decision
   - **Retry path**: Records failure with `outbox_store.record_failure(entry, retries, next_attempt_ts, backoff_exp)`
   - **Quarantine path**: Writes to DLQ with `dead_letter_queue.record(DeadLetter)`
   - **CRITICAL**: Does NOT `mark_applied()` on quarantine (Gap 37 fix) - entry remains until DLQ requeue succeeds
   - **Metrics**: Emits `outbox_retry_backoff_exponent`, `outbox_backoff_sleep_seconds`, `dlq_entries_abandoned_total` (Gap 38/46)

3. **`register_driver(alias, driver)`**: Inject or replace driver instance (used by handshake pool)

4. **`unregister_driver(alias)`**: Remove cached driver (used when handshake expires)

**Metrics Emitted**:
- `outbox_apply_total{outcome="success|retry|quarantine", driver="<alias>"}`
- `outbox_retry_backoff_exponent{driver="<alias>"}` (Gap 46)
- `outbox_backoff_sleep_seconds{driver="<alias>"}` (Gap 46)
- `dlq_entries_abandoned_total{driver="<alias>"}` (Gap 38)

**Usage**:
```python
worker = OutboxWorker(
    outbox_store=store,
    dead_letter_queue=dlq,
    retry_scheduler=RetryScheduler(max_attempts=5),
    driver_loader=load_driver_from_alias_map(alias_map),
    batch_size=128,
)

# Process neo4j_indexer queue
worker.process_driver("neo4j_indexer", limit=256)
```

---

### 4. `pool.py`
**Purpose**: Driver worker pool with HTTP/gRPC handshake coordination for dynamic driver registration.

#### Data Classes
```python
@dataclass(slots=True)
class DriverSession:
    session_id: str          # UUID4 hex
    alias: str               # Driver alias (e.g., "neo4j_indexer")
    driver_module: str       # Resolved module (e.g., "neo4j_driver")
    transport: str           # "http" or "grpc"
    endpoint: str            # URL or gRPC target
    capabilities: tuple[str, ...]  # Optional capabilities
    metadata: Mapping[str, Any]    # Extra session metadata
    issued_at: datetime
    expires_at: datetime     # Session TTL
```

```python
@dataclass(slots=True)
class DriverHandshakeError(Exception):
    code: str                # ERROR_CODE (e.g., "DRIVER_ALIAS_NOT_FOUND")
    status_code: int         # HTTP status code
    reason: str              # Human-readable reason
    hint: str | None         # Optional troubleshooting hint
```

#### HTTP Driver Adapter
```python
class HTTPDriverAdapter:
    def __init__(self, *, endpoint: str, session_id: str, timeout: float = 5.0)
    def apply(self, entry: OutboxEntry) -> None
```
- **Purpose**: Forwards `OutboxEntry` to remote HTTP driver endpoint
- **Serialization**: Converts entry to JSON with base64-encoded payload
- **Headers**: `Content-Type: application/json`, `X-K0-Driver-Session: <session_id>`
- **Timeout**: 5s default
- **Error handling**: Raises `RuntimeError` on HTTP >=300 or network errors

**Serialization Format**:
```json
{
  "id": 12345,
  "wal_pos": "0000001A-00000042",
  "tenant_id": "tenant_abc",
  "space_id": "space_xyz",
  "driver": "neo4j_indexer",
  "op_kind": "INSERT_ENVELOPE",
  "payload_base64": "eyJmb28iOiJiYXIifQ==",
  "fingerprint": "a7f3c2e8...",
  "requeue_seq": 0,
  "retries": 0,
  "last_error": null
}
```

#### Pool Manager
```python
class DriverWorkerPool:
    def __init__(
        self,
        *,
        alias_map: AliasMap,
        outbox_store: OutboxStore,
        dead_letter_queue: DeadLetterQueue,
        retry_scheduler_factory: Callable[[], RetryScheduler],
        metrics_emitter: MetricsEmitter | None = None,
        batch_size: int = 128,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: int = 300,  # 5 minutes
        max_retry_attempts: int = 10,
    )

    def register_handshake(
        self,
        *,
        alias: str,
        transport: str,
        endpoint: str,
        capabilities: Sequence[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        lease_seconds: int | None = None,
    ) -> DriverSession

    def process_driver(self, alias: str, *, limit: int | None = None) -> None
    def get_session(self, session_id: str) -> DriverSession | None
    def active_sessions(self, alias: str) -> list[DriverSession]
```

**Key Methods**:
1. **`register_handshake()`**: Driver registration with validation
   - Validates alias exists in `alias_map`
   - Validates transport is "http" or "grpc"
   - Validates endpoint URL format (HTTP: `http(s)://...`, gRPC: `dns:///host:port`)
   - Deduplicates capabilities
   - Generates UUID session ID with configurable TTL (default 5 minutes)
   - For HTTP: Creates `HTTPDriverAdapter` and injects into worker via `register_driver()`
   - Emits `k0_driver_handshakes_total{outcome="accepted", alias="...", transport="..."}`
   - **Error cases**: Raises `DriverHandshakeError` with specific codes:
     - `DRIVER_HANDSHAKE_INVALID`: Bad transport, endpoint, or capabilities
     - `DRIVER_ALIAS_NOT_FOUND`: Alias not in `alias_map.yaml`

2. **`process_driver(alias, limit)`**: Delegates to `OutboxWorker.process_driver()`

3. **`get_session(session_id)`**: Retrieve session by ID (cleans up expired sessions first)

4. **`active_sessions(alias)`**: List all active sessions for driver alias

5. **`_cleanup_expired_sessions()`**: Remove expired sessions and unregister drivers

**Usage**:
```python
pool = DriverWorkerPool(
    alias_map=alias_map,
    outbox_store=store,
    dead_letter_queue=dlq,
    retry_scheduler_factory=lambda: RetryScheduler(max_attempts=5),
    lease_seconds=300,
)

# Register HTTP driver
session = pool.register_handshake(
    alias="neo4j_indexer",
    transport="http",
    endpoint="https://indexer.local/apply",
    capabilities=["idempotent", "batch"],
    lease_seconds=600,
)
# session.session_id: "a7f3c2e8b1d9f4a6..."

# Process driver queue
pool.process_driver("neo4j_indexer", limit=256)

# Check active sessions
sessions = pool.active_sessions("neo4j_indexer")
```

---

## Connections & Integration Points

### Upstream Dependencies
1. **`k0.storage.outbox.OutboxStore`**:
   - `dequeue_ready_batch(alias, limit)`: Fetch entries ready for processing (respects `next_attempt_ts`)
   - `mark_applied(id)`: Delete successfully applied entry
   - `record_failure(entry, retries, requeue_seq, last_error, next_attempt_ts, backoff_exp, status)`: Update retry metadata

2. **`k0.storage.dlq.DeadLetterQueue`**:
   - `record(DeadLetter)`: Insert quarantined entry with reason and retry count

3. **`k0.drivers.alias_map.AliasMap`**:
   - `resolve(alias)`: Map alias to driver module key

4. **`k0.drivers.*`**: Driver implementations (e.g., `neo4j_driver.py`, `sqlite.py`)
   - Must expose `apply(entry: OutboxEntry)` method

### Downstream Consumers
1. **`k0.bus.BusDispatcher`**:
   - Calls `pool.process_driver(alias)` after WAL commit to drain outbox queues
   - Scheduled via `k0.qos.Scheduler` for background processing

2. **`k0.kernel.app`**: FastAPI routes for driver handshake
   - `POST /api/v1/outbox/register-driver`: Accepts driver handshake requests
   - Calls `pool.register_handshake()` to create sessions

3. **`k0.workers.outbox_worker`**: Background worker process
   - Polls outbox for each driver alias every N seconds
   - Calls `pool.process_driver(alias)` in loop

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. WAL Commit + Outbox Insert                                    │
│    UnitOfWork.commit() → OutboxStore.insert(driver, op_kind,    │
│    payload, fingerprint)                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Worker Dequeue                                                │
│    OutboxWorker.process_driver(alias) →                          │
│    OutboxStore.dequeue_ready_batch(alias, limit) →              │
│    [OutboxEntry where next_attempt_ts <= now()]                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Driver Apply                                                  │
│    driver.apply(entry) → External system (Neo4j, FAISS, etc.)   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                 ┌───────┴───────┐
                 │               │
           ✓ Success        ✗ Failure
                 │               │
                 ▼               ▼
┌────────────────────────┐  ┌────────────────────────────────────┐
│ 4a. Mark Applied       │  │ 4b. Retry or Quarantine            │
│ OutboxStore.           │  │ RetryScheduler.decide(entry) →     │
│ mark_applied(id)       │  │ if action="retry":                 │
│ → Entry deleted        │  │   OutboxStore.record_failure()     │
│                        │  │ else:                              │
│ Emit: outbox_apply_    │  │   DeadLetterQueue.record()         │
│ total{outcome=success} │  │   Emit: dlq_entries_total         │
└────────────────────────┘  └────────────────────────────────────┘
```

### Handshake Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Driver Registration Request                                   │
│    POST /api/v1/outbox/register-driver                           │
│    {alias, transport, endpoint, capabilities, lease_seconds}     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Handshake Validation                                          │
│    DriverWorkerPool.register_handshake() →                       │
│    - Validate alias in alias_map                                 │
│    - Validate transport (http/grpc)                              │
│    - Validate endpoint URL                                       │
│    - Generate session_id (UUID4)                                 │
│    - Set expires_at = now + lease_seconds                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Driver Override                                               │
│    If transport="http": Create HTTPDriverAdapter →              │
│    worker.register_driver(alias, adapter)                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Session Storage                                               │
│    sessions[session_id] = DriverSession                          │
│    alias_sessions[alias] = session_id                            │
│    Emit: k0_driver_handshakes_total{outcome=accepted}            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Worker Uses HTTP Adapter                                      │
│    OutboxWorker.process_driver(alias) →                          │
│    HTTPDriverAdapter.apply(entry) →                              │
│    POST {endpoint} with X-K0-Driver-Session header               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing

### Unit Tests
```python
# tests/k0/outbox/test_fingerprint.py
def test_compute_fingerprint_deterministic():
    fp1 = compute_fingerprint("neo4j", "INSERT", b"data")
    fp2 = compute_fingerprint("neo4j", "INSERT", b"data")
    assert fp1 == fp2

# tests/k0/outbox/test_scheduler.py
def test_retry_scheduler_exponential_backoff():
    scheduler = RetryScheduler(max_attempts=5)
    entry = OutboxEntry(retries=0, ...)
    decision = scheduler.decide(entry)
    assert decision.action == "retry"
    assert decision.backoff_exp == 1  # 2^1 = 2 seconds

# tests/k0/outbox/test_worker.py
def test_worker_applies_entries_successfully(mocker):
    driver = mocker.Mock(spec=OutboxDriver)
    worker.register_driver("neo4j", driver)
    worker.process_driver("neo4j")
    driver.apply.assert_called_once()

# tests/k0/outbox/test_pool.py
def test_register_handshake_creates_session():
    session = pool.register_handshake(
        alias="neo4j_indexer",
        transport="http",
        endpoint="https://indexer.local/apply",
    )
    assert session.session_id is not None
    assert session.alias == "neo4j_indexer"
```

### Integration Tests
```python
# tests/integration/test_outbox_e2e.py
def test_outbox_retry_with_backoff(kernel_client):
    # Submit envelope
    response = kernel_client.post("/api/v1/submit", json=envelope)
    assert response.status_code == 202

    # Simulate driver failure
    with patch("k0.drivers.neo4j_driver.apply", side_effect=RuntimeError("Connection failed")):
        worker.process_driver("neo4j_indexer")

    # Verify retry with exponential backoff
    entry = outbox_store.dequeue_ready_batch("neo4j_indexer")[0]
    assert entry.retries == 1
    assert entry.backoff_exp == 1
    assert entry.next_attempt_ts > datetime.now(timezone.utc)
```

---

## Performance & Observability

### Metrics
- `outbox_apply_total{outcome, driver}` (counter): Apply outcomes (success/retry/quarantine)
- `outbox_retry_backoff_exponent{driver}` (gauge): Current backoff exponent (Gap 46)
- `outbox_backoff_sleep_seconds{driver}` (gauge): Calculated sleep duration (Gap 46)
- `dlq_entries_abandoned_total{driver}` (counter): Entries marked ABANDONED after max retries (Gap 38)
- `k0_driver_handshakes_total{alias, transport, outcome}` (counter): Handshake outcomes

### Traces
- Span: `outbox.worker.process_driver` (driver alias, batch size)
- Span: `outbox.driver.apply` (entry ID, fingerprint, retries)
- Span: `outbox.scheduler.decide` (retries, action, backoff_exp)

### Logging
```json
{
  "event": "outbox_entry_applied",
  "entry_id": 12345,
  "driver": "neo4j_indexer",
  "fingerprint": "a7f3c2e8...",
  "retries": 0,
  "cognitive_trace_id": "trace_abc"
}
```

---

## Related Modules
- **`k0.storage.outbox`**: Outbox table schema and store operations
- **`k0.storage.dlq`**: Dead-letter queue for failed entries
- **`k0.drivers`**: Driver implementations (SQLite, Neo4j, FAISS, etc.)
- **`k0.qos`**: Scheduler for background outbox processing
- **`k0.bus`**: BusDispatcher that triggers outbox workers
- **`k0.uow`**: UnitOfWork that commits to outbox atomically

---

## Related ADRs
- **ADR-0021**: Outbox Pattern for Reliable Event Delivery
- **ADR-0042**: Driver Abstraction and SPI
- **ADR-0033**: Exponential Backoff Retry Strategy
- **ADR-0045**: Dead-Letter Queue Design

---

## Key Design Decisions

1. **Fingerprinting**: BLAKE3 chosen for speed and collision resistance (faster than SHA-256, same security level)
2. **Exponential backoff**: 2^n capped at 64s to balance retry latency with system load
3. **No premature deletion**: Gap 37 fix - entries remain in outbox until DLQ requeue succeeds
4. **Handshake TTL**: Default 5 minutes to prevent stale driver registrations
5. **Batch processing**: 128 entries default for optimal throughput/latency tradeoff
