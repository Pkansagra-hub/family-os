# FlatBuffers Contracts - Layer 1 (Kernel)

**Source ADRs:** ADR-0001b, ADR-0001c

## Overview

This directory contains FlatBuffers schema contracts for Layer 1 (Kernel) components: Agent Fabric, Orchestrator Core, Planner, Protocol Monitor, and Learning Loop.

## Layer 1 Components

Layer 1 is the core kernel layer responsible for agentic orchestration, planning, protocol validation, and adaptive learning.

## Contracts Included

### 1. Agent Fabric Schemas
- `AgentState.fbs` - Agent lifecycle state (6 states)
- `AgentCapabilities.fbs` - Capability definitions
- `HireRequest.fbs` - Agent hiring request
- `HireResponse.fbs` - Agent hiring response

### 2. Orchestrator Schemas
- `TaskAnnouncement.fbs` - Task announcement for bidding
- `BidSubmission.fbs` - Agent bid submission
- `TaskAssignment.fbs` - Task assignment to agent
- `TaskCompletion.fbs` - Task completion result

### 3. Planner Schemas
- `PlanSketch.fbs` - High-level plan from LLM
- `ExpandedPlan.fbs` - Detailed plan with steps
- `PlanValidation.fbs` - Validation result
- `CommittedPlan.fbs` - Final committed plan

### 4. Protocol Monitor Schemas
- `ProtocolState.fbs` - Protocol FSM state
- `ProtocolViolation.fbs` - Protocol violation event
- `ProtocolTimeout.fbs` - Timeout event

### 5. Learning Loop Schemas
- `FeedbackSignal.fbs` - User feedback (explicit/implicit)
- `LearningDelta.fbs` - Configuration delta
- `DriftDetection.fbs` - Drift detection result

## Schema Standards

```yaml
schema_standards:
  naming_convention: PascalCase
  field_naming: snake_case
  version_field: required in all schemas

  common_fields:
    - trace_id: string (cognitive_trace_id)
    - timestamp: int64 (unix_ms)
    - version: uint16 (schema version)

  performance:
    serialization_target_us: 100
    deserialization_target_us: 100
    zero_copy: true
```

## Example Schema

```flatbuffers
// AgentState.fbs
namespace k1.agent_fabric;

enum AgentStateEnum: byte {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2,
  IDLE = 3,
  DRAINING = 4,
  TERMINATED = 5
}

table AgentState {
  agent_id: string (required);
  state: AgentStateEnum;
  capabilities: [string];
  memory_mb: uint32;
  trace_id: string;
  timestamp: int64;
  version: uint16 = 1;
}

root_type AgentState;
```

## Usage

```python
# Serialize
from k1.agent_fabric import AgentState
import flatbuffers

builder = flatbuffers.Builder(1024)
agent_state = AgentState.Create(
    builder,
    agent_id="agent-123",
    state=AgentStateEnum.ACTIVE,
    capabilities=["PLANNING", "TOOL_CALL"],
    memory_mb=500
)
builder.Finish(agent_state)
serialized = builder.Output()

# Deserialize (zero-copy)
agent = AgentState.GetRootAs(serialized, 0)
print(agent.AgentId())  # "agent-123"
```

## Related Contracts

- Agent Lifecycle: `../../agent_lifecycle/`
- Orchestration: `../../orchestration/`
- Planning: `../../planning/`
- Protocols: `../../protocols/`

---

**Last Updated:** 2025-10-13
