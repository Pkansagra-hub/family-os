---
adr_number: 0019e
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: 'Phase 1 (Foundation)'
implementation_status: PLANNING
authors:
- K1 Architecture Team
title: SessionState Event Schema (8 Core Events)
affected_layers:
- layer2_orchestration
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.sessionstate.events
- k1.sessionstate.manager
- k1.bus.event_bus
concerns:
- architecture
- contracts
- observability
- reliability
propagation:
  affected_adrs:
  - ADR-0017
  - ADR-0017g
  - ADR-0018
  - ADR-0019
  - ADR-0045
  - ADR-0048
  affected_tests:
  - tests/k1/sessionstate/test_events.py
  - tests/k1/sessionstate/test_event_emission.py
  triggers:
  - Event schema version changes
  - New event types added
  - Event payload structure changes
  - Event topic naming changes
related_adrs:
- ADR-0017
- ADR-0017g
- ADR-0018
- ADR-0019
- ADR-0019a
- ADR-0020d
- ADR-0045
- ADR-0048
related_contracts:
- k1/contracts/schemas/events/sessionstate/mutation_requested.v1.json
- k1/contracts/schemas/events/sessionstate/mutation_approved.v1.json
- k1/contracts/schemas/events/sessionstate/mutation_rejected.v1.json
- k1/contracts/schemas/events/sessionstate/eviction_triggered.v1.json
- k1/contracts/schemas/events/sessionstate/eviction_completed.v1.json
- k1/contracts/schemas/events/sessionstate/emergency_activated.v1.json
- k1/contracts/schemas/events/sessionstate/emergency_resolved.v1.json
- k1/contracts/schemas/events/sessionstate/reconstruction_started.v1.json
related_diagrams: []
research_citations:
- 'Event Sourcing (Martin Fowler, 2005)'
- 'CloudEvents Specification (CNCF, 2024)'
- 'AsyncAPI 3.0 (Linux Foundation, 2024)'
superseded_by: []
supersedes: []
---

# ADR-0019e: SessionState Event Schema (8 Core Events)

**Status:** ACCEPTED
**Date:** 2025-11-03
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0019 (FlatBuffers SessionState Serialization)](0019.md)
**Category:** Contracts & Serialization - Event Schemas
**Related ADRs:**


- [ADR-0017 (SessionState 12-Section Design)](../03-layer2-orchestration/0017-sessionstate-6-section-design/0017.md)
- [ADR-0017g (Single-Writer Concurrency)](../03-layer2-orchestration/0017-sessionstate-6-section-design/0017g-single-writer-concurrency-pattern.md)
- [ADR-0018 (3-Tier Eviction Strategy)](../05-layer4-runtime/0018-3-tier-eviction-strategy/0018.md)
- [ADR-0048 (K1 Internal Event Bus)](../03-layer2-orchestration/0048-k1-internal-event-bus/)

---

## Context

### Problem Statement

SessionState operations (mutations, evictions, emergencies, reconstruction) need standardized events for:

1. **Audit Trail:** Track all state changes for debugging and compliance
2. **Coordination:** Enable sub-agents and services to react to state changes
3. **Observability:** Monitor SessionState health via event streams
4. **Integration:** Allow external systems to subscribe to state changes


Without formal event schemas:

- Events are ad-hoc and inconsistent
- Consumers break on schema changes
- No versioning strategy for evolution
- Debugging becomes impossible at scale

### Requirements

1. **Versioned Schemas:** All events have `.v1` suffix for evolution
2. **CloudEvents Compatible:** Follow CNCF CloudEvents structure
3. **JSON Schema Validation:** All events validated against schemas
4. **Topic Hierarchy:** Events organized by domain and action
5. **Trace Correlation:** All events include trace_id for distributed tracing

---

## Decision

We will define **8 core SessionState events** organized into 4 categories:

### Event Catalog

| Event | Topic | Category | Emitter | Trigger |
|-------|-------|----------|---------|---------|
| `sessionstate.mutation.requested.v1` | `sessionstate.mutation.requested` | Mutation | Sub-Agent | Sub-agent requests mutation via Delta Bus |
| `sessionstate.mutation.approved.v1` | `sessionstate.mutation.approved` | Mutation | Concierge | Mutation approved and applied |
| `sessionstate.mutation.rejected.v1` | `sessionstate.mutation.rejected` | Mutation | Concierge | Mutation rejected by MutationGuard |
| `sessionstate.eviction.triggered.v1` | `sessionstate.eviction.triggered` | Eviction | EvictionEngine | Eviction started due to pressure |
| `sessionstate.eviction.completed.v1` | `sessionstate.eviction.completed` | Eviction | EvictionEngine | Eviction finished successfully |
| `sessionstate.emergency.activated.v1` | `sessionstate.emergency.activated` | Emergency | SizeTracker | Emergency mode activated (>95% capacity) |
| `sessionstate.emergency.resolved.v1` | `sessionstate.emergency.resolved` | Emergency | SizeTracker | Emergency mode resolved (<90% capacity) |
| `sessionstate.reconstruction.started.v1` | `sessionstate.reconstruction.started` | Lifecycle | ReconstructionSLA | Session reconstruction from COLD tier |

