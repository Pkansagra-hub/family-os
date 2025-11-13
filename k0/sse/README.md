# K0 Server-Sent Events (SSE) Module

**Purpose**: SSE multiplexing server for real-time event streaming with backpressure control, topic-based ACL, and cursor-based pagination.

**Layer**: Communication & Streaming
**Category**: Server-Sent Events, real-time notifications, backpressure management
**Related ADRs**: ADR-0130 (SSE Architecture), ADR-0131 (Backpressure Thresholds), ADR-0132 (Topic ACL)

---

## Overview

The SSE module provides **real-time event streaming** with:

1. **Topic-based subscriptions**: Subscribe to multiple topics with role-based ACL filtering
2. **Cursor-based pagination**: Resume subscriptions from last acknowledged position
3. **Backpressure management**: Configurable thresholds (WARNING, THROTTLE, SHED) based on lag and pending events
4. **Acknowledgment tracking**: Per-subscriber offset tracking for reliable delivery
5. **WAL-backed streaming**: Events sourced from Write-Ahead Log (st_wal)

**Usage Context**: Ports (sse.subscribe handler), Workers (SSE server loop), CLI (sse-server command)

---

## Repository Files & Functions

### 1. `server.py`

**Purpose**: SSE multiplexing implementation with backpressure control and topic ACL.

#### Classes

```python
@dataclass(slots=True)
class CursorState:
    last_position: int
    last_ts: datetime
    subscriber_id: str | None = None
    topic: str | None = None
    space_id: str | None = None
    tenant_id: str | None = None
```

- **Purpose**: Represents decoded cursor parameters for subscription resumption
- **Fields**:
  - `last_position`: WAL position to resume from
  - `last_ts`: Timestamp of last acknowledged event
  - `subscriber_id`: Subscriber identifier (for cursor validation)
  - `topic`: Optional topic filter in cursor
  - `space_id`: Optional space scope in cursor
  - `tenant_id`: Optional tenant scope in cursor

---

```python
@dataclass(slots=True)
class BackpressureTopicMetrics:
    topic: str
    pending_events: int
    lag_ms: int
    cursor: str | None
```

- **Purpose**: Per-topic backpressure metrics
- **Fields**:
  - `pending_events`: Number of unacknowledged events for topic
  - `lag_ms`: Time difference between latest commit and last ack (milliseconds)
  - `cursor`: Optional cursor token for resuming from last ack

---

```python
@dataclass(slots=True)
class BackpressureMetrics:
    level: str  # "normal", "warning", "throttle", "shed"
    lag_ms: int
    pending_events: int
    topics: list[BackpressureTopicMetrics]
    ack_offsets: Mapping[str, int]
```

- **Purpose**: Aggregate backpressure metrics across all subscribed topics
- **Fields**:
  - `level`: Backpressure level (normal/warning/throttle/shed)
  - `lag_ms`: Maximum lag across all topics
  - `pending_events`: Total pending events across all topics
  - `topics`: Per-topic metrics breakdown
  - `ack_offsets`: Map of topic → last acknowledged offset

**Backpressure Levels** (Gap 25):

| Level | Condition | Action |
|-------|-----------|--------|
| **normal** | lag < 2s AND pending < 5K | No throttling |
| **warning** | lag ≥ 2s OR pending ≥ 5K | Emit warning logs |
| **throttle** | lag ≥ 5s OR pending ≥ 20K | Slow down event delivery |
| **shed** | lag ≥ 15s OR pending ≥ 50K | Drop connection |

---

```python
@dataclass(slots=True)
class SSEServer:
    wal: WriteAheadLog
    offset_store: OffsetStore
    observability: ObservabilityEmitter
    acl_path: Path
    qos: QoSContext
    database_connection: sqlite3.Connection | None = None
    max_batch: int = 128

    # Gap 25: Configurable backpressure thresholds
    max_pending_events: int = 1_000
    disconnect_threshold: int = 10_000
    WARNING_LAG_MS: int = 2_000
    WARNING_PENDING: int = 5_000
    THROTTLE_LAG_MS: int = 5_000
    THROTTLE_PENDING: int = 20_000
    SHED_LAG_MS: int = 15_000
    SHED_PENDING: int = 50_000
```

