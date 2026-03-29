---
adr_id: FAB-001
title: "Core Envelope Schemas"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-003"
  - "FAB-004"
  - "FAB-007"
  - "FAB-009"
related_events:
  - "k1.fabric.capability.requested.v1"
  - "k1.fabric.capability.resolved.v1"
  - "k1.fabric.capability.completed.v1"
related_contracts:
  - "k1/contracts/flatbuffers/agent_fabric/capability_request.fbs"
  - "k1/contracts/flatbuffers/agent_fabric/capability_result.fbs"
  - "k1/contracts/flatbuffers/agent_fabric/task_envelope.fbs"
  - "k1/contracts/flatbuffers/agent_fabric/committed_plan.fbs"
  - "k1/contracts/flatbuffers/agent_fabric/retrieval_result.fbs"
related_ports:
  - "IEnvelopeCodec"
implements_issue: "1.1.7"
superseded_by: ""
tags:
  - envelope
  - schema
  - serialization
  - foundation
---

# FAB-001: Core Envelope Schemas

## Context

### Problem Statement

The Capability Fabric requires domain-agnostic envelope types that flow through every subsystem: CapabilityRequest, CapabilityResult, TaskEnvelope, CommittedPlan, RetrievalResult. A design decision is needed on the type system: Pydantic dataclasses vs FlatBuffers vs both.

### Current Situation

- ADR-0011 established FlatBuffers for ALL K1 serialization (scored 9/10)
- fabric_discussion.md Section 14 outlines envelope requirements
- No K1 Fabric envelope types exist yet
- All subsystems in M2-M8 depend on this decision
- FAB-007 decided dual-layer serialization (Pydantic internal + FlatBuffers at boundary)

### Constraints

- Must be domain-agnostic (not tied to specific capability types)
- Must support efficient serialization for inter-agent messaging
- Must be versionable (envelope schema versioning)
- Pydantic validation required at API boundaries
- Must carry WFQ priority for scheduling (FAB-009)

### Requirements

- CapabilityRequest: intent + parameters + metadata + wfq_priority
- CapabilityResult: result + status + metrics + execution_time_ms
- TaskEnvelope: wraps requests through pipeline stages
- CommittedPlan: validated plan ready for execution (list of steps with tools_granted)
- RetrievalResult: semantic search results with similarity scores

---

## Decision

### Chosen Approach: Pydantic Dataclasses with FlatBuffers Codec

Per FAB-007 decision, envelopes are **Pydantic `@dataclass` types** internally, with a FlatBuffers codec at serialization boundaries (mailbox, K0 bridge). This gives rich validation where callers construct requests, and zero-copy where performance matters.

### Core Envelope Definitions

```python
# k1/fabric/types/envelopes.py
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional
import uuid


class RequestStatus(Enum):
    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class WFQPriority(Enum):
    URGENT = auto()      # <=50ms budget
    REALTIME = auto()    # <=150ms budget
    INTERACTIVE = auto() # <=300ms budget
    BACKGROUND = auto()  # <=5s budget


@dataclass(frozen=True)
class CapabilityRequest:
    """
    Domain-agnostic request to invoke a capability.

    This is the PRIMARY input to the Fabric pipeline.
    Callers (Orchestrator, Planner) construct this; Fabric processes it.
    """
    intent: str                          # Natural language or structured intent
    parameters: dict[str, Any]           # Capability-specific params
    wfq_priority: WFQPriority            # Scheduling priority (FAB-009)
    deadline_ms: int                     # Absolute deadline from priority class
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""                 # For SessionState reader scoping
    plan_id: Optional[str] = None        # If part of a CommittedPlan
    step_id: Optional[str] = None        # Step within the plan
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityResult:
    """
    Domain-agnostic result from capability execution.

    Returned by Fabric to the caller after the full pipeline completes.
    """
    request_id: str                      # Matches CapabilityRequest.trace_id
    status: RequestStatus                # COMPLETED or FAILED
    result: Any                          # Capability-specific result payload
    provider_name: str                   # Which provider executed this
    execution_time_ms: float             # Wall-clock time for full pipeline
    retrieval_time_ms: float             # Time spent in Retrieval subsystem
    resolution_time_ms: float            # Time spent in Resolution subsystem
    agent_time_ms: float                 # Time spent in Agent execution
    error: Optional[str] = None          # Error message if FAILED
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def success(cls, request_id: str, result: Any, provider: str, **timing) -> "CapabilityResult":
        return cls(request_id=request_id, status=RequestStatus.COMPLETED,
                   result=result, provider_name=provider, **timing)

    @classmethod
    def failure(cls, request_id: str, error: str, provider: str = "", **timing) -> "CapabilityResult":
        return cls(request_id=request_id, status=RequestStatus.FAILED,
                   result=None, provider_name=provider, error=error, **timing)


@dataclass(frozen=True)
class RetrievalResult:
    """
    Results from SemanticIndex search.

    Contains top-K candidates with similarity scores.
    """
    query_intent: str                    # Original intent searched
    candidates: list["RetrievalCandidate"]  # Ranked by similarity
    search_time_ms: float                # FAISS query time
    index_size: int                      # Number of contracts in index
    embedding_model: str = "ultrabert-v4.0.0"


@dataclass(frozen=True)
class RetrievalCandidate:
    """A single candidate from semantic retrieval."""
    contract_name: str                   # e.g., "calendar.create_event"
    similarity_score: float              # Cosine similarity [0.0, 1.0]
    contract_description: str            # Human-readable description
    capabilities: list[str]              # Capability slugs
    provider_type: str                   # "tool", "agent", "composite"


@dataclass(frozen=True)
class CommittedPlan:
    """
    A validated plan ready for execution by the Fabric.

    Created by Planner, validated by Orchestrator, executed by Fabric.
    Each step specifies which tools are granted to the spawned agent.
    """
    plan_id: str
    session_id: str
    steps: list["PlanStep"]
    wfq_priority: WFQPriority
    total_deadline_ms: int               # Budget for entire plan


@dataclass(frozen=True)
class PlanStep:
    """A single step in a CommittedPlan."""
    step_id: str
    intent: str                          # What this step accomplishes
    tools_granted: list[str]             # Capability names scoped to this step (FAB-006)
    agent_template: str                  # YAML template name for Agent Factory
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)  # step_ids this depends on


@dataclass
class TaskEnvelope:
    """
    Mutable wrapper that carries a CapabilityRequest through pipeline stages.

    Accumulates metadata as it passes through Retrieval -> Resolution -> Execution.
    """
    request: CapabilityRequest
    retrieval_result: Optional[RetrievalResult] = None
    resolved_provider: Optional[str] = None
    resolved_at_ms: Optional[float] = None
    execution_started_at_ms: Optional[float] = None
    stage: str = "created"               # created -> retrieved -> resolved -> executing -> completed
```

