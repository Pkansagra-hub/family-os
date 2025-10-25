# K0 Bridge - K1↔K0 Communication Layer

**Purpose:** Bridge between K1 Intelligence Module and K0 Memory Module

**Location:** `k1/l5_infrastructure/bridge_k0/`

**ADRs:**

- **ADR-0001a:** K0 Bridge Architecture (dual-protocol, 4 ports)
- **ADR-0024:** Performance Budgets (latency targets)
- **ADR-0042:** K0 SSE Event Streaming (durable events)

---

## Overview

The K0 Bridge implements the communication protocol between K1 (AI agentic orchestrator) and K0 (memory kernel). It provides 4 client modules corresponding to K0's 4 external ports:

| Client | Port | Purpose | Performance |
|--------|------|---------|-------------|
| `command_client.py` | Command (`:5200`) | Memory writes, actions | <50ms GREEN, <200ms AMBER/RED |
| `query_client.py` | Query (`:5201`) | Memory retrieval, search | <100ms P95 |
| `sse_client.py` | SSE (`:5202`) | Real-time events | <5ms delivery |
| `batch_client.py` | - | SessionState delta batching | <10ms overhead, 80% reduction |
| `observability_client.py` | Observability (`:5203`) | Metrics push | <20ms |

---

## Batch Client Implementation

### Features

**✅ Implemented (January 2025):**

- SessionState delta batching (field-level change tracking)
- 3-trigger flush (250ms timer OR 64KB size OR 100 deltas)
- Delta coalescing (remove redundant updates, last-write-wins)
- Fairness queue (round-robin per session, max 5 deltas/session)
- zstd compression (level 3 for batches >1KB)
- Integration with K0 Command Port (uses `command_client.py`)
- Prometheus metrics (batch size, compression ratio, latency)
- cognitive_trace_id propagation

### Usage

```python
from k1.l5_infrastructure.bridge_k0.batch_client import (
    BatchClient,
    SessionStateDelta,
    DeltaOperation,
    FlushReason,
)
from k1.l5_infrastructure.bridge_k0.command_client import K0CommandClient

# Initialize clients
command_client = K0CommandClient(base_url="http://localhost:5200")
batch_client = BatchClient(
    command_client=command_client,
    flush_interval_ms=250,  # 250ms flush interval
    max_batch_size_bytes=64 * 1024,  # 64KB size trigger
    max_batch_count=100,  # 100 deltas trigger
    enable_compression=True,  # Enable zstd compression
)

# Start batch client (begins periodic flush loop)
await batch_client.start()

# Add SessionState deltas
delta = SessionStateDelta(
    session_id="session_abc123",
    field_path="control.current_flow",
    operation=DeltaOperation.SET,
    new_value="flow_xyz",
    old_value="flow_previous",
    section="control",
    cognitive_trace_id="trace_123",
)

await batch_client.add_delta(delta)

# Deltas automatically flushed after 250ms OR 64KB OR 100 deltas

# Explicit flush (optional)
stats = await batch_client.flush(reason=FlushReason.EXPLICIT)
print(f"Flushed {stats.deltas_sent} deltas, {stats.deltas_coalesced} coalesced")

# Stop batch client (flushes pending deltas)
await batch_client.stop(flush_pending=True)
```

### Batching Strategy

**3-Trigger Flush (Nagle Algorithm 1984):**

1. **Timer Trigger (250ms):** Flush every 250ms regardless of size/count
2. **Size Trigger (64KB):** Flush when batch exceeds 64KB uncompressed
3. **Count Trigger (100 deltas):** Flush when batch exceeds 100 deltas

**Delta Coalescing:** Keep only latest value per field_path (last-write-wins)

**Fairness Queue:** Round-robin per session, max 5 deltas/session/batch

**Compression:** zstd level 3 for batches >1KB (2-3× reduction typical)

### Metrics

| Metric | Type | Purpose |
|--------|------|---------|
| `batch_deltas_queued_total` | Counter | Total deltas queued |
| `batch_flushes_total` | Counter | Total flushes (by reason) |
| `batch_size_deltas` | Histogram | Deltas per batch |
| `batch_processing_latency_ms` | Histogram | Batch processing latency |
| `batch_coalesced_deltas_total` | Counter | Deltas removed by coalescing |

---

## SSE Client Implementation

### Features

**✅ Implemented (January 2025):**

