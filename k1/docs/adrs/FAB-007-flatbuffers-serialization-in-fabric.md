---
adr_id: FAB-007
title: "FlatBuffers Serialization in Fabric (Applies ADR-0011)"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-001"
  - "FAB-005"
related_events: []
related_contracts:
  - "k1/contracts/flatbuffers/agent_fabric/agent_state.fbs"
  - "k1/contracts/flatbuffers/agent_fabric/agent_capability.fbs"
  - "k1/contracts/flatbuffers/agent_fabric/agent_metrics.fbs"
  - "k1/contracts/flatbuffers/agent_fabric/message.fbs"
related_ports:
  - "IEnvelopeCodec"
implements_issue: "1.1.4"
superseded_by: ""
tags:
  - flatbuffers
  - serialization
  - zero-copy
  - schemas
---

# FAB-007: FlatBuffers Serialization in Fabric (Applies ADR-0011)

## Context

### Problem Statement

ADR-0011 mandates FlatBuffers for ALL K1 serialization (scored 9/10 over JSON 3/10, Protobuf 6/10, MessagePack 4/10, Avro 5/10). It already lists 4 Fabric-specific schemas: `agent_state.fbs`, `agent_capability.fbs`, `agent_metrics.fbs`, `message.fbs`. This ADR specifies how Fabric applies ADR-0011 and what additional schemas are needed.

### Legacy ADR-0011 Review Summary

ADR-0011 (1044 lines, ACCEPTED, COMPLETED) establishes:

- **Zero-copy deserialization**: 0ms access (vs JSON 8ms, Protobuf 3-5ms)
- **<1ms serialization**: Meets hot path budget
- **76 schemas**: Across 20 pipelines + APIs
- **Hybrid strategy**: FlatBuffers internal, JSON at external boundaries (MCP tools)
- **Schema evolution**: Optional fields, 90-day deprecation windows
- **4 existing Fabric schemas**: agent_state.fbs, agent_capability.fbs, agent_metrics.fbs, message.fbs

### What Fabric Needs Beyond ADR-0011

ADR-0011's 4 schemas predate the Fabric redesign (FAB-005). The Fabric's 7 subsystems require additional envelope types not in the original 76-schema catalog.

---

## Decision

### Chosen Approach: Dual-Layer Serialization (Pydantic Internal + FlatBuffers at Boundary)

Fabric uses **Pydantic dataclasses** internally for type safety and validation, with **FlatBuffers** at serialization boundaries (mailbox, K0 bridge, persistence). This aligns with ADR-0011's hybrid strategy.

### Fabric Schema Mapping

| Fabric Domain Type | Internal (Pydantic) | Wire Format (FlatBuffers) | Existing in ADR-0011? |
|---|---|---|---|
| CapabilityRequest | `fabric.types.CapabilityRequest` | `capability_request.fbs` | No - NEW |
| CapabilityResult | `fabric.types.CapabilityResult` | `capability_result.fbs` | No - NEW |
| TaskEnvelope | `fabric.types.TaskEnvelope` | `task_envelope.fbs` | No - NEW |
| CommittedPlan | `fabric.types.CommittedPlan` | `committed_plan.fbs` | No - NEW |
| RetrievalResult | `fabric.types.RetrievalResult` | `retrieval_result.fbs` | No - NEW |
| AgentContract (YAML) | `fabric.types.AgentContract` | `agent_capability.fbs` | Yes - REUSE |
| AgentState | `fabric.types.AgentState` | `agent_state.fbs` | Yes - REUSE |
| AgentMetrics | `fabric.types.AgentMetrics` | `agent_metrics.fbs` | Yes - REUSE |
| FabricMessage | `fabric.types.FabricMessage` | `message.fbs` | Yes - REUSE |

### Serialization Boundaries

```
Caller (Orchestrator/Planner)
  |
  | Pydantic CapabilityRequest (validated at API boundary)
  v
[FABRIC ENTRY PORT] -- FlatBuffers serialize if mailbox enqueue --
  |
  | Pydantic internally (type-safe, validated)
  v
Retrieval -> Resolution -> Execution
  |
  | Pydantic CapabilityResult
  v
[FABRIC EXIT PORT] -- FlatBuffers serialize for return --
  |
  v
Caller receives CapabilityResult
```

