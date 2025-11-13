# Bus Module

## Overview

The **bus** module is the post-commit dispatch coordinator for K0, responsible for reliably fanning out Write-Ahead Log (WAL) commit events to multiple downstream consumers (SSE endpoints, driver outboxes, etc.). It provides a middleware-based architecture with scheduler integration for QoS-aware message distribution.

## Purpose

- **Event Distribution**: Fan out WAL commit records to registered sinks after transactions commit
- **QoS Integration**: Coordinate with the scheduler to enforce band-based rate limits and token costs
- **Middleware Pipeline**: Support observability, tracing, and metrics through composable middleware
- **Ordered Delivery**: Ensure monotonic WAL offset processing to maintain event ordering guarantees

## Architecture

The bus follows a **middleware-chain pattern** similar to web frameworks, allowing cross-cutting concerns (timing, tracing, metrics) to be injected around the core dispatch logic.

```
WAL Commit → BusDispatcher → Middleware Chain → Sinks (SSE, Outbox)
                    ↓
               Scheduler (QoS tokens)
```

## Core Components

### 1. `core.py` - Dispatch Coordinator

**`BusMessage`**
- Immutable representation of a post-commit WAL record
- Fields: `topic`, `payload`, `offset`, `trace_id`

**`BusDispatchContext`**
- Runtime context exposed to middleware and sinks
- Tracks message, band, port, token cost, timing, and trace information
- Available via `current_dispatch_context()` ContextVar

**`BusDispatcher`**
- Main orchestrator for WAL event fan-out
- Acquires scheduler tokens before dispatch (respects QoS bands)
- Maintains monotonic WAL offset ordering
- Executes middleware chain around sink invocation

**Key Functions:**
- `dispatch(messages)` - Batch dispatch with WAL ordering enforcement
- `register_sink(sink)` - Add async sink for message delivery
- `register_middleware(middleware)` - Add middleware to execution chain

**Middleware Types:**
- `BusMiddleware` - `Callable[[BusDispatchContext, BusMiddlewareHandler], Awaitable[None]]`
- `BusMiddlewareHandler` - Next handler in chain
- `BusSink` - `Callable[[BusMessage], Awaitable[None]]`

### 2. `middleware.py` - Built-in Middleware Utilities

**`timestamp_middleware(clock=None)`**
- Records wall-clock and monotonic timestamps for each dispatch
- Populates `started_at`, `completed_at`, `duration_seconds` in context

**`latency_metrics_middleware(metrics, buckets=None)`**
- Emits Prometheus-compatible latency histograms and counters
- Metrics:
  - `bus_dispatch_latency_seconds` (histogram with topic/outcome labels)
  - `bus_dispatch_total` (counter)
  - `bus_dispatch_failures_total` (counter for failures only)

**`tracing_middleware(tracer_factory, span_name="bus.dispatch", span_kind=SpanKind.CONSUMER)`**
- Propagates cognitive trace IDs through dispatch
- Creates OpenTelemetry spans with bus-specific attributes
- Binds structured logging context (trace_id, topic, offset, band, port)

## Integration Points

### With QoS Scheduler
```python
from k0.qos import Scheduler
from k0.bus import BusDispatcher

scheduler = Scheduler(...)
dispatcher = BusDispatcher(
    scheduler=scheduler,
    port="bus",
    default_band="GREEN",
    token_cost=1,
)
```

### With Observability
```python
from k0.bus import latency_metrics_middleware, tracing_middleware
from k0.obs import MetricsExporter, TracerFactory

dispatcher.register_middleware(timestamp_middleware())
dispatcher.register_middleware(latency_metrics_middleware(metrics))
dispatcher.register_middleware(tracing_middleware(tracer_factory=tracer))
```

### With Sinks (SSE, Outbox)
```python
async def sse_sink(message: BusMessage) -> None:
    await sse_manager.broadcast(message.topic, message.payload)

async def outbox_sink(message: BusMessage) -> None:
    await outbox_store.enqueue_from_wal(message)

dispatcher.register_sink(sse_sink)
dispatcher.register_sink(outbox_sink)
```

## Usage Example

```python
from k0.bus import BusDispatcher, BusMessage, timestamp_middleware
from k0.qos import Scheduler

# Initialize
scheduler = Scheduler(...)
dispatcher = BusDispatcher(
    scheduler=scheduler,
    port="bus",
    default_band="GREEN",
    token_cost=1,
)

# Add middleware
dispatcher.register_middleware(timestamp_middleware())

# Register sinks
dispatcher.register_sink(my_async_sink)

# Dispatch WAL events
messages = [
    BusMessage(topic="envelopes", payload=b"...", offset=100),
    BusMessage(topic="events", payload=b"...", offset=101),
]
await dispatcher.dispatch(messages)
```

## Key Guarantees

1. **Monotonic Ordering**: WAL offsets must be non-decreasing; violations raise `ValueError`
2. **Scheduler Integration**: All dispatches acquire QoS tokens before execution
3. **Middleware Isolation**: Each middleware can observe/modify context but must call next handler
4. **Concurrent Safety**: Internal lock ensures thread-safe dispatch batching
5. **Context Propagation**: `current_dispatch_context()` available to sinks and middleware

## Error Handling

- Middleware exceptions bubble up and mark dispatch outcome as "failure" in metrics
- Sinks execute concurrently via `asyncio.gather()` - individual sink failures don't block others
- Scheduler token cleanup guaranteed via `finally` block

## Performance Considerations

- Batch dispatch preferred over single-message calls (reduces lock contention)
- Middleware chain overhead: ~3 function calls per message per middleware
- Sink fan-out is concurrent (parallel `asyncio.create_task()`)
- Monotonic ordering check is O(n) per batch (sorted once)

## Configuration

No direct configuration file - dispatcher initialized programmatically with:
- `port` - Scheduler port identifier
- `default_band` - QoS band (GREEN/AMBER/RED)
- `token_cost` - Scheduler tokens consumed per dispatch
- `band_resolver` - Optional function to override band per message

## Testing

See `tests/k0/bus/` for integration tests validating:
- Middleware chain execution order
- Scheduler token acquisition/release
- WAL offset monotonicity enforcement
- Context propagation to sinks

## Related Modules

- **k0.qos**: Scheduler for token-based rate limiting
- **k0.sse**: Server-sent events sink
- **k0.outbox**: Driver outbox sink
- **k0.obs**: Metrics and tracing infrastructure
- **k0.uow**: Unit of Work pattern (WAL commit source)