- **Purpose**: Manage SSE subscriptions, acknowledgments, and backpressure
- **Dependencies**:
  - `wal`: WriteAheadLog for reading events
  - `offset_store`: OffsetStore for tracking subscriber positions
  - `observability`: ObservabilityEmitter for metrics/events
  - `acl_path`: Path to topic ACL YAML file
  - `qos`: QoSContext for budget enforcement
- **Thresholds**: Configurable backpressure levels (Gap 25)

#### Methods

```python
def subscribe(
    self,
    *,
    tenant_id: str,
    space_id: str,
    subscriber_id: str,
    topics: Sequence[str],
    roles: Sequence[str],
    cursor_token: str | None,
    fanout_limit: int | None = None,
) -> tuple[list[WalEntry], list[str]]
```

- **Purpose**: Subscribe to SSE topics with ACL filtering and cursor resumption
- **ACL Check**: Load `acl.yaml` and filter topics by role permissions
- **Cursor Validation**: Verify cursor scope matches tenant/space/subscriber
- **WAL Read**: Fetch events from `last_position` with fanout limit
- **Filtering**: Only return events matching tenant/space/topic
- **Returns**: `(filtered_entries, permitted_topics)`

**Algorithm**:

```python
def subscribe(...) -> tuple[list[WalEntry], list[str]]:
    # 1. Validate fanout limit
    fanout_limit = fanout_limit or self.max_batch
    if fanout_limit <= 0:
        raise HTTPException(400, "INVALID_FANOUT_LIMIT")

    # 2. Load ACL and filter topics
    permitted_topics = self._load_acl(topics, roles)
    if not permitted_topics:
        raise HTTPException(403, "TOPIC_ACCESS_DENIED")

    # 3. Decode cursor (if provided)
    last_position = 0
    if cursor_token:
        cursor_state = self._decode_cursor(cursor_token)
        # Validate cursor scope
        if cursor_state.subscriber_id and cursor_state.subscriber_id != subscriber_id:
            raise HTTPException(400, "CURSOR_SUBSCRIBER_MISMATCH")
        if cursor_state.space_id and cursor_state.space_id != space_id:
            raise HTTPException(400, "CURSOR_SCOPE_MISMATCH")
        last_position = cursor_state.last_position

    # 4. Read WAL entries
    rows = self.wal.read_from(
        last_position,
        min(fanout_limit, self.max_batch),
        connection=self.database_connection,
    )

    # 5. Filter by topic ACL and scope
    filtered_rows: list[WalEntry] = []
    for row in rows:
        if not self._topic_allowed(row.topic, permitted_topics):
            continue
        if row.space_id != space_id or row.tenant_id != tenant_id:
            continue
        filtered_rows.append(row)

    return filtered_rows, permitted_topics
```

**Example**:

```python
server = SSEServer(wal, offset_store, observability, acl_path, qos)

# Subscribe to memory and events topics
entries, permitted = server.subscribe(
    tenant_id="tenant_001",
    space_id="space_001",
    subscriber_id="sub_abc123",
    topics=["memory.*", "events.*"],
    roles=["household_device"],
    cursor_token=None,  # Start from beginning
    fanout_limit=128,
)

# Stream entries to client
for entry in entries:
    yield f"data: {json.dumps(entry.envelope_json)}\n\n"
```

---

```python
def evaluate_backpressure(
    self,
    *,
    subscriber_id: str,
    tenant_id: str,
    space_id: str,
    topics: Sequence[str],
) -> BackpressureMetrics
```

- **Purpose**: Evaluate backpressure levels based on lag and pending events (Gap 25)
- **Per-topic Metrics**: Calculate lag_ms and pending_events for each topic
- **Aggregate Metrics**: Compute max_lag_ms and total_pending across all topics
- **Level Determination**:
  - `shed`: lag > 15s OR pending > 50K
  - `throttle`: lag > 5s OR pending > 20K
  - `warning`: lag > 2s OR pending > 5K
  - `normal`: Otherwise
- **Returns**: `BackpressureMetrics` with level, lag, pending, per-topic metrics

**Algorithm**:

