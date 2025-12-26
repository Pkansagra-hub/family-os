# ADR-055: Stream-Based Bus Architecture

**Status**: Accepted  
**Date**: 2025-12-26  
**Decision Makers**: K0 Architecture Team  
**Supersedes**: N/A

## Context

The feedback subsystem needs to publish signals to the bus without writing to WAL. The current BusDispatcher assumes all messages:
1. Originate from `st_wal` (WAL-backed)
2. Have strictly monotonic offsets
3. Use `msg.offset` for idempotency

This creates three critical problems when adding non-WAL feedback signals:

### Problem 1: Bus Monotonicity Under Load
If feedback worker reads `last_offset` and publishes with `offset = last_offset + 1`, it races with WAL dispatch:
- Thread A: WAL dispatcher publishes offset=100
- Thread B: Feedback worker reads last_offset=100, prepares offset=101
- Thread A: WAL dispatcher publishes offset=101 (WAL-backed)
- Thread B: Feedback worker tries to publish offset=101 (feedback, non-WAL)
- Result: Monotonic check fails OR feedback overwrites WAL event

### Problem 2: Feedback Floods & Backpressure
10,000 simultaneous feedback signals can starve command/pipeline processing:
- No separate QoS budget for feedback vs WAL events
- Single scheduler port means feedback consumes tokens needed for critical operations
- No backpressure signal when feedback queue depth exceeds capacity

### Problem 3: Restart & Offset Reset Semantics
- `_last_offset` is in-memory only
- After restart, `_last_offset = None` until first WAL event
- Feedback worker using synthetic offsets has no stable idempotency key across restarts

## Alternatives Considered

### Option A: Feedback → WAL (Most Correct, WAL Pollution)
**Approach**: Write feedback signals to `st_wal` before publishing to bus.

**Pros**:
- Preserves all existing bus invariants
- Guaranteed monotonic offsets
- Restart-safe idempotency

**Cons**:
- WAL pollution: feedback signals don't need durability guarantees
- Increased WAL write volume (10,000 feedback/sec → 10,000 WAL writes/sec)
- Performance degradation under feedback floods

**Verdict**: Rejected due to WAL pollution and performance impact.

### Option B: Separate Feedback Bus (Simple, Bus Explosion)
**Approach**: Create `FeedbackBusDispatcher` as separate implementation.

**Pros**:
- Clean separation
- No risk to WAL bus
- Simple to implement

**Cons**:
- Code duplication (two full bus implementations)
- "Bus explosion" - need separate buses for every non-WAL use case
- Maintenance burden (bugs fixed in one bus, not the other)

**Verdict**: Rejected due to code duplication and maintenance burden.

### Option C: Category-Aware Bus with Optional Offset (Complex, Invasive)
**Approach**: Make `BusMessage.offset` optional, add `category` field.

**Pros**:
- One bus, one message type
- Avoids duplication

**Cons**:
- **Too invasive**: Changes BusMessage contract globally
- Breaks existing pipelines that assume `msg.offset` is always present
- Monotonic enforcement logic becomes ambiguous
- High blast radius: all pipeline tests need updating

**Verdict**: Rejected due to invasiveness and risk of breaking WAL delivery.

### Option D: Streams Inside the Bus (Chosen)
**Approach**: One BusDispatcher with multiple independent streams.

**Pros**:
- **Preserves WAL invariants**: WAL stream unchanged, default behavior identical
- **Enforces correctness**: stream="wal" requires offset; stream="feedback" requires message_id
- **QoS isolation**: Per-stream scheduler ports prevent feedback from starving WAL
- **No duplication**: Single BusDispatcher implementation
- **Extensible**: New streams (e.g., "telemetry", "audit") can be added without explosion

**Cons**:
- Medium-sized change (bus core + enforcement + tests)
- Requires careful design to avoid semantic collision

**Verdict**: **Accepted** - best balance of correctness, performance, and maintainability.

## Decision

Implement **stream-based bus architecture** with enforcement:

### 1. Streams as Independent Offset Domains

Add `stream: str` parameter to `BusDispatcher.__init__()` and `dispatch()`:

