# K1 Internal Event Bus Contracts

**Source ADR:** ADR-0048

## Overview

This directory contains contracts for K1's internal event bus, which enables loose coupling between K1 components through publish/subscribe messaging.

## Contracts Included

### 1. Event Schemas Contract (`event_schemas.yaml`)
- Internal event type definitions
- Event payload schemas
- Event metadata requirements
- Event versioning

### 2. Event Routing Contract (`event_routing.yaml`)
- Topic-based routing rules
- Subscription patterns
- Event filtering logic
- Priority handling

### 3. Delivery Guarantees Contract (`delivery_guarantees.yaml`)
- At-most-once delivery semantics
- At-least-once delivery semantics
- Ordering guarantees
- Durability requirements

### 4. Backpressure Contract (`backpressure.yaml`)
- Backpressure detection thresholds
- Flow control mechanisms
- Queue overflow handling
- Producer throttling rules

## Key Specifications

### Event Bus Architecture
```yaml
event_bus:
  type: in_memory_pub_sub
  implementation: asyncio_queues
  max_subscribers_per_topic: 100
  queue_size_per_subscriber: 1000
  delivery_mode: at_most_once
```

### Event Schema
```yaml
event:
  event_id: string           # Unique event ID (UUID)
  event_type: string         # Event type (e.g., "agent.state_changed")
  timestamp: iso8601         # Event creation timestamp
  source: string             # Component that published event
  payload: object            # Event-specific data
  trace_id: string           # cognitive_trace_id for correlation
  priority: enum             # URGENT, HIGH, NORMAL, LOW
```

### Topic Naming Convention
```
<layer>.<component>.<event_type>
Examples:
  - kernel.orchestrator.task_assigned
  - execution.tool_runner.tool_completed
  - state.session_state.delta_applied
  - infrastructure.thermal.state_changed
```

### Subscription Pattern
```yaml
subscription:
  topic: string              # Topic to subscribe to (supports wildcards)
  callback: callable         # Async callback function
  filter: optional           # Event filtering predicate
  priority: enum             # Subscription priority
```

### Wildcard Patterns
- `*` - Single level wildcard (e.g., `kernel.*.task_assigned`)
- `**` - Multi-level wildcard (e.g., `kernel.**`)
- `#` - All events

## Event Types

### Layer 1 - Kernel Events
- `kernel.orchestrator.task_assigned`
- `kernel.orchestrator.agent_selected`
- `kernel.agent_fabric.agent_hired`
- `kernel.planner.plan_generated`
- `kernel.protocol_monitor.violation_detected`

### Layer 2 - State Events
- `state.session_state.delta_applied`
- `state.session_state.eviction_triggered`
- `state.memory_manager.receipt_issued`

### Layer 3 - Execution Events
- `execution.tool_runner.tool_called`
- `execution.tool_runner.tool_completed`
- `execution.model_hub.inference_started`
- `execution.model_hub.inference_completed`

### Layer 4 - Ingress Events
- `ingress.api_gateway.request_received`
- `ingress.websocket.connection_established`
- `ingress.voice.frame_processed`

### Layer 5 - Infrastructure Events
- `infrastructure.thermal.state_changed`
- `infrastructure.config.hot_reload_completed`
- `infrastructure.observability.metric_exported`

## Performance Characteristics

```yaml
performance:
  publish_latency_p95_ms: 1
  delivery_latency_p95_ms: 5
  throughput_events_per_sec: 10000
  max_event_size_kb: 64
  queue_overflow_policy: drop_oldest
```

## Usage Examples

### Publishing Events
```python
# Publish event to internal event bus
await event_bus.publish(
    topic="kernel.orchestrator.task_assigned",
    payload={
        "task_id": "task-123",
        "agent_id": "agent-456",
        "trace_id": "trace-789"
    },
    priority=EventPriority.HIGH
)
```

### Subscribing to Events
```python
# Subscribe to events
async def on_task_assigned(event: Event):
    print(f"Task assigned: {event.payload['task_id']}")

await event_bus.subscribe(
    topic="kernel.orchestrator.task_assigned",
    callback=on_task_assigned
)
```

## Related Contracts

- Bridge Integration: `../bridge_integration/`
- K0 SSE Contracts: `../k0_sse/`
- Actor Model Contracts: `../actor_model/`

---

**Last Updated:** 2025-10-13