```python
def evaluate_backpressure(...) -> BackpressureMetrics:
    total_pending = 0
    max_lag_ms = 0
    topic_metrics: list[BackpressureTopicMetrics] = []
    ack_offsets: dict[str, int] = {}
    now = datetime.now(tz=timezone.utc)

    for topic in topics:
        # 1. Fetch subscriber offset
        offset_record = self.offset_store.fetch(
            subscriber_id, topic, space_id, tenant_id
        )
        offset_value = int(offset_record.offset) if offset_record else 0
        ack_offsets[topic] = offset_value
        ack_ts = self._parse_iso8601(offset_record.updated_ts) if offset_record else None

        # 2. Get WAL backlog stats
        stats = self.wal.backlog_stats(
            tenant_id=tenant_id,
            space_id=space_id,
            topic=topic,
            offset=offset_value,
        )

        pending = stats.pending_events
        total_pending += pending

        # 3. Calculate lag_ms
        if stats.latest_commit_ts:
            latest_commit_ts = self._parse_iso8601(stats.latest_commit_ts)
            reference = ack_ts or latest_commit_ts
            lag_delta = latest_commit_ts - reference
            lag_ms = max(int(lag_delta.total_seconds() * 1000), 0)
        else:
            lag_ms = 0

        max_lag_ms = max(max_lag_ms, lag_ms)

        # 4. Build cursor token
        cursor_token = self.build_cursor(...) if offset_value > 0 else None

        topic_metrics.append(BackpressureTopicMetrics(
            topic=topic, pending_events=pending, lag_ms=lag_ms, cursor=cursor_token
        ))

    # 5. Determine backpressure level
    level = "normal"
    if max_lag_ms > self.SHED_LAG_MS or total_pending > self.SHED_PENDING:
        level = "shed"
    elif max_lag_ms > self.THROTTLE_LAG_MS or total_pending > self.THROTTLE_PENDING:
        level = "throttle"
    elif max_lag_ms > self.WARNING_LAG_MS or total_pending > self.WARNING_PENDING:
        level = "warning"

    return BackpressureMetrics(
        level=level,
        lag_ms=max_lag_ms,
        pending_events=total_pending,
        topics=topic_metrics,
        ack_offsets=ack_offsets,
    )
```

**Example**:

```python
# Evaluate backpressure for subscriber
metrics = server.evaluate_backpressure(
    subscriber_id="sub_abc123",
    tenant_id="tenant_001",
    space_id="space_001",
    topics=["memory.*", "events.*"],
)

if metrics.level == "shed":
    logger.warning(f"Shedding connection for sub_abc123 (lag={metrics.lag_ms}ms)")
    raise HTTPException(429, "TOO_MANY_PENDING_EVENTS")
elif metrics.level == "throttle":
    logger.info(f"Throttling sub_abc123 (lag={metrics.lag_ms}ms)")
    await asyncio.sleep(0.5)  # Slow down delivery
```

---

```python
def acknowledge(
    self,
    *,
    subscriber_id: str,
    tenant_id: str,
    space_id: str,
    topic: str,
    offset: int,
    ack_ts: datetime | None = None,
) -> None
```

- **Purpose**: Acknowledge processed events and update subscriber offset
- **Validation**: Reject negative offsets (raises HTTPException 400)
- **Storage**: Upsert offset record in `st_offsets` table
- **Timestamp**: Use provided `ack_ts` or current UTC time

**Algorithm**:

```python
def acknowledge(...) -> None:
    # 1. Validate offset
    if offset < 0:
        raise HTTPException(400, "NEGATIVE_OFFSET")

    # 2. Default timestamp
    ack_ts = ack_ts or datetime.now(tz=timezone.utc)

    # 3. Create offset record
    record = Offset(
        subscriber_id=subscriber_id,
        topic=topic,
        space_id=space_id,
        tenant_id=tenant_id,
        offset=offset,
        updated_ts=ack_ts.isoformat(),
    )

    # 4. Upsert offset
    self.offset_store.upsert(record, connection=self.database_connection)
```

**Example**:

```python
# Acknowledge events up to position 1500
server.acknowledge(
    subscriber_id="sub_abc123",
    tenant_id="tenant_001",
    space_id="space_001",
    topic="memory.timeline",
    offset=1500,
)
```

---

```python
def build_cursor(
    self,
    *,
    subscriber_id: str,
    tenant_id: str,
    space_id: str,
    topic: str,
    offset: int,
    commit_ts: str,
) -> str
```

- **Purpose**: Build cursor token for subscription resumption
- **Format**: JSON with nonce for uniqueness
- **Fields**: subscriber_id, tenant_id, space_id, topic, offset, ts, nonce
- **Returns**: JSON string (not base64 encoded)

**Algorithm**:

```python
def build_cursor(...) -> str:
    cursor_payload: dict[str, str | int] = {
        "subscriber_id": subscriber_id,
        "tenant_id": tenant_id,
        "space_id": space_id,
        "topic": topic,
        "offset": int(offset),
        "ts": commit_ts,
        "nonce": secrets.token_hex(8),  # 16-char hex string
    }
    return json.dumps(cursor_payload)
```

**Example Cursor**:

```json
{
  "subscriber_id": "sub_abc123",
  "tenant_id": "tenant_001",
  "space_id": "space_001",
  "topic": "memory.timeline",
  "offset": 1500,
  "ts": "2025-11-12T10:00:00Z",
  "nonce": "a1b2c3d4e5f6g7h8"
}
```

---

#### Private Methods

```python
def _load_acl(self, requested_topics: Sequence[str], roles: Sequence[str]) -> list[str]
```

- **Purpose**: Load ACL from YAML and filter topics by role permissions
- **ACL Format**: `roles → allow → patterns` (with wildcard support)
- **Pattern Matching**: Topic starts with pattern (after stripping `*`)
- **Returns**: List of permitted topics

**Algorithm**:

```python
def _load_acl(requested_topics, roles) -> list[str]:
    # 1. Load YAML
    document = yaml.safe_load(self.acl_path.read_text(encoding="utf-8"))

    # 2. Collect allowed patterns for user's roles
    allowed_patterns: set[str] = set()
    for role in roles:
        allow_list = document["roles"][role].get("allow", [])
        for pattern in allow_list:
            if isinstance(pattern, str):
                allowed_patterns.add(pattern)

    # 3. Filter requested topics by patterns
    permitted = [
        topic for topic in requested_topics
        if self._topic_allowed(topic, allowed_patterns)
    ]
    return permitted
```

---

```python
def _topic_allowed(self, topic: str, patterns: Iterable[str]) -> bool
```

- **Purpose**: Check if topic matches any ACL pattern (with wildcard support)
- **Wildcard**: Pattern ending with `*` matches topic prefix
- **Example**: Pattern `memory.*` matches `memory.store`, `memory.timeline`, etc.

---

```python
def _decode_cursor(self, token: str) -> CursorState
```

- **Purpose**: Decode and validate cursor token (Gap 48)
- **Validation**: JSON decode, required fields, negative offset check
- **Metrics**: Track invalid cursors by reason (MALFORMED, NEGATIVE)
- **Observability**: Emit `sse_cursor_validation_seconds` for latency tracking
- **Returns**: `CursorState` with decoded fields

**Algorithm**:

```python
def _decode_cursor(token: str) -> CursorState:
    validation_start = time.perf_counter()

    # 1. JSON decode
    try:
        payload = json.loads(token)
    except json.JSONDecodeError as exc:
        self.observability.emit_metric("sse_invalid_cursor_total", 1.0, reason="MALFORMED")
        raise HTTPException(400, "CURSOR_DECODE_ERROR") from exc

    # 2. Extract required fields
    try:
        position = int(payload.get("offset", payload.get("pos")))
        ts_raw = payload["ts"]
        ts = self._parse_iso8601(ts_raw)
    except (KeyError, ValueError, TypeError) as exc:
        self.observability.emit_metric("sse_invalid_cursor_total", 1.0, reason="MALFORMED")
        raise HTTPException(400, "CURSOR_FIELDS_MISSING") from exc

    # 3. Validate offset
    if position < 0:
        self.observability.emit_metric("sse_invalid_cursor_total", 1.0, reason="NEGATIVE")
        raise HTTPException(400, "CURSOR_NEGATIVE_POSITION")

    # 4. Emit validation latency
    validation_duration = time.perf_counter() - validation_start
    self.observability.emit_metric("sse_cursor_validation_seconds", validation_duration)

    # 5. Return cursor state
    return CursorState(
        last_position=position,
        last_ts=ts,
        subscriber_id=payload.get("subscriber_id"),
        topic=payload.get("topic"),
        space_id=payload.get("space_id"),
        tenant_id=payload.get("tenant_id"),
    )
```

---

```python
def _parse_iso8601(value: str) -> datetime
```

- **Purpose**: Parse ISO8601 timestamp with timezone handling
- **Normalization**: Replace `Z` suffix with `+00:00` for Python compatibility
- **Default Timezone**: Assume UTC if no timezone provided
- **Returns**: Timezone-aware datetime in UTC