- HTTP GET to K0 SSE Port (`:5202/k0/sse.subscribe`)
- EventSource client (W3C SSE protocol)
- Topic-based filtering (server-side, K0 filters events)
- Cursor-based resume (Last-Event-ID header, no event loss)
- Exponential backoff reconnection (1s → 2s → 4s → 8s → 16s max)
- SSE event parsing (event, data, id, retry fields)
- Backpressure advisory handling (throttle, lag-warning, shed)
- Prometheus metrics (event rate, delivery latency, reconnections)
- cognitive_trace_id propagation (end-to-end observability)

### Usage

```python
from k1.l5_infrastructure.bridge_k0.sse_client import K0SSEClient

# Initialize client
client = K0SSEClient(base_url="http://localhost:5202")

# Subscribe to events (long-lived connection)
async for event in client.subscribe(
    topics=["k0.memory.write", "k0.sync.status"],
    subscriber_id="k1_agent_123",
    space_id="family_home",
    tenant_id="family_001",
    cognitive_trace_id="trace_xyz789"
):
    # Handle event
    if event.event == "trace":
        print(f"Memory event: {event.data}")
    elif event.event == "advisory":
        print(f"Backpressure: {event.data['type']}")

    # Cursor automatically tracked for resume
```

### Event Types

**K0 SSE Event Types (ADR-0016):**

1. **`trace`** - Memory write notifications
   - `data.cursor`: Resume cursor
   - `data.topic`: Event topic (e.g., `k0.memory.write`)
   - `data.wal_pos`: WAL offset
   - `data.commit_ts`: Commit timestamp

2. **`advisory`** - Backpressure warnings
   - `data.type`: `lag-warning`, `throttled`, `shed`
   - `data.lag_ms`: Lag in milliseconds
   - `data.pending_events`: Queue depth

### Reconnection Strategy

**Exponential Backoff (ADR-0042c):**

- **First attempt:** 1s delay
- **Second attempt:** 2s delay
- **Third attempt:** 4s delay
- **Fourth attempt:** 8s delay
- **Fifth+ attempts:** 16s delay (max)

**Cursor-based Resume:**

- Client sends `Last-Event-ID: <cursor>` header on reconnect
- K0 resumes stream from cursor position
- **No events missed** during reconnection

### Error Handling

**Non-Retryable Errors (Immediate Failure):**

- **400 Bad Request:** Invalid topics, missing subscriber_id
- **403 Forbidden:** ACL deny, insufficient permissions
- **429 Too Many Requests:** QoS budget exhausted, backpressure shed

**Retryable Errors (Exponential Backoff):**

- **5xx Server Error:** K0 unavailable, transient failure
- **Network Error:** Connection timeout, DNS failure

### Metrics

**Prometheus Metrics Exported:**

```python
# Active subscriptions (gauge)
k1_intelligence_sse_subscriptions_active

# Events received (counter, labels: event_type, topic)
k1_intelligence_sse_events_received_total{event_type="trace", topic="k0.memory.write"}

# Delivery latency (histogram, labels: event_type)
k1_intelligence_sse_delivery_latency_ms{event_type="trace"}

# Reconnections (counter, labels: reason)
k1_intelligence_sse_reconnection_total{reason="connection_error"}

# Connection duration (histogram)
k1_intelligence_sse_connection_duration_seconds
```

### Performance

**Performance Budget (ADR-0024):**

- **Event delivery:** <5ms P95 (K0 commit_ts → K1 reception)
- **Reconnection:** <1s first attempt (exponential backoff)
- **Subscription overhead:** <10ms (connection establishment)
- **Throughput:** 100+ events/sec

---

## Testing

### Unit Tests

**Location:** `tests/k1/l5_infrastructure/bridge_k0/test_sse_client.py`

**Test Coverage:**

- ✅ Basic subscription (happy path)
- ✅ Event parsing (trace, advisory events)
- ✅ Cursor-based resume (Last-Event-ID)
- ✅ Reconnection with exponential backoff
- ✅ Error handling (400, 403, 429, 5xx)
- ✅ Backpressure advisory handling
- ✅ Metrics emission

**Run Unit Tests:**

```powershell
python -m ward test --path tests/k1/l5_infrastructure/bridge_k0/test_sse_client.py
```

### Integration Tests

**Requires K0 Running:**

```powershell
# Start K0 kernel
cd d:\familyos\k0
python -m k0.kernel.main

# Run integration tests
python -m ward test --path tests/k1/l5_infrastructure/bridge_k0/ -m integration
```

### Performance Tests

**Performance Budget Validation:**