### Common Event Envelope

All events follow CloudEvents envelope:

```json
{
  "specversion": "1.0",
  "type": "sessionstate.mutation.requested.v1",
  "source": "k1://sessionstate/manager",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "time": "2025-11-03T12:30:00.000Z",
  "datacontenttype": "application/json",
  "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
  "data": {
    // Event-specific payload
  }
}
```

---

## Event Schemas

### 1. sessionstate.mutation.requested.v1

**Purpose:** Sub-agent requests a state mutation via Delta Bus.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.mutation.requested.v1.json",
  "title": "SessionState Mutation Requested",
  "type": "object",
  "required": ["request_id", "requester_agent_id", "target_section", "operation", "timestamp_ms"],
  "properties": {
    "request_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for tracking this mutation request"
    },
    "requester_agent_id": {
      "type": "string",
      "description": "Agent ID requesting the mutation"
    },
    "target_section": {
      "type": "string",
      "enum": ["control", "beliefs_active", "beliefs_history", "scoreboard",
               "history_active", "history_recent", "clarifications",
               "affective_now", "narrative_active", "meta", "persona", "telemetry"],
      "description": "Target section for mutation"
    },
    "operation": {
      "type": "string",
      "description": "Operation to perform (e.g., 'add_fact', 'update_referent')"
    },
    "payload": {
      "type": "object",
      "description": "Operation-specific data"
    },
    "estimated_size_bytes": {
      "type": "integer",
      "minimum": 0,
      "description": "Estimated size change in bytes"
    },
    "priority": {
      "type": "integer",
      "enum": [0, 1, 2],
      "default": 0,
      "description": "Priority level: 0=normal, 1=high, 2=urgent"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

### 2. sessionstate.mutation.approved.v1

**Purpose:** Concierge approved and applied a mutation.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.mutation.approved.v1.json",
  "title": "SessionState Mutation Approved",
  "type": "object",
  "required": ["request_id", "section", "operation", "timestamp_ms"],
  "properties": {
    "request_id": {
      "type": "string",
      "format": "uuid",
      "description": "Original request ID"
    },
    "section": {
      "type": "string",
      "description": "Section that was mutated"
    },
    "operation": {
      "type": "string",
      "description": "Operation that was applied"
    },
    "size_before_bytes": {
      "type": "integer",
      "description": "Section size before mutation"
    },
    "size_after_bytes": {
      "type": "integer",
      "description": "Section size after mutation"
    },
    "latency_us": {
      "type": "integer",
      "description": "Mutation latency in microseconds"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

### 3. sessionstate.mutation.rejected.v1

**Purpose:** Concierge rejected a mutation request.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.mutation.rejected.v1.json",
  "title": "SessionState Mutation Rejected",
  "type": "object",
  "required": ["request_id", "reason", "reason_code", "timestamp_ms"],
  "properties": {
    "request_id": {
      "type": "string",
      "format": "uuid",
      "description": "Original request ID"
    },
    "reason_code": {
      "type": "string",
      "enum": ["NOT_WRITER", "SECTION_LOCKED", "SIZE_EXCEEDED",
               "NEVER_EVICT_VIOLATION", "INVALID_OPERATION", "PREFLIGHT_FAILED"],
      "description": "Machine-readable rejection reason"
    },
    "reason": {
      "type": "string",
      "description": "Human-readable rejection reason"
    },
    "section": {
      "type": "string",
      "description": "Target section that was rejected"
    },
    "available_kb": {
      "type": "number",
      "description": "Available capacity in KB (if SIZE_EXCEEDED)"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

### 4. sessionstate.eviction.triggered.v1

**Purpose:** Eviction process started due to memory pressure.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.eviction.triggered.v1.json",
  "title": "SessionState Eviction Triggered",
  "type": "object",
  "required": ["eviction_id", "tier", "trigger_reason", "pressure_level", "timestamp_ms"],
  "properties": {
    "eviction_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for this eviction operation"
    },
    "tier": {
      "type": "integer",
      "enum": [1, 2, 3],
      "description": "Eviction tier: 1=soft, 2=hard, 3=OOM"
    },
    "trigger_reason": {
      "type": "string",
      "enum": ["SIZE_THRESHOLD", "TURN_COMPLETION", "IDLE_TIMEOUT", "OOM_PREVENTION"],
      "description": "What triggered the eviction"
    },
    "pressure_level": {
      "type": "string",
      "enum": ["GREEN", "AMBER", "RED", "CRITICAL"],
      "description": "Current pressure level"
    },
    "current_size_kb": {
      "type": "number",
      "description": "Current total size in KB"
    },
    "target_size_kb": {
      "type": "number",
      "description": "Target size after eviction in KB"
    },
    "sections_targeted": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Sections targeted for eviction"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

### 5. sessionstate.eviction.completed.v1

**Purpose:** Eviction process completed successfully.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.eviction.completed.v1.json",
  "title": "SessionState Eviction Completed",
  "type": "object",
  "required": ["eviction_id", "bytes_evicted", "duration_ms", "timestamp_ms"],
  "properties": {
    "eviction_id": {
      "type": "string",
      "format": "uuid",
      "description": "Eviction ID from triggered event"
    },
    "bytes_evicted": {
      "type": "integer",
      "description": "Total bytes evicted"
    },
    "sections_evicted": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "section": {"type": "string"},
          "bytes_evicted": {"type": "integer"},
          "items_evicted": {"type": "integer"}
        }
      },
      "description": "Per-section eviction details"
    },
    "destination": {
      "type": "string",
      "enum": ["LOCAL_COLD", "K0_WARM", "DISCARDED"],
      "description": "Where evicted data went"
    },
    "size_before_kb": {
      "type": "number",
      "description": "Total size before eviction"
    },
    "size_after_kb": {
      "type": "number",
      "description": "Total size after eviction"
    },
    "duration_ms": {
      "type": "integer",
      "description": "Eviction duration in milliseconds"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

### 6. sessionstate.emergency.activated.v1

**Purpose:** Emergency mode activated (capacity > 95%).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.emergency.activated.v1.json",
  "title": "SessionState Emergency Activated",
  "type": "object",
  "required": ["session_id", "capacity_percent", "action_taken", "timestamp_ms"],
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Affected session ID"
    },
    "capacity_percent": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Current capacity utilization"
    },
    "hot_size_kb": {
      "type": "number",
      "description": "HOT tier size in KB"
    },
    "warm_size_kb": {
      "type": "number",
      "description": "WARM tier size in KB"
    },
    "total_size_kb": {
      "type": "number",
      "description": "Total size in KB"
    },
    "action_taken": {
      "type": "string",
      "enum": ["AGGRESSIVE_EVICTION", "TURN_REJECTION", "SESSION_PAUSE"],
      "description": "Immediate action taken"
    },
    "eviction_id": {
      "type": "string",
      "format": "uuid",
      "description": "Associated eviction ID if applicable"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

### 7. sessionstate.emergency.resolved.v1

**Purpose:** Emergency mode resolved (capacity < 90%).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.emergency.resolved.v1.json",
  "title": "SessionState Emergency Resolved",
  "type": "object",
  "required": ["session_id", "capacity_percent", "resolution_method", "timestamp_ms"],
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Affected session ID"
    },
    "capacity_percent": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Current capacity utilization"
    },
    "peak_capacity_percent": {
      "type": "number",
      "description": "Peak capacity during emergency"
    },
    "duration_seconds": {
      "type": "integer",
      "description": "How long emergency lasted"
    },
    "bytes_recovered": {
      "type": "integer",
      "description": "Bytes freed during emergency"
    },
    "resolution_method": {
      "type": "string",
      "enum": ["EVICTION", "TURN_COMPLETION", "TIMEOUT", "MANUAL"],
      "description": "How emergency was resolved"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

### 8. sessionstate.reconstruction.started.v1

**Purpose:** Session reconstruction from COLD tier started.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sessionstate.reconstruction.started.v1.json",
  "title": "SessionState Reconstruction Started",
  "type": "object",
  "required": ["session_id", "reconstruction_id", "source", "sections_requested", "timestamp_ms"],
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Session being reconstructed"
    },
    "reconstruction_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique ID for this reconstruction"
    },
    "source": {
      "type": "string",
      "enum": ["LOCAL_COLD", "K0_WARM", "K0_COLD"],
      "description": "Source tier for reconstruction"
    },
    "sections_requested": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Sections requested for hydration"
    },
    "trigger_reason": {
      "type": "string",
      "enum": ["SESSION_RESUME", "CACHE_MISS", "FAILOVER", "MANUAL"],
      "description": "What triggered reconstruction"
    },
    "sla_target_ms": {
      "type": "integer",
      "description": "SLA target for this reconstruction"
    },
    "timestamp_ms": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  }
}
```

---

## Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SESSIONSTATE EVENT FLOW                                   │
│                                                                              │
│  ┌─────────────┐                                                            │
│  │  Sub-Agent  │──┐                                                         │
│  └─────────────┘  │ mutation.requested.v1                                   │
│  ┌─────────────┐  │                                                         │
│  │  Sub-Agent  │──┼──────────────────────────────┐                          │
│  └─────────────┘  │                              ▼                          │
│  ┌─────────────┐  │                    ┌─────────────────┐                  │
│  │  Sub-Agent  │──┘                    │   CONCIERGE     │                  │
│  └─────────────┘                       │   (Writer)      │                  │
│                                        └─────────────────┘                  │
│                                                 │                           │
│                              ┌──────────────────┼──────────────────┐        │
│                              ▼                  ▼                  ▼        │
│                    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│                    │  approved   │    │  rejected   │    │  eviction   │   │
│                    │    .v1      │    │    .v1      │    │ triggered   │   │
│                    └─────────────┘    └─────────────┘    └─────────────┘   │
│                                                                  │          │
│                                                                  ▼          │
│                    ┌─────────────┐                     ┌─────────────┐     │
│                    │ emergency   │◄────────────────────│  eviction   │     │
│                    │ activated   │                     │ completed   │     │
│                    └─────────────┘                     └─────────────┘     │
│                           │                                                 │
│                           ▼                                                 │
│                    ┌─────────────┐                     ┌─────────────┐     │
│                    │ emergency   │                     │reconstruction│    │
│                    │ resolved    │                     │  started    │     │
│                    └─────────────┘                     └─────────────┘     │
│                                                                             │
│  TOPIC HIERARCHY:                                                          │
│  sessionstate.mutation.requested                                           │
│  sessionstate.mutation.approved                                            │
│  sessionstate.mutation.rejected                                            │
│  sessionstate.eviction.triggered                                           │
│  sessionstate.eviction.completed                                           │
│  sessionstate.emergency.activated                                          │
│  sessionstate.emergency.resolved                                           │
│  sessionstate.reconstruction.started                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Consequences

### Positive

1. **Type Safety:** JSON Schema validation catches malformed events
2. **Versioning:** `.v1` suffix enables non-breaking evolution
3. **Observability:** Full event stream for debugging and monitoring
4. **Decoupling:** Consumers don't need direct SessionState access
5. **Audit Trail:** Complete history of all state changes

### Negative

1. **Schema Maintenance:** 8 schemas to keep in sync
2. **Event Volume:** High mutation rate → high event volume
3. **Storage Cost:** Event logs require storage

### Mitigations

| Concern | Mitigation |
|---------|------------|
| Schema drift | CI validation against contract files |
| Event volume | Batch mutations, sampling for telemetry |
| Storage cost | Retention policies (24h hot, 30d cold) |

---

## Contract File Locations

```
k1/contracts/schemas/events/sessionstate/
├── mutation_requested.v1.json
├── mutation_approved.v1.json
├── mutation_rejected.v1.json
├── eviction_triggered.v1.json
├── eviction_completed.v1.json
├── emergency_activated.v1.json
├── emergency_resolved.v1.json
└── reconstruction_started.v1.json
```

---

## Final Decision

**SessionState Event Schema (8 Core Events)** is ACCEPTED.

### Event Summary

| Event | Purpose | Emitter |
|-------|---------|---------|
| `mutation.requested.v1` | Sub-agent mutation request | Sub-Agent |
| `mutation.approved.v1` | Mutation applied | Concierge |
| `mutation.rejected.v1` | Mutation rejected | Concierge |
| `eviction.triggered.v1` | Eviction started | EvictionEngine |
| `eviction.completed.v1` | Eviction finished | EvictionEngine |
| `emergency.activated.v1` | Emergency mode on | SizeTracker |
| `emergency.resolved.v1` | Emergency mode off | SizeTracker |
| `reconstruction.started.v1` | Reconstruction began | ReconstructionSLA |

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| JSON Schema files | PLANNING | 8 schema files |
| Python event classes | PLANNING | Dataclasses with validation |
| Event emission hooks | PLANNING | Integration with SessionStateManager |
| Tests | PLANNING | Schema validation + emission tests |