---

### 2. `acl.yaml`

**Purpose**: Topic ACL configuration with role-based permissions.

**Schema**:

```yaml
roles:
  <role_name>:
    allow:
      - "<topic_pattern>"
      - "<topic_pattern>"
```

**Example**:

```yaml
roles:
  household_device:
    allow:
      - "memory.*"
      - "events.*"

  security_operator:
    allow:
      - "policy.*"
      - "infra.sanitized.*"

  coordinator:
    allow:
      - "test.*"
      - "memory.*"
      - "events.*"
      - "policy.*"
```

**Pattern Matching**:

- `memory.*` → Matches `memory.store`, `memory.timeline`, `memory.recall`
- `events.*` → Matches `events.created`, `events.updated`
- `policy.*` → Matches `policy.evaluated`, `policy.violated`

---

### 3. `__init__.py`

**Purpose**: Export SSE module public API.

**Exported Classes**:

```python
__all__ = ["BackpressureMetrics", "SSEServer"]
```

---

## Usage Examples

### SSE Subscription with Cursor Resumption

```python
from k0.sse import SSEServer

server = SSEServer(wal, offset_store, observability, acl_path, qos)

# Initial subscription (no cursor)
entries, permitted = server.subscribe(
    tenant_id="tenant_001",
    space_id="space_001",
    subscriber_id="sub_abc123",
    topics=["memory.*", "events.*"],
    roles=["household_device"],
    cursor_token=None,
    fanout_limit=128,
)

# Stream entries
for entry in entries:
    print(f"Event: {entry.topic} @ position {entry.position}")

# Build cursor for next subscription
last_entry = entries[-1]
cursor = server.build_cursor(
    subscriber_id="sub_abc123",
    tenant_id="tenant_001",
    space_id="space_001",
    topic=last_entry.topic,
    offset=last_entry.position,
    commit_ts=last_entry.commit_ts,
)

# Resume subscription with cursor
entries, _ = server.subscribe(
    tenant_id="tenant_001",
    space_id="space_001",
    subscriber_id="sub_abc123",
    topics=["memory.*"],
    roles=["household_device"],
    cursor_token=cursor,
    fanout_limit=128,
)
```

### Backpressure Evaluation

```python
# Evaluate backpressure
metrics = server.evaluate_backpressure(
    subscriber_id="sub_abc123",
    tenant_id="tenant_001",
    space_id="space_001",
    topics=["memory.*", "events.*"],
)

print(f"Backpressure Level: {metrics.level}")
print(f"Max Lag: {metrics.lag_ms}ms")
print(f"Total Pending: {metrics.pending_events} events")

for topic_metric in metrics.topics:
    print(f"  {topic_metric.topic}: {topic_metric.pending_events} pending, {topic_metric.lag_ms}ms lag")

# Handle backpressure
if metrics.level == "shed":
    # Drop connection
    raise HTTPException(429, "TOO_MANY_PENDING_EVENTS")
elif metrics.level == "throttle":
    # Slow down event delivery
    await asyncio.sleep(0.5)
elif metrics.level == "warning":
    # Log warning
    logger.warning(f"High backpressure for sub_abc123: {metrics.pending_events} pending")
```

### Event Acknowledgment

```python
# Acknowledge events up to position 1500
server.acknowledge(
    subscriber_id="sub_abc123",
    tenant_id="tenant_001",
    space_id="space_001",
    topic="memory.timeline",
    offset=1500,
)

# Verify acknowledgment
offset_record = offset_store.fetch(
    subscriber_id="sub_abc123",
    topic="memory.timeline",
    space_id="space_001",
    tenant_id="tenant_001",
)

print(f"Acknowledged offset: {offset_record.offset}")
print(f"Last updated: {offset_record.updated_ts}")
```

---

## Backpressure Management (Gap 25)

### Configurable Thresholds

| Threshold | Default | Description |
|-----------|---------|-------------|
| `WARNING_LAG_MS` | 2000ms | Lag threshold for warning level |
| `WARNING_PENDING` | 5000 | Pending events threshold for warning |
| `THROTTLE_LAG_MS` | 5000ms | Lag threshold for throttle level |
| `THROTTLE_PENDING` | 20000 | Pending events threshold for throttle |
| `SHED_LAG_MS` | 15000ms | Lag threshold for shed level |
| `SHED_PENDING` | 50000 | Pending events threshold for shed |