```powershell
# Run performance tests
python -m ward test --path tests/k1/l5_infrastructure/bridge_k0/ -m performance
```

---

## Architecture Integration

### K0 SSE Port (Server-Side)

**K0 Implementation:** `k0/ports/sse.py`

**Endpoint:**

```
GET /k0/sse.subscribe?topics=k0.memory.write,k0.sync.status&space_id=family_home&tenant_id=family_001
```

**Headers:**

```
Accept: text/event-stream
X-Cognitive-Trace-Id: trace_xyz789
X-SSE-Subscriber: k1_agent_123
X-SSE-Band: GREEN
X-SSE-Roles: household_device
Last-Event-ID: event_123  # Optional, for resume
```

**Response (SSE Format):**

```
event: trace
data: {"cursor": "event_124", "topic": "k0.memory.write", "wal_pos": 100, "commit_ts": "2025-01-24T00:00:00Z"}
id: event_124

event: advisory
data: {"type": "lag-warning", "lag_ms": 500, "pending_events": 10}
id: advisory_001

```

### K1 Event Bus Integration

**SSE client → K1 event bus flow:**

```
K0 SSE Port (:5202)
    ↓ HTTP GET (SSE stream)
K0SSEClient (sse_client.py)
    ↓ Parse SSE events (event, data, id)
K1 Event Bus (event_bus.py)
    ↓ Publish(EventTopic.MEMORY_UPDATED)
K1 Agents (Layer 3)
    ↓ Handle memory updates
```

**Example Integration:**

```python
from k1.l5_infrastructure.bridge_k0.sse_client import K0SSEClient
from k1.l5_infrastructure.event_bus import EventBus, EventTopic

# Initialize
sse_client = K0SSEClient()
event_bus = EventBus.get_instance()

# Subscribe and forward to event bus
async for event in sse_client.subscribe(
    topics=["k0.memory.write"],
    subscriber_id="k1_orchestrator",
    space_id="family_home",
    tenant_id="family_001"
):
    if event.event == "trace":
        # Forward memory events to K1 event bus
        await event_bus.publish(
            topic=EventTopic.MEMORY_UPDATED,
            payload=event.data,
            cognitive_trace_id=event.data.get("cognitive_trace_id")
        )
```

---

## Next Steps

### Phase 1 (Completed)

- ✅ SSE client core implementation
- ✅ Event parsing (W3C SSE format)
- ✅ Cursor-based resume
- ✅ Exponential backoff reconnection
- ✅ Error handling
- ✅ Metrics emission

### Phase 2 (Next)

- [ ] Integration tests with real K0
- [ ] Performance validation (<5ms P95)
- [ ] Event bus integration (Layer 5 → Layer 2)
- [ ] Cursor persistence (SQLite, 7-day retention)
- [ ] Backpressure adaptive throttling

### Phase 3 (Future)

- [ ] Multi-subscriber coordination
- [ ] Event replay from cursor
- [ ] Advanced filtering (predicate pushdown)
- [ ] Event transformation pipeline

---

## References

**Primary ADRs:**

- [ADR-0001a: K0 Bridge Architecture](../../../../docs/architecture/decisions/0001a-k0-bridge-communication-protocol.md)
- [ADR-0016: SSE Event Schemas](../../../../docs/architecture/decisions/0016-sse-event-schemas.md)
- [ADR-0042: K0 SSE Event Streaming](../../../../docs/architecture/decisions/0042-k0-sse-event-streaming.md)
- [ADR-0042c: Reconnection Strategy](../../../../docs/architecture/decisions/0042c-sse-reconnection-strategy.md)

**Related ADRs:**

- [ADR-0024: Performance Budgets](../../../../docs/architecture/decisions/0024-performance-budgets.md)
- [ADR-0029: Prometheus Metrics](../../../../docs/architecture/decisions/0029-prometheus-metrics.md)
- [ADR-0043: SSE Topic Taxonomy](../../../../docs/architecture/decisions/0043-sse-topic-taxonomy.md)

**K0 Implementation:**

- `k0/ports/sse.py` - K0 SSE port implementation
- `k0/sse/server.py` - SSE server logic
- `k0/contracts/openapi.k0.yaml` - K0 API schema

**Research:**

- [W3C Server-Sent Events Spec](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [EventSource API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [Exponential Backoff (AWS)](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)

---

**Last Updated:** January 24, 2025
**Status:** Phase 1 Complete ✅
**Next Milestone:** Integration Testing with K0