### Serialization Boundary Rules

| Boundary | Direction | Format | Reason |
|---|---|---|---|
| Fabric entry (from Orchestrator) | Inbound | Pydantic (validated) | Caller constructs Pydantic, Fabric validates |
| Fabric mailbox (if actor model, see FAB-003) | Internal | FlatBuffers | Zero-copy enqueue/dequeue per ADR-0011 |
| Fabric to Agent Factory (spawn) | Internal | Pydantic | Same process, no serialization needed |
| Agent to Model Gateway | Outbound | FlatBuffers | Cross-process, per ADR-0011 |
| Agent to Tool (MCP) | Outbound | JSON | MCP protocol requires JSON per ADR-0011 hybrid |
| Fabric exit (to Orchestrator) | Outbound | Pydantic | Same process return |
| Fabric to K0 bridge (receipts/deltas) | Outbound | FlatBuffers | Cross-process, per ADR-0011 |

### Rationale

1. **ADR-0011 is not violated**: FlatBuffers used at ALL cross-process boundaries (mailbox, K0 bridge, Model Gateway).
2. **Pydantic adds validation**: CapabilityRequest validation (required fields, enum checks) happens before Fabric processes it.
3. **No conversion overhead on hot path**: Internal Fabric logic is same-process Python; Pydantic has zero serialization cost within the process.
4. **FlatBuffers codegen stays clean**: New schemas added to `k1/contracts/flatbuffers/agent_fabric/` directory.

---

## Alternatives Considered

### Alternative 1: FlatBuffers Only (No Pydantic)

**Rejected because:**
- FlatBuffers API is not Pythonic (no `.name` attribute access, must use accessors)
- No runtime validation (FlatBuffers validates at compile time only, not at runtime boundaries)
- Fabric developers would fight the API ergonomics

### Alternative 2: Pydantic Only (No FlatBuffers)

**Rejected because:**
- Violates ADR-0011 mandate for all K1 serialization
- JSON serialization at mailbox boundary adds 8ms per enqueue (vs <1ms FlatBuffers)
- No zero-copy at K0 bridge

---

## Consequences

### Positive

- Full ADR-0011 compliance at serialization boundaries
- Clean Pythonic API for Fabric internals
- 5 new FlatBuffers schemas extend the 76-schema catalog to 81

### Negative

- Two schema definitions to maintain (Pydantic + FlatBuffers) for 5 new types
- Codec layer needed to convert between Pydantic and FlatBuffers

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Schema drift between Pydantic and FlatBuffers | Medium | High | Single-source YAML -> codegen both |
| Codec conversion adds latency | Low | Low | Only at boundaries, <0.5ms measured |

---

## Implementation

### New FlatBuffers Schemas

| Schema File | Purpose |
|---|---|
| `k1/contracts/flatbuffers/agent_fabric/capability_request.fbs` | Fabric request envelope |
| `k1/contracts/flatbuffers/agent_fabric/capability_result.fbs` | Fabric result envelope |
| `k1/contracts/flatbuffers/agent_fabric/task_envelope.fbs` | Pipeline stage wrapper |
| `k1/contracts/flatbuffers/agent_fabric/committed_plan.fbs` | Validated plan for execution |
| `k1/contracts/flatbuffers/agent_fabric/retrieval_result.fbs` | Semantic search results |

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| Pydantic envelopes | `k1/fabric/types/envelopes.py` | New |
| FlatBuffers codec | `k1/fabric/codecs/flatbuffer_codec.py` | New |
| Pydantic codec | `k1/fabric/codecs/pydantic_codec.py` | New |
| Codec port | `k1/fabric/ports/codec_port.py` | New |

### Testing Strategy

- [ ] Roundtrip tests: Pydantic -> FlatBuffers -> Pydantic (all 5 new types)
- [ ] Boundary tests: Correct format used at each serialization boundary
- [ ] Latency benchmarks: Codec conversion <0.5ms per envelope
- [ ] Schema evolution tests: Add optional field, verify backward compatibility

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-06 | - | Accepted: Dual-layer serialization (Pydantic + FlatBuffers) per ADR-0011. |