### Decision Matrix

```
if lag > SHED_LAG_MS OR pending > SHED_PENDING:
    level = "shed"  # Drop connection
elif lag > THROTTLE_LAG_MS OR pending > THROTTLE_PENDING:
    level = "throttle"  # Slow down delivery
elif lag > WARNING_LAG_MS OR pending > WARNING_PENDING:
    level = "warning"  # Emit warning logs
else:
    level = "normal"  # No action
```

### Lag Calculation

```
lag_ms = (latest_commit_ts - ack_ts).total_seconds() * 1000

where:
  latest_commit_ts = Most recent event timestamp in WAL for topic
  ack_ts = Timestamp of last acknowledged offset for subscriber
```

---

## Integration Points

### Upstream Dependencies

- **`k0.storage.wal`**: ReadAheadLog for streaming events
- **`k0.storage.offsets`**: OffsetStore for tracking subscriber positions
- **`k0.obs`**: ObservabilityEmitter for metrics/events
- **`k0.qos`**: QoSContext for fanout budget enforcement
- **PyYAML**: YAML parsing for ACL configuration

### Downstream Consumers

- **`k0.ports.sse`**: HTTP handlers for `/k0/sse.subscribe`, `/k0/sse.ack`
- **`k0.workers.sse_server`**: SSE server loop for real-time streaming
- **`k0.cli`**: CLI commands for SSE server management

---

## Performance & Observability

### Metrics

- **`sse_invalid_cursor_total`**: Count of invalid cursors by reason (MALFORMED, NEGATIVE)
- **`sse_cursor_validation_seconds`**: Cursor validation latency (Gap 48)
- **`sse_backpressure_level`**: Current backpressure level (normal/warning/throttle/shed)
- **`sse_pending_events_total`**: Total pending events across all subscribers
- **`sse_lag_ms`**: Maximum lag across all subscribers

### Performance Targets (P95)

| Operation | Latency | Throughput |
|-----------|---------|------------|
| `subscribe()` | <50ms | 200 req/s |
| `evaluate_backpressure()` | <20ms | 500 req/s |
| `acknowledge()` | <10ms | 1000 req/s |
| `_decode_cursor()` | <5ms | 2000 req/s |

---

## Error Handling

### HTTP Exceptions

- **400 BAD_REQUEST**: Invalid fanout limit, cursor decode error, negative offset
- **403 FORBIDDEN**: Topic access denied (no matching ACL patterns)
- **429 TOO_MANY_REQUESTS**: Backpressure shed level exceeded
- **500 INTERNAL_SERVER_ERROR**: ACL parse error, invalid ACL shape

**Example**:

```python
try:
    entries, _ = server.subscribe(...)
except HTTPException as exc:
    if exc.status_code == 403:
        logger.error("Topic access denied for user")
    elif exc.status_code == 400:
        logger.error(f"Invalid request: {exc.detail}")
    raise
```

---

## Related Modules

- **`k0.storage.wal`**: WriteAheadLog for event streaming
- **`k0.storage.offsets`**: OffsetStore for acknowledgment tracking
- **`k0.obs`**: ObservabilityEmitter for metrics/events
- **`k0.ports.sse`**: HTTP handlers for SSE endpoints
- **`k0.qos`**: QoSContext for fanout budget enforcement

---

## Related ADRs

- **ADR-0130**: SSE Architecture and Topic-Based Subscriptions
- **ADR-0131**: Backpressure Thresholds and Shed Policies (Gap 25)
- **ADR-0132**: Topic ACL and Role-Based Permissions
- **ADR-0133**: Cursor Validation and Security (Gap 48)

---

## Key Design Decisions

1. **Topic-Based ACL**: Role-based permissions with wildcard pattern matching for flexible access control
2. **Cursor Validation**: Scope checking (tenant/space/subscriber) prevents cursor replay attacks
3. **Backpressure Levels**: Configurable thresholds (warning/throttle/shed) for graceful degradation
4. **WAL-Backed Streaming**: Events sourced directly from WAL for consistency and durability
5. **Per-Topic Metrics**: Backpressure tracked per topic for fine-grained monitoring
6. **Defensive Observability**: Metrics/events failures don't break SSE delivery (Gap 48)
7. **Fanout Budget**: QoS integration limits events per subscription for resource protection