### Immutability Rules

| Type | Frozen? | Rationale |
|---|---|---|
| CapabilityRequest | Yes | Input is immutable; never modified after construction |
| CapabilityResult | Yes | Output is immutable; constructed once by provider |
| RetrievalResult | Yes | Search results are immutable snapshots |
| RetrievalCandidate | Yes | Individual candidate is immutable |
| CommittedPlan | Yes | Plan is committed; steps don't change during execution |
| PlanStep | Yes | Step is immutable after planning phase |
| TaskEnvelope | No | Accumulates metadata through pipeline stages |

### Rationale

1. **Pydantic frozen dataclasses**: Prevent accidental mutation of requests/results flowing between subsystems.
2. **TaskEnvelope is mutable**: It's the ONE type that accumulates state as it moves through the pipeline (Retrieval adds candidates, Resolution adds provider, Execution adds timing).
3. **WFQ priority embedded in request**: Per FAB-009, priority propagates through the pipeline without external lookup.
4. **Factory methods on CapabilityResult**: `success()` and `failure()` constructors prevent invalid state (e.g., COMPLETED with error, or FAILED with result).

---

## Alternatives Considered

### Alternative 1: Pure Pydantic BaseModel (not dataclass)

**Description:** Use Pydantic BaseModel for all envelope types.

**Pros:**
- Rich validation at boundaries
- Native Python ergonomics
- Easy to extend and version

**Cons:**
- BaseModel overhead (~2x slower construction than frozen dataclass)
- Not hashable by default (need model_config)
- Heavier than needed for internal types

**Rejected because:** Frozen dataclasses are sufficient for internal types. BaseModel validation is overkill when callers are trusted K1 components. FAB-007 handles the serialization story separately.

### Alternative 2: FlatBuffers Only

**Description:** Use FlatBuffers schemas for all envelopes.

**Pros:**
- Zero-copy deserialization
- Schema evolution support
- Matches ADR-0011

**Cons:**
- Less Pythonic API (accessor methods, not attributes)
- Harder to add validation
- No factory methods or computed properties

**Rejected because:** FlatBuffers API is painful for Python developers. Per FAB-007, FlatBuffers is used at serialization boundaries only. Internal code uses Pydantic.

### Alternative 3: Dual Layer (BaseModel + FlatBuffers with codegen)

**Description:** Define schemas in YAML, codegen both Pydantic BaseModel and FlatBuffers from single source.

**Pros:**
- Single source of truth
- No schema drift risk

**Cons:**
- Codegen toolchain complexity
- Generated code is less readable
- Debugging generated code is harder

**Rejected because:** Over-engineering for initial implementation. Can migrate to codegen in M4+ if schema drift becomes a real problem. Start with hand-written frozen dataclasses.

---

## Consequences

### Positive

- 7 well-defined types shared across ALL Fabric subsystems
- Frozen immutability prevents accidental corruption
- WFQ priority propagation built into the type system
- Factory methods on CapabilityResult enforce valid state transitions

### Negative

- Hand-written Pydantic + FlatBuffers means two definitions (mitigated by FAB-007 codec tests)
- TaskEnvelope mutability requires careful handling in concurrent paths

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Schema drift between Pydantic and FlatBuffers | Medium | High | Roundtrip tests in FAB-007 |
| TaskEnvelope mutation during concurrent access | Low | Medium | FAB-003 concurrency model ensures single-threaded pipeline |
| Frozen dataclass too rigid for future extensions | Low | Low | Optional fields with defaults; schema evolution via new version |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| Envelope types | `k1/fabric/types/envelopes.py` | New |
| Envelope codec | `k1/fabric/codecs/envelope_codec.py` | New |
| Request builder | `k1/fabric/types/builders.py` | New (convenience) |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.fabric.capability.requested.v1` | Emitted | CapabilityRequest received by Fabric |
| `k1.fabric.capability.resolved.v1` | Emitted | Provider resolved for request |
| `k1.fabric.capability.completed.v1` | Emitted | CapabilityResult returned to caller |

### Testing Strategy

- [ ] Construction tests for all 7 types (valid + invalid inputs)
- [ ] Immutability tests (frozen dataclass rejects mutation)
- [ ] Factory method tests (CapabilityResult.success, .failure)
- [ ] Serialization roundtrip tests (Pydantic -> FlatBuffers -> Pydantic) per FAB-007
- [ ] TaskEnvelope stage progression tests (created -> retrieved -> resolved -> executing -> completed)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2025-01-01 | - | Initial proposal (seeded from implementation plan 1.1.7) |
| 2026-02-06 | - | Accepted: Frozen Pydantic dataclasses, 7 types, WFQ priority embedded. |
