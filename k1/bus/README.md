# K1 Bus Module (Coordination: The Nervous System)

## Overview

The `bus/` module implements the **Coordination: The Nervous System** layer of the K1 Cognitive Architecture. This module provides the communication infrastructure for all K1 components, enabling low-latency, high-frequency coordination through a single physical bus (with two logical lanes: event topics and delta topics) plus direct mailbox routing.

## Purpose

- **Event lane (k1.* topics)**: Pub/sub for lifecycle + coordination events (STRICT/RELAXED/BEST_EFFORT by prefix)
- **Delta lane (k1.*.delta.v1 topics)**: Fire-and-forget progress/state deltas (STRICT by convention)
- **Mailbox Router**: Location-transparent routing for actor-to-actor communication
- **Message Passing**: Actor Model communication with backpressure management

## Architecture

### Core Components

- **`event_bus.py`**: shared transport implementation for the K1 bus (topic publish/subscribe)
- **`delta_bus.py`**: ergonomic delta-lane wrapper (topic conventions; delegates aggregation to Concierge)
- **`mailbox_router.py`**: UUID-to-mailbox mapping with location transparency

### Event Categories

Following ADR-0048 (K1 Internal Event Bus):

- **`k1.orchestration.*`**: Agent coordination (task announcements, proposals, selection)
- **`k1.planning.*`**: Planning phase transitions (sketch, expand, validate, commit)
- **`k1.agent.*`**: Agent lifecycle (FSM transitions: PENDING → WARMING → ACTIVE → IDLE)
- **`k1.tool.*`**: Tool execution status (started, completed, failed)
- **`k1.barge_in.*`**: Voice interrupts (user barge-in detected)
- **`k1.memory.*`**: Memory cache operations (eviction, warming)

### NOT in K1 Event Bus (Use K0 SSE)

- **`k0.config.*`**: Config hot-reload (durable, needs replay)
- **`k0.receipt.*`**: Receipt acknowledgments (durable, audit trail)
- **`k0.learning.*`**: Learning feedback (durable, ML training)
- **`k0.crdt.*`**: CRDT sync (durable, family synchronization)
- **`k0.audit.*`**: Audit logs (durable, compliance)

## Key ADRs

- **ADR-0048**: K1 Internal Event Bus for Runtime Coordination - Core pub/sub architecture
- **ADR-0017**: SessionState 6-Section Design - Delta bus integration
- **ADR-0045**: K1 Event Bus Coordination - Agent coordination patterns
- **ADR-0049**: Fast/Smart Lane Router Policy - Message routing optimization
- **ADR-0014**: JSON for REST API (Dual Format) - API communication
- **ADR-0015**: WebSocket Binary Protocol - Real-time messaging
- **ADR-0016**: SSE Event Schemas (17 Types) - Server-sent events
- **ADR-0022**: K0 Bridge Bounded Batching - Bridge communication
- **ADR-0023**: Cursor-Based Turn Pagination - Efficient pagination
- **ADR-0034**: MCP Protocol for Tool Integration - Tool communication
- **ADR-0040**: WebSocket for Real-Time Chat - Chat protocols
- **ADR-0041**: REST API for Session Management - Session APIs
- **ADR-0042**: K0 SSE Event Streaming - Durable event streaming
- **ADR-0043**: SSE Topic Taxonomy - Event organization
- **ADR-0044**: K0 Bridge HTTP2 FlatBuffers - Bridge protocols
- **ADR-0046**: SSE WebSocket Bridge - Protocol bridging

## Interfaces

### Event Bus Interface

```python
class EventBus:
    async def publish(self, topic: str, message: FlatBuffersMessage) -> None:
        """Publish message to topic"""

    async def subscribe(self, topic_pattern: str, handler: Callable) -> Subscription:
        """Subscribe to topic pattern"""

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Unsubscribe from topic"""
```

### Delta Bus Interface

```python
class DeltaBus:
    async def send_delta(self, session_id: str, delta: StateDelta) -> None:
        """Send state delta (no aggregation, delegates to Concierge)"""
```

### Mailbox Router Interface

```python
class MailboxRouter:
    async def register(self, agent_id: str, mailbox: AgentMailbox) -> None:
        """Register agent mailbox"""

    async def send(self, message: MailboxMessage) -> None:
        """Route message to target mailbox"""

    async def get_mailbox(self, agent_id: str) -> AgentMailbox:
        """Get mailbox by agent ID"""
```

## Performance Characteristics

- **Event Bus Latency**: <2ms for pub/sub operations
- **Throughput**: 1000s events/sec for runtime coordination
- **Mailbox Routing**: <1ms for direct message delivery
- **Memory Footprint**: In-memory only, no persistence overhead
- **Backpressure**: Mailbox size limits prevent unbounded queues

## Fault Tolerance

- **Supervision**: Router monitors mailbox health and connectivity
- **Message Persistence**: Critical messages buffered during outages
- **Graceful Degradation**: Slow consumer detection and logging
- **Actor Isolation**: Failures don't cascade through message passing

## Security

- **Message Validation**: FlatBuffers schema validation for all messages
- **Access Control**: Capability tokens required for sensitive topics
- **Audit Trail**: All messages include trace IDs for observability
- **Privacy**: Message content respects privacy bands

## Testing

- **Unit Tests**: Isolated bus components with mock subscribers
- **Integration Tests**: End-to-end message routing and event handling
- **Performance Tests**: Latency and throughput benchmarks
- **Chaos Tests**: Network partition and message loss scenarios

## Dependencies

- `k1.contracts`: FlatBuffers message schemas
- `k1.supervision`: Health monitoring and failure detection
- `k1.config`: Event bus configuration and topic patterns
- `k1.observability`: Metrics and tracing integration

## Development Notes

- Event bus is K1-internal only (respects ADR-0001 K0/K1 separation)
- Use K0 SSE for durable events, K1 event bus for ephemeral coordination
- All messages are immutable FlatBuffers for zero-copy performance
- Mailbox router provides location transparency for distributed deployment
- Backpressure management prevents memory exhaustion from high-frequency events</content>