```python
class BusDispatcher:
    def __init__(self, *, scheduler: Scheduler, stream: str = "wal", ...):
        self._stream = stream
        self._stream_state = {
            "lock": asyncio.Lock(),
            "last_offset": None,
            "enforce_monotonic": stream == "wal",
            "require_offset": stream == "wal",
            "require_message_id": stream != "wal",
        }
```

**Stream definitions**:
- `stream="wal"` (default): WAL-backed messages, strict monotonic offsets, current behavior
- `stream="feedback"`: Non-WAL feedback signals, id-based idempotency, no monotonic offsets

### 2. Enforcement Layer

Add validation in `dispatch()`:

```python
async def dispatch(self, messages: Iterable[BusMessage]) -> None:
    for message in batch:
        if self._stream_state["require_offset"] and message.offset is None:
            raise ValueError(f"stream={self._stream} requires offset")
        if self._stream_state["require_message_id"]:
            if not message.metadata or "message_id" not in message.metadata:
                raise ValueError(f"stream={self._stream} requires metadata['message_id']")
        if self._stream_state["enforce_monotonic"]:
            self._ensure_monotonic(message.offset)
```

This prevents:
- Feedback signals from accidentally using WAL stream (would fail offset requirement)
- WAL events from accidentally using feedback stream (would fail monotonic check)

### 3. Per-Stream QoS Isolation

Each stream gets its own scheduler port:

```python
BusDispatcher(scheduler, stream="wal", port="bus_wal")
BusDispatcher(scheduler, stream="feedback", port="bus_feedback")
```

Scheduler profile:
```python
SchedulerProfile(
    port_limits={
        "bus_wal": 32,      # WAL stream (high priority)
        "bus_feedback": 16,  # Feedback stream (lower priority)
    }
)
```

This ensures feedback floods cannot starve WAL event processing.

### 4. Topic Routing (Gold Standard)

For maximum correctness, add `UniversalBus` facade that routes by topic:

```python
class UniversalBus:
    def __init__(self, wal_dispatcher: BusDispatcher, feedback_dispatcher: BusDispatcher):
        self._wal = wal_dispatcher
        self._feedback = feedback_dispatcher
    
    async def dispatch(self, messages: Iterable[BusMessage]) -> None:
        wal_messages = [m for m in messages if not m.topic.startswith("feedback.")]
        feedback_messages = [m for m in messages if m.topic.startswith("feedback.")]
        await asyncio.gather(
            self._wal.dispatch(wal_messages),
            self._feedback.dispatch(feedback_messages),
        )
```

This removes the chance a developer forgets to pass `stream=` parameter.

## Consequences

### Positive

✅ **Correctness**: WAL stream semantics unchanged, impossible to violate monotonicity  
✅ **Performance**: QoS isolation prevents feedback floods from blocking critical operations  
✅ **Extensibility**: New streams (telemetry, audit) can be added without code duplication  
✅ **Idempotency**: Feedback uses `feedback_id`, not synthetic offsets  
✅ **Restart-safe**: No in-memory offset state for feedback stream  

### Negative

⚠️ **Complexity**: Medium-sized change (bus core + enforcement + worker + tests)  
⚠️ **Migration**: Existing code uses default `stream="wal"`, must be explicit for feedback  

### Neutral

ℹ️ **Backpressure**: Add `feedback_queue_depth` metric, decide later on 429 throttling  
ℹ️ **Testing**: Requires concurrent WAL + feedback dispatch tests to prove isolation  

## Implementation Plan

1. Add `stream` parameter to `BusDispatcher.__init__()` with enforcement logic
2. Add per-stream state management (lock, last_offset, validation)
3. Update `dispatch()` to validate stream requirements
4. Add `UniversalBus` facade for topic-based routing
5. Implement feedback worker using `stream="feedback"`
6. Add `feedback_queue_depth` metric in feedback worker
7. Write integration tests: concurrent WAL + feedback dispatch under flood

## References

- FEEDBACK-021: Design stream-based BusDispatcher with per-stream state
- FEEDBACK-022: Implement stream routing (wal vs feedback) with enforcement
- FEEDBACK-023: Add per-stream QoS isolation (separate scheduler ports)
- [k0/bus/core.py](../../k0/bus/core.py) - Current BusDispatcher implementation
- [docs/plans/FEEDBACK-issues-tracker.md](../../plans/FEEDBACK-issues-tracker.md) - M0.5 milestone
