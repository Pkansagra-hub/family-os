# K0 SSE Event Streaming Contracts

**Source ADRs:** ADR-0042, ADR-0042a-e, ADR-0043, ADR-0043a-d

## Overview

This directory contains contracts for K0 Server-Sent Events (SSE) streaming, which enables real-time event delivery from K0 to K1 and frontend clients.

## Contracts Included

### 1. Event Production Contract (`event_production.yaml`)
- **Source:** ADR-0042a
- K0 event production pipeline
- Event schema definitions
- Event lifecycle management

### 2. Event Consumption Contract (`event_consumption.yaml`)
- **Source:** ADR-0042b
- K1 event consumption patterns
- Subscription management
- Event filtering rules

### 3. Reconnection & Replay Contract (`reconnection_replay.yaml`)
- **Source:** ADR-0042c
- Reconnection strategies
- Event replay from cursor position
- Connection state management

### 4. Backpressure & Persistence Contract (`backpressure_persistence.yaml`)
- **Source:** ADR-0042d
- Backpressure handling rules
- Event persistence requirements
- Queue management

### 5. Device Storage Tiers Contract (`device_storage.yaml`)
- **Source:** ADR-0042e
- Hot/Warm/Cold storage tiers for SSE events
- Storage allocation policies
- Retention rules per tier

### 6. Topic Hierarchy Contract (`topic_hierarchy.yaml`)
- **Source:** ADR-0043a
- SSE topic naming conventions
- Topic hierarchy structure
- Topic ACL rules

### 7. Topic Subscription Contract (`topic_subscription.yaml`)
- **Source:** ADR-0043b
- Subscription request format
- Subscription lifecycle
- Filtering patterns

### 8. Topic Routing Contract (`topic_routing.yaml`)
- **Source:** ADR-0043c
- Event routing algorithms
- Topic-based filtering
- Wildcard subscription rules

### 9. Topic ACL Contract (`topic_acl.yaml`)
- **Source:** ADR-0043d
- Access control for topics
- Privacy band enforcement on topics
- Authorization rules

## Key Specifications

### Event Schema
```yaml
event:
  id: string                 # Unique event ID
  topic: string              # Topic path (e.g., "session.turn.completed")
  timestamp: iso8601         # Event timestamp
  payload: object            # Event-specific data
  trace_id: string           # cognitive_trace_id for correlation
```

### Topic Naming Convention
```
<scope>.<entity>.<action>
Examples:
  - session.turn.started
  - session.turn.completed
  - agent.hired
  - tool.called
```

### Reconnection Strategy
- Last-Event-ID header for cursor-based replay
- 60-second buffering window for replay
- Exponential backoff for reconnection

## Usage Examples

See `examples/` directory for implementation examples.

## Related Contracts

- K0 Bridge Contracts: `../k0_bridge/`
- API Contracts: `../api/sse/`
- Observability Contracts: `../observability/`

---

**Last Updated:** 2025-10-13
