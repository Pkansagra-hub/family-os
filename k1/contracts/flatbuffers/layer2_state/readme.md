# FlatBuffers Contracts - Layer 2 (State & Persistence)

**Source ADRs:** ADR-0001b, ADR-0010, ADR-0011

## Overview

This directory contains FlatBuffers schema contracts for Layer 2 (State & Persistence) components: SessionState, Memory Manager, Receipt System, and K0 Bridge.

## Layer 2 Components

Layer 2 manages persistent state, memory, and communication with the K0 kernel.

## Contracts Included

### 1. SessionState Schemas
- `SessionState.fbs` - Complete 6-section structure
- `BeliefsSection.fbs` - Beliefs section
- `ScoreboardSection.fbs` - Scoreboard section
- `ControlSection.fbs` - Control section
- `PersonaSection.fbs` - Persona section
- `MultimodalSection.fbs` - Multimodal section
- `MetaSection.fbs` - Meta section
- `StateDelta.fbs` - Incremental state update

### 2. Memory Manager Schemas
- `MemoryEntry.fbs` - Individual memory entry
- `MemoryMetadata.fbs` - Memory metadata
- `RecallQuery.fbs` - Memory recall query
- `RecallResult.fbs` - Recall results

### 3. Receipt System Schemas
- `Receipt.fbs` - Receipt for K0 operations
- `ReceiptVerification.fbs` - Receipt verification

### 4. K0 Bridge Schemas
- `K0Request.fbs` - Generic K0 request
- `K0Response.fbs` - Generic K0 response
- `PortMessage.fbs` - Port-specific message wrapper

## Schema Example: SessionState

```flatbuffers
// SessionState.fbs
namespace k1.sessionstate;

table BeliefsSection {
  current_plan: [ubyte];  // Serialized Plan
  context: [ubyte];        // Retrieved context
  user_intent: string;
  conversation_history: [string];
}

table ControlSection {
  active_agents: [string];
  task_queue: [ubyte];
  protocol_states: [ubyte];
}

table SessionState {
  session_id: string (required);
  created_at: int64;
  last_updated: int64;

  beliefs: BeliefsSection;
  scoreboard: ScoreboardSection;
  control: ControlSection;
  persona: PersonaSection;
  multimodal: MultimodalSection;
  meta: MetaSection;

  version: uint32;
  trace_id: string;
}

root_type SessionState;
```

## Delta Format

```flatbuffers
// StateDelta.fbs
namespace k1.sessionstate;

enum DeltaType: byte {
  UPDATE = 0,
  DELETE = 1,
  APPEND = 2
}

enum Section: byte {
  BELIEFS = 0,
  SCOREBOARD = 1,
  CONTROL = 2,
  PERSONA = 3,
  MULTIMODAL = 4,
  META = 5
}

table StateDelta {
  session_id: string (required);
  section: Section;
  delta_type: DeltaType;
  data: [ubyte];  // Compressed delta
  version: uint32;
  timestamp: int64;
  trace_id: string;
}

root_type StateDelta;
```

## Performance Characteristics

```yaml
performance:
  sessionstate_serialization_us: 500
  sessionstate_deserialization_us: 100
  delta_serialization_us: 50
  delta_deserialization_us: 20

  size_budgets:
    sessionstate_kb: 64
    delta_kb: 4
```

## Related Contracts

- SessionState: `../../sessionstate/`
- Storage: `../../storage/`
- K0 Bridge: `../../k0_bridge/`

---

**Last Updated:** 2025-10-13
