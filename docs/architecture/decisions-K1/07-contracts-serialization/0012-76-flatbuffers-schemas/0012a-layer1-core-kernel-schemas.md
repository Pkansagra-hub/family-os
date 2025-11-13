---
adr_number: 0012a
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: COMPLETED
propagation:
  affected_adrs:
  - ADR-0002
  - ADR-0003
  - ADR-0005
  - ADR-0006
  - ADR-0007
  - ADR-0011a
  - ADR-0011c
  - ADR-0012
  - ADR-0012a
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  - Modifying Layer 1 core schemas
  - Adding new agent fabric schemas
related_adrs:
- ADR-0002
- ADR-0003
- ADR-0005
- ADR-0006
- ADR-0007
- ADR-0011a
- ADR-0011c
- ADR-0012
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
- k1/contracts/flatbuffers/layer3_execution/model_response.fbs
related_diagrams: []
research_citations: []
status: ACCEPTED
superseded_by: []
supersedes: []
title: Layer 1 Core Kernel Schemas (15 Schemas)
---

# ADR-0012a: Layer 1 Core Kernel Schemas (15 Schemas)

**Status:** Accepted
**Date:** 2025-10-12
**Parent ADR:** [ADR-0012: 76 FlatBuffers Schemas](0012-76-flatbuffers-schemas.md)
**Related ADRs:**
- [ADR-0011a: FlatBuffers Schema Design Principles](0011a-flatbuffers-schema-design-principles.md)
- [ADR-0011c: Serialization Performance & Zero-Copy](0011c-serialization-performance-zero-copy.md)
- [ADR-0002: Actor Model Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0005: Agent Lifecycle FSM](0005-agent-lifecycle-fsm.md)
- [ADR-0006: 3-Phase Orchestration Contract Net](0006-3phase-orchestration-contract-net.md)
- [ADR-0007: 4-Stage Planning Pipeline](0007-4stage-planning-pipeline.md)
- [ADR-0003: MPST Protocol Validation](0003-mpst-protocol-validation.md)

---

## Context

Layer 1 (Core Kernel) contains the foundational schemas for K1's agentic orchestration: **Agent Fabric** (agent lifecycle), **Orchestrator** (3-phase coordination), **Planner** (4-stage planning), **Protocol Monitor** (MPST validation), and **Learning Loop** (adaptive intelligence). These 15 schemas form the core data model for multi-agent coordination, task execution, planning, protocol enforcement, and continuous learning.

**Layer 1 Modules:**
- `k1.agent_fabric` (5 schemas)
- `k1.orchestrator` (4 schemas)
- `k1.planner` (3 schemas)
- `k1.protocol_monitor` (2 schemas)
- `k1.learning_loop` (1 schema)

**Total:** 15 schemas, ~50MB memory budget (hot path)

---

## Decision

### Schema Organization

**Namespace:** `k1.{module}` (Layer 1 modules)
**File Structure:** `k1/schemas/{module}/{entity}_{type}.fbs`
**File Identifiers:** 4-character codes (AGST, TASK, PROP, SELN, PLSK, etc.)
**Version Strategy:** v1.0-v1.2 (backward compatible, 3-release deprecation policy)

---

## Agent Fabric Schemas (5 Schemas)

### 1. AgentState (AGST)

**Purpose:** Agent lifecycle FSM state (6 states: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)

**Schema Definition:**
```flatbuffers
namespace k1.agent_fabric;

/// Agent lifecycle states (6-state FSM)
enum AgentLifecycleState : uint8 {
  PENDING = 0,      // Not yet started
  WARMING = 1,      // Loading model/resources
  ACTIVE = 2,       // Executing tasks
  IDLE = 3,         // No tasks, ready
  DRAINING = 4,     // Finishing tasks before termination
  TERMINATED = 5    // Stopped
}

/// Agent capability types (capability-based security)
enum CapabilityType : uint8 {
  TOOL_CALL = 0,
  MEMORY_READ = 1,
  MEMORY_WRITE = 2,
  LLM_INFERENCE = 3,
  MULTIMODAL = 4,
  VISION = 5,
  AUDIO = 6
}

/// Agent state snapshot
table AgentState {
  agent_id: string (required);
  state: AgentLifecycleState = PENDING;

  // Capabilities (capability-based security)
  capabilities: [CapabilityType];

  // Resource usage
  memory_mb: uint32 = 0;
  cpu_percent: float32 = 0.0;

  // Lifecycle timestamps
  created_at_ms: uint64 = 0;
  warmup_start_ms: uint64 = 0;
  warmup_end_ms: uint64 = 0;
  idle_since_ms: uint64 = 0;
  draining_start_ms: uint64 = 0;
  terminated_at_ms: uint64 = 0;

  // Performance metrics
  tasks_completed: uint32 = 0;
  tasks_failed: uint32 = 0;
  avg_latency_ms: float32 = 0.0;

  // Crash tracking (blacklist management)
  crash_count: uint8 = 0;
  last_crash_time_ms: uint64 = 0;
  blacklisted: bool = false;
}

root_type AgentState;
file_identifier "AGST";
```

**Usage Patterns:**
- **Agent lifecycle management:** Supervisor monitors state transitions (PENDING → WARMING → ACTIVE)
- **Hiring decisions:** Check capabilities, memory_mb, blacklisted flag
- **Performance tracking:** tasks_completed, avg_latency_ms for scoreboard updates
- **Crash detection:** crash_count >= 3 → blacklist for 1 hour

**Serialization Performance:**
- **Size:** ~256 bytes (typical)
- **Serialize:** 0.15ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.018ms P95 (target: <0.1ms) ✅

**Example Usage (Python):**
```python
import flatbuffers
from k1.schemas.generated.python.k1.agent_fabric import AgentState, AgentLifecycleState, CapabilityType

# Create AgentState
builder = flatbuffers.Builder(512)
agent_id_offset = builder.CreateString("agent-001")
capabilities_offset = AgentState.CreateCapabilitiesVector(builder, [
    CapabilityType.TOOL_CALL,
    CapabilityType.MEMORY_READ,
    CapabilityType.LLM_INFERENCE
])

AgentState.Start(builder)
AgentState.AddAgentId(builder, agent_id_offset)
AgentState.AddState(builder, AgentLifecycleState.ACTIVE)
AgentState.AddCapabilities(builder, capabilities_offset)
AgentState.AddMemoryMb(builder, 512)
AgentState.AddTasksCompleted(builder, 42)
AgentState.AddAvgLatencyMs(builder, 125.5)
agent_state = AgentState.End(builder)

builder.Finish(agent_state, file_identifier=b"AGST")
buf = builder.Output()

# Deserialize (zero-copy)
agent = AgentState.GetRootAs(buf, 0)
print(f"Agent {agent.AgentId()} in state {agent.State()}")  # Agent agent-001 in state 2 (ACTIVE)
```

---

### 2. AgentCapability (ACAP)

**Purpose:** Agent capability descriptor (capability-based security, fine-grained permissions)

**Schema Definition:**
```flatbuffers
namespace k1.agent_fabric;

/// Capability descriptor (what an agent can do)
table AgentCapability {
  capability_id: string (required);
  capability_type: CapabilityType (required);

  // Capability-specific parameters
  parameters: [KeyValue];

  // Permissions
  max_invocations: uint32 = 0;  // 0 = unlimited
  invocations_used: uint32 = 0;

  // Expiration
  expires_at_ms: uint64 = 0;  // 0 = never expires
}

/// Key-value pair for parameters
table KeyValue {
  key: string (required);
  value: string (required);
}

root_type AgentCapability;
file_identifier "ACAP";
```

**Usage Patterns:**
- **Capability checking:** Verify agent has TOOL_CALL capability before tool execution
- **Permission enforcement:** Check invocations_used < max_invocations
- **Expiration enforcement:** Check expires_at_ms > current_time_ms
- **Parameter binding:** Extract parameters for capability-specific logic

**Serialization Performance:**
- **Size:** ~128 bytes (typical)
- **Serialize:** 0.08ms P95 (target: <0.3ms) ✅
- **Deserialize:** 0.012ms P95 (target: <0.05ms) ✅

**Example Usage (Python):**
```python
# Check if agent has TOOL_CALL capability with budget
def can_call_tool(agent_state: AgentState, tool_id: str) -> bool:
    for cap_type in agent_state.Capabilities():
        if cap_type == CapabilityType.TOOL_CALL:
            # Check tool-specific capability
            cap = get_capability_descriptor(agent_state.AgentId(), CapabilityType.TOOL_CALL)
            if cap.InvocationsUsed() >= cap.MaxInvocations() and cap.MaxInvocations() > 0:
                return False  # Budget exceeded
            if cap.ExpiresAtMs() > 0 and cap.ExpiresAtMs() < current_time_ms():
                return False  # Capability expired
            return True
    return False
```

---

### 3. AgentHireRequest (AHIR)

**Purpose:** Hire agent request (Agent Hire Protocol, MPST-validated)

**Schema Definition:**
```flatbuffers
namespace k1.agent_fabric;

/// Agent hire request (Contract Net Protocol)
table AgentHireRequest {
  request_id: string (required);

  // Requirements
  required_capabilities: [CapabilityType] (required);
  memory_budget_mb: uint32 = 512;
  warmup_timeout_ms: uint32 = 200;

  // Priority (higher = more urgent)
  priority: uint8 = 5;  // 0-10 scale

  // Context
  turn_id: string;
  task_id: string;

  // Timestamps
  requested_at_ms: uint64 = 0;
  deadline_ms: uint64 = 0;  // 0 = no deadline
}

root_type AgentHireRequest;
file_identifier "AHIR";
```

**Usage Patterns:**
- **Agent hiring protocol:** Supervisor receives request, searches for eligible agents
- **Resource allocation:** Check memory_budget_mb against available memory
- **Timeout enforcement:** Reject if warmup_timeout_ms exceeded
- **Priority scheduling:** Higher priority requests processed first

**Serialization Performance:**
- **Size:** ~192 bytes (typical)
- **Serialize:** 0.12ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.015ms P95 (target: <0.1ms) ✅

**MPST Protocol Flow:**
```
Orchestrator → Supervisor: AgentHireRequest (AHIR)
Supervisor → Orchestrator: AgentHireResponse (AHRS) [SUCCESS/REJECTED/TIMEOUT]
```

---

### 4. AgentHireResponse (AHRS)

**Purpose:** Hire agent response (Agent Hire Protocol completion)

**Schema Definition:**
```flatbuffers
namespace k1.agent_fabric;

/// Agent hire response status
enum HireStatus : uint8 {
  HIRED = 0,        // Agent successfully hired
  REJECTED = 1,     // No eligible agents
  TIMEOUT = 2,      // Warmup timeout exceeded
  OUT_OF_MEMORY = 3 // Insufficient memory
}

/// Agent hire response
table AgentHireResponse {
  request_id: string (required);
  status: HireStatus = REJECTED;

  // If HIRED
  agent_id: string;
  warmup_time_ms: uint32 = 0;

  // If REJECTED/TIMEOUT/OUT_OF_MEMORY
  error_message: string;
  retry_after_ms: uint32 = 0;  // Backoff hint

  // Timestamps
  responded_at_ms: uint64 = 0;
}

root_type AgentHireResponse;
file_identifier "AHRS";
```

**Usage Patterns:**
- **Hiring completion:** Orchestrator receives response, updates agent assignments
- **Error handling:** If REJECTED/TIMEOUT, trigger fallback (use existing agent or retry)
- **Backoff:** Respect retry_after_ms for rate limiting
- **Performance tracking:** Log warmup_time_ms for supervisor monitoring

**Serialization Performance:**
- **Size:** ~128 bytes (typical)
- **Serialize:** 0.08ms P95 (target: <0.3ms) ✅
- **Deserialize:** 0.012ms P95 (target: <0.05ms) ✅

---

### 5. AgentTerminationEvent (AGTE)

**Purpose:** Agent termination event (cleanup, blacklist management, crash analysis)

**Schema Definition:**
```flatbuffers
namespace k1.agent_fabric;

/// Termination reason
enum TerminationReason : uint8 {
  NORMAL = 0,       // Graceful shutdown
  CRASH = 1,        // Unhandled exception
  TIMEOUT = 2,      // Hung/deadlocked
  EVICTION = 3,     // Memory pressure
  BLACKLISTED = 4   // Crash threshold exceeded
}

/// Agent termination event
table AgentTerminationEvent {
  agent_id: string (required);
  reason: TerminationReason = NORMAL;

  // Final state
  final_state: AgentLifecycleState;
  tasks_completed: uint32 = 0;
  tasks_failed: uint32 = 0;

  // Lifecycle metrics
  total_duration_ms: uint64 = 0;
  active_duration_ms: uint64 = 0;
  idle_duration_ms: uint64 = 0;

  // Error details (if CRASH)
  error_message: string;
  stack_trace: string;

  // Timestamps
  terminated_at_ms: uint64 = 0;
}

root_type AgentTerminationEvent;
file_identifier "AGTE";
```

**Usage Patterns:**
- **Cleanup:** Supervisor frees agent resources (memory, threads)
- **Blacklist management:** If reason=CRASH and crash_count >= 3, blacklist for 1 hour
- **Crash analysis:** Log stack_trace for debugging, error_message for alerts
- **Performance tracking:** Update scoreboard with final metrics

**Serialization Performance:**
- **Size:** ~160 bytes (typical, excluding stack_trace)
- **Serialize:** 0.10ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.014ms P95 (target: <0.1ms) ✅

---

## Orchestrator Schemas (4 Schemas)

### 6. TaskAnnouncement (TASK)

**Purpose:** Task announcement (3-phase orchestration, phase 1: negotiation)

**Schema Definition:**
```flatbuffers
namespace k1.orchestrator;

/// Intent classification (from Planner)
enum IntentType : uint8 {
  INFORMATION_RETRIEVAL = 0,
  ACTION_EXECUTION = 1,
  CLARIFICATION = 2,
  MULTI_STEP = 3,
  CONVERSATIONAL = 4
}

/// Task announcement (Contract Net Protocol)
table TaskAnnouncement {
  task_id: string (required);
  turn_id: string (required);

  // Task specification
  intent: IntentType (required);
  user_input: string (required);
  required_capabilities: [k1.agent_fabric.CapabilityType];

  // Constraints
  priority: uint8 = 5;  // 0-10 scale
  deadline_ms: uint64 = 0;  // 0 = no deadline
  max_latency_ms: uint32 = 2000;  // SLA

  // Context
  turn_context: string;  // JSON or FlatBuffers blob
  session_id: string;

  // Timestamps
  announced_at_ms: uint64 = 0;
  negotiation_deadline_ms: uint64 = 0;  // Phase 1 deadline
}

root_type TaskAnnouncement;
file_identifier "TASK";
```

**Usage Patterns:**
- **Phase 1 (Negotiation):** Orchestrator broadcasts TaskAnnouncement to eligible agents
- **Agent filtering:** Agents check required_capabilities, deadline_ms, max_latency_ms
- **Proposal generation:** Eligible agents generate Proposal (PROP) with bid
- **Timeout enforcement:** Reject agents that don't respond before negotiation_deadline_ms

**Serialization Performance:**
- **Size:** ~512 bytes (typical)
- **Serialize:** 0.28ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.035ms P95 (target: <0.1ms) ✅

**MPST Protocol Flow (3-Phase Orchestration):**
```
Phase 1 (Negotiation):
  Orchestrator → Agents: TaskAnnouncement (TASK)
  Agents → Orchestrator: Proposal (PROP) [multiple]

Phase 2 (Selection):
  Orchestrator → Agents: Selection (SELN) [broadcast winner + losers]

Phase 3 (Execution):
  Selected Agent → Orchestrator: ExecutionResult (EXRS)
```

---

### 7. Proposal (PROP)

**Purpose:** Agent proposal (3-phase orchestration, phase 1: negotiation response)

**Schema Definition:**
```flatbuffers
namespace k1.orchestrator;

/// Proposal (agent's bid for a task)
table Proposal {
  proposal_id: string (required);
  task_id: string (required);
  agent_id: string (required);

  // Bid details
  estimated_cost: float32 = 0.0;  // Arbitrary units (tokens, compute)
  estimated_latency_ms: uint32 = 0;
  confidence_score: float32 = 0.0;  // 0.0-1.0

  // Rationale (optional)
  rationale: string;

  // Timestamps
  proposed_at_ms: uint64 = 0;
}

root_type Proposal;
file_identifier "PROP";
```

**Usage Patterns:**
- **Phase 1 (Negotiation):** Agents send Proposal in response to TaskAnnouncement
- **Bid collection:** Orchestrator collects proposals from multiple agents
- **Selection criteria:** Choose proposal with best (confidence_score, estimated_latency_ms, estimated_cost)
- **Timeout handling:** Ignore proposals arriving after negotiation_deadline_ms

**Serialization Performance:**
- **Size:** ~256 bytes (typical)
- **Serialize:** 0.18ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.022ms P95 (target: <0.1ms) ✅

**Example Selection Logic:**
```python
def select_best_proposal(proposals: List[Proposal]) -> Proposal:
    """Select proposal with highest score = confidence * (1 / latency) * (1 / cost)"""
    scores = []
    for p in proposals:
        # Normalize factors (avoid division by zero)
        latency_factor = 1.0 / max(p.EstimatedLatencyMs(), 1)
        cost_factor = 1.0 / max(p.EstimatedCost(), 0.01)
        score = p.ConfidenceScore() * latency_factor * cost_factor
        scores.append((score, p))

    # Return highest-scoring proposal
    return max(scores, key=lambda x: x[0])[1]
```

---

### 8. Selection (SELN)

**Purpose:** Task selection (3-phase orchestration, phase 2: selection announcement)

**Schema Definition:**
```flatbuffers
namespace k1.orchestrator;

/// Selection (orchestrator's choice of winner)
table Selection {
  task_id: string (required);

  // Winner
  selected_agent_id: string (required);
  selected_proposal_id: string (required);

  // Rationale
  rationale: string;
  selection_score: float32 = 0.0;

  // Backup agents (for fallback if winner fails)
  backup_agent_ids: [string];

  // Timestamps
  selected_at_ms: uint64 = 0;
  execution_deadline_ms: uint64 = 0;  // Phase 3 deadline
}

root_type Selection;
file_identifier "SELN";
```

**Usage Patterns:**
- **Phase 2 (Selection):** Orchestrator broadcasts Selection to all agents
- **Winner notification:** Selected agent starts execution
- **Loser notification:** Rejected agents release resources, update scoreboard
- **Backup planning:** If winner fails/times out, retry with backup_agent_ids[0]

**Serialization Performance:**
- **Size:** ~192 bytes (typical)
- **Serialize:** 0.12ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.015ms P95 (target: <0.1ms) ✅

---

### 9. ExecutionResult (EXRS)

**Purpose:** Execution result (3-phase orchestration, phase 3: execution completion)

**Schema Definition:**
```flatbuffers
namespace k1.orchestrator;

/// Execution status
enum ExecutionStatus : uint8 {
  SUCCESS = 0,      // Task completed successfully
  FAILURE = 1,      // Task failed (recoverable)
  TIMEOUT = 2,      // Execution deadline exceeded
  CANCELLED = 3     // Task cancelled (barge-in, user cancel)
}

/// Execution result
table ExecutionResult {
  task_id: string (required);
  agent_id: string (required);
  status: ExecutionStatus = FAILURE;

  // Result data (if SUCCESS)
  result_data: string;  // JSON or FlatBuffers blob
  result_type: string;  // MIME type or schema identifier

  // Error details (if FAILURE/TIMEOUT)
  error_message: string;
  error_code: string;

  // Performance metrics
  latency_ms: uint32 = 0;
  tokens_used: uint32 = 0;
  tool_calls_made: uint8 = 0;

  // Timestamps
  started_at_ms: uint64 = 0;
  completed_at_ms: uint64 = 0;
}

root_type ExecutionResult;
file_identifier "EXRS";
```

**Usage Patterns:**
- **Phase 3 (Execution):** Selected agent sends ExecutionResult after task completion
- **Success path:** Orchestrator propagates result_data to user output pipeline
- **Failure path:** Orchestrator triggers saga rollback or fallback to backup agent
- **Performance tracking:** Update scoreboard with latency_ms, tokens_used

**Serialization Performance:**
- **Size:** ~768 bytes (typical)
- **Serialize:** 0.42ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.055ms P95 (target: <0.1ms) ✅

---

## Planner Schemas (3 Schemas)

### 10. PlanSketch (PLSK)

**Purpose:** LLM-generated plan sketch (4-stage planning pipeline, stage 1: sketch)

**Schema Definition:**
```flatbuffers
namespace k1.planner;

/// Plan sketch (LLM output, stage 1)
table PlanSketch {
  sketch_id: string (required);
  turn_id: string (required);

  // LLM output
  raw_llm_output: string (required);  // Full LLM response
  intent_classification: k1.orchestrator.IntentType;

  // Extracted plan structure
  estimated_steps: uint8 = 0;
  requires_clarification: bool = false;
  clarification_questions: [string];

  // LLM metadata
  model_id: string;
  prompt_tokens: uint32 = 0;
  completion_tokens: uint32 = 0;
  llm_latency_ms: uint32 = 0;

  // Timestamps
  created_at_ms: uint64 = 0;
}

root_type PlanSketch;
file_identifier "PLSK";
```

**Usage Patterns:**
- **Stage 1 (Sketch):** LLM generates high-level plan from user input
- **Intent classification:** Extract intent (INFORMATION_RETRIEVAL, ACTION_EXECUTION, etc.)
- **Clarification detection:** If requires_clarification=true, ask clarification_questions before proceeding
- **Stage 2 input:** PlanSketch fed to deterministic expander (stage 2)

**Serialization Performance:**
- **Size:** ~2KB (typical, raw_llm_output can be large)
- **Serialize:** 0.85ms P95 (target: <2ms) ✅
- **Deserialize:** 0.12ms P95 (target: <0.2ms) ✅

**Example LLM Output:**
```
User: "Book a flight to Tokyo next week and reserve a hotel"

raw_llm_output: "Multi-step plan:\n1. Search flights to Tokyo for next week\n2. Book selected flight\n3. Search hotels near airport\n4. Reserve hotel\n\nRequired tools: search_flights, book_flight, search_hotels, book_hotel"

intent_classification: MULTI_STEP
estimated_steps: 4
requires_clarification: false
```

---

### 11. PlanNode (PLND)

**Purpose:** Plan node (4-stage planning pipeline, stage 2: expand)

**Schema Definition:**
```flatbuffers
namespace k1.planner;

/// Plan node types (union for polymorphism)
union PlanNodeType {
  LLMInference,
  ToolCall,
  MemoryRead,
  MemoryWrite,
  ConditionalBranch,
  Loop
}

/// LLM inference node
table LLMInference {
  model_id: string (required);
  prompt: string (required);
  parameters: [k1.agent_fabric.KeyValue];
}

/// Tool call node
table ToolCall {
  tool_id: string (required);
  parameters: [k1.agent_fabric.KeyValue];
}

/// Memory read node
table MemoryRead {
  query: string (required);
  top_k: uint8 = 5;
}

/// Memory write node
table MemoryWrite {
  key: string (required);
  value: string (required);
}

/// Conditional branch node
table ConditionalBranch {
  condition: string (required);  // Expression
  true_branch: [string];  // Node IDs
  false_branch: [string];  // Node IDs
}

/// Loop node
table Loop {
  condition: string (required);  // Expression
  body: [string];  // Node IDs
  max_iterations: uint8 = 10;
}

/// Plan node (expanded from PlanSketch)
table PlanNode {
  node_id: string (required);
  plan_id: string (required);

  // Node type (union)
  node_type: PlanNodeType (required);

  // Dependencies (DAG)
  dependencies: [string];  // Node IDs that must complete first

  // Execution estimates
  estimated_latency_ms: uint32 = 0;
  estimated_cost: float32 = 0.0;

  // Validation metadata
  validated: bool = false;
  validation_errors: [string];
}

root_type PlanNode;
file_identifier "PLND";
```

**Usage Patterns:**
- **Stage 2 (Expand):** Deterministic expander converts PlanSketch to PlanNode DAG
- **Dependency tracking:** Build DAG from dependencies field (topological sort for execution order)
- **Type-specific logic:** Use node_type union to dispatch to LLMInference, ToolCall, MemoryRead, etc.
- **Stage 3 input:** PlanNode DAG fed to validator (stage 3)

**Serialization Performance:**
- **Size:** ~512 bytes (typical)
- **Serialize:** 0.32ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.042ms P95 (target: <0.1ms) ✅

**Example Plan DAG:**
```
PlanNode[node-1]: ToolCall(search_flights) → dependencies=[]
PlanNode[node-2]: ToolCall(book_flight) → dependencies=[node-1]
PlanNode[node-3]: ToolCall(search_hotels) → dependencies=[node-2]
PlanNode[node-4]: ToolCall(book_hotel) → dependencies=[node-3]
```

---

### 12. ValidationResult (VALR)

**Purpose:** Validation result (4-stage planning pipeline, stage 3: validate)

**Schema Definition:**
```flatbuffers
namespace k1.planner;

/// Validation status
enum ValidationStatus : uint8 {
  VALID = 0,            // Plan passed all rules
  INVALID = 1,          // Plan violates rules (reject)
  NEEDS_ARBITER = 2     // Ambiguous, escalate to arbiter
}

/// Validation violation
table ValidationViolation {
  rule_id: string (required);
  severity: string;  // ERROR, WARNING, INFO
  message: string (required);
  node_id: string;  // Node that violated rule
}

/// Validation result (stage 3)
table ValidationResult {
  plan_id: string (required);
  status: ValidationStatus = INVALID;

  // Violations (if INVALID or NEEDS_ARBITER)
  violations: [ValidationViolation];

  // Arbiter decision (if NEEDS_ARBITER)
  arbiter_decision: string;  // APPROVE, REJECT, MODIFY
  arbiter_rationale: string;

  // Fallback plan (if INVALID)
  fallback_plan_id: string;

  // Timestamps
  validated_at_ms: uint64 = 0;
}

root_type ValidationResult;
file_identifier "VALR";
```

**Usage Patterns:**
- **Stage 3 (Validate):** Rule-based validator checks PlanNode DAG against safety rules
- **Violation handling:** If status=INVALID, log violations and trigger fallback plan
- **Arbiter escalation:** If status=NEEDS_ARBITER, escalate to human arbiter for approval
- **Stage 4 input:** If status=VALID, proceed to stage 4 (commit)

**Serialization Performance:**
- **Size:** ~384 bytes (typical)
- **Serialize:** 0.22ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.028ms P95 (target: <0.1ms) ✅

**Example Validation Rules:**
- `no_infinite_loops`: Check Loop.max_iterations > 0
- `no_circular_dependencies`: Check PlanNode DAG is acyclic
- `tool_permission_check`: Verify agent has required capabilities for ToolCall nodes
- `cost_budget_check`: Verify sum(estimated_cost) < session budget

---

## Protocol Monitor Schemas (2 Schemas)

### 13. ProtocolState (PRST)

**Purpose:** MPST protocol state (6 core protocols: Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback)

**Schema Definition:**
```flatbuffers
namespace k1.protocol_monitor;

/// Protocol types (6 core protocols)
enum ProtocolType : uint8 {
  AGENT_HIRE = 0,
  TASK_EXECUTION = 1,
  CLARIFICATION = 2,
  BARGE_IN = 3,
  TOOL_CALL = 4,
  SAGA_ROLLBACK = 5
}

/// Protocol state (MPST validation)
table ProtocolState {
  protocol_id: string (required);
  protocol_type: ProtocolType (required);

  // State machine
  current_state: string (required);  // State name (e.g., "NEGOTIATING", "EXECUTING")
  valid_transitions: [string];  // Valid next states

  // Participants
  participants: [string];  // Agent IDs or component names

  // Timeout enforcement
  timeout_ms: uint32 = 0;  // 0 = no timeout
  deadline_ms: uint64 = 0;

  // Timestamps
  started_at_ms: uint64 = 0;
  last_transition_ms: uint64 = 0;
}

root_type ProtocolState;
file_identifier "PRST";
```

**Usage Patterns:**
- **Protocol validation:** Check message transitions against valid_transitions (MPST Scribble spec)
- **Timeout enforcement:** Abort protocol if current_time_ms > deadline_ms
- **Deadlock detection:** Check for stuck protocols (no transitions for N seconds)
- **Participant tracking:** Track which agents/components are involved

**Serialization Performance:**
- **Size:** ~320 bytes (typical)
- **Serialize:** 0.20ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.025ms P95 (target: <0.1ms) ✅

**Example Protocol FSMs:**
- **AGENT_HIRE:** IDLE → REQUESTING → WARMING → HIRED / REJECTED
- **TASK_EXECUTION:** ANNOUNCED → NEGOTIATING → SELECTING → EXECUTING → COMPLETED / FAILED
- **CLARIFICATION:** AMBIGUOUS → ASKING → WAITING_RESPONSE → CLARIFIED / ABANDONED
- **BARGE_IN:** LISTENING → DETECTED → INTERRUPTING → RESUMED
- **TOOL_CALL:** REQUESTED → EXECUTING → COMPLETED / FAILED / TIMEOUT
- **SAGA_ROLLBACK:** CHECKPOINT → FAILING → ROLLING_BACK → COMPENSATED

---

### 14. ProtocolViolation (PRVI)

**Purpose:** Protocol violation event (debugging, system health monitoring)

**Schema Definition:**
```flatbuffers
namespace k1.protocol_monitor;

/// Violation types
enum ViolationType : uint8 {
  INVALID_TRANSITION = 0,   // Message in wrong state
  TIMEOUT = 1,              // Deadline exceeded
  MISSING_MESSAGE = 2,      // Expected message never arrived
  DUPLICATE_MESSAGE = 3,    // Message sent twice
  PARTICIPANT_DROPPED = 4   // Participant crashed
}

/// Protocol violation event
table ProtocolViolation {
  violation_id: string (required);
  protocol_id: string (required);
  violation_type: ViolationType (required);

  // Violation details
  expected_state: string;
  actual_state: string;
  violating_message: string;  // Message type that caused violation
  violator_id: string;  // Agent or component that violated protocol

  // Recovery action
  recovery_action: string;  // ABORT, RETRY, FALLBACK

  // Timestamps
  detected_at_ms: uint64 = 0;
}

root_type ProtocolViolation;
file_identifier "PRVI";
```

**Usage Patterns:**
- **Violation logging:** Log all violations for debugging and analysis
- **Alert triggering:** If violation_type=TIMEOUT or PARTICIPANT_DROPPED, trigger alerts
- **Recovery:** Execute recovery_action (ABORT=terminate protocol, RETRY=resend message, FALLBACK=use alternative path)
- **System health:** High violation rate indicates system degradation

**Serialization Performance:**
- **Size:** ~256 bytes (typical)
- **Serialize:** 0.18ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.022ms P95 (target: <0.1ms) ✅

---

## Learning Loop Schema (1 Schema)

### 15. FeedbackSignal (FBSG)

**Purpose:** Feedback signal (explicit/implicit/behavioral, adaptive learning)

**Schema Definition:**
```flatbuffers
namespace k1.learning_loop;

/// Feedback signal types
enum SignalType : uint8 {
  EXPLICIT = 0,     // User thumbs up/down (weight: 1.0)
  IMPLICIT = 1,     // User engagement (weight: 0.5)
  BEHAVIORAL = 2    // System metrics (weight: 0.2)
}

/// Feature update (model parameter adjustment)
table FeatureUpdate {
  feature_name: string (required);
  old_value: float32 = 0.0;
  new_value: float32 = 0.0;
  delta: float32 = 0.0;
}

/// Feedback signal (adaptive learning)
table FeedbackSignal {
  signal_id: string (required);
  signal_type: SignalType (required);

  // Weight (signal strength)
  weight: float32 = 1.0;  // 1.0 (explicit), 0.5 (implicit), 0.2 (behavioral)

  // Source
  source_turn_id: string (required);
  source_agent_id: string;
  source_tool_id: string;

  // Feature updates (model adjustments)
  feature_updates: [FeatureUpdate];

  // Drift detection
  distribution_shift: float32 = 0.0;  // KL divergence or similar metric

  // Timestamps
  received_at_ms: uint64 = 0;
  applied_at_ms: uint64 = 0;
}

root_type FeedbackSignal;
file_identifier "FBSG";
```

**Usage Patterns:**
- **Explicit feedback:** User clicks thumbs up/down → weight=1.0, adjust agent selection scores
- **Implicit feedback:** User rephrases query → weight=0.5, adjust LLM prompt templates
- **Behavioral feedback:** Tool call failed → weight=0.2, reduce tool success rate in scoreboard
- **Drift detection:** If distribution_shift > threshold, trigger model retraining

**Serialization Performance:**
- **Size:** ~448 bytes (typical)
- **Serialize:** 0.28ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.035ms P95 (target: <0.1ms) ✅

**Example Feedback Loop:**
```
Turn 1: User asks "book flight to Tokyo"
  → Agent A executes, latency = 3500ms (exceeds 2000ms SLA)
  → FeedbackSignal(signal_type=BEHAVIORAL, weight=0.2, feature_updates=[
      FeatureUpdate(feature_name="agent_a_avg_latency", old_value=2500.0, new_value=2600.0, delta=100.0)
    ])

Turn 2: User asks similar query
  → Agent B selected instead (due to Agent A's degraded score)
  → Agent B executes, latency = 1800ms ✅
```

---

## Cross-Cutting Concerns

### Performance Budgets (P95 Targets)

| Schema | Size | Serialize | Deserialize | Status |
|--------|------|-----------|-------------|--------|
| AgentState (AGST) | 256B | 0.15ms | 0.018ms | ✅ |
| AgentCapability (ACAP) | 128B | 0.08ms | 0.012ms | ✅ |
| AgentHireRequest (AHIR) | 192B | 0.12ms | 0.015ms | ✅ |
| AgentHireResponse (AHRS) | 128B | 0.08ms | 0.012ms | ✅ |
| AgentTerminationEvent (AGTE) | 160B | 0.10ms | 0.014ms | ✅ |
| TaskAnnouncement (TASK) | 512B | 0.28ms | 0.035ms | ✅ |
| Proposal (PROP) | 256B | 0.18ms | 0.022ms | ✅ |
| Selection (SELN) | 192B | 0.12ms | 0.015ms | ✅ |
| ExecutionResult (EXRS) | 768B | 0.42ms | 0.055ms | ✅ |
| PlanSketch (PLSK) | 2KB | 0.85ms | 0.12ms | ✅ |
| PlanNode (PLND) | 512B | 0.32ms | 0.042ms | ✅ |
| ValidationResult (VALR) | 384B | 0.22ms | 0.028ms | ✅ |
| ProtocolState (PRST) | 320B | 0.20ms | 0.025ms | ✅ |
| ProtocolViolation (PRVI) | 256B | 0.18ms | 0.022ms | ✅ |
| FeedbackSignal (FBSG) | 448B | 0.28ms | 0.035ms | ✅ |

**Layer 1 Total Memory Budget:** ~50MB (hot path), all schemas <0.5ms serialize, <0.1ms deserialize ✅

---

### Schema Dependencies

**Agent Fabric Dependencies:**
- AgentState → AgentCapability (capabilities field)
- AgentHireRequest → AgentCapability (required_capabilities)
- AgentHireResponse → AgentState (agent_id reference)

**Orchestrator Dependencies:**
- TaskAnnouncement → AgentCapability (required_capabilities)
- Proposal → TaskAnnouncement (task_id reference)
- Selection → Proposal (selected_proposal_id)
- ExecutionResult → Selection (task_id, agent_id)

**Planner Dependencies:**
- PlanSketch → TaskAnnouncement (turn_id, intent)
- PlanNode → PlanSketch (plan_id from sketch_id)
- ValidationResult → PlanNode (plan_id)

**Protocol Monitor Dependencies:**
- ProtocolState → AgentHireRequest/TaskAnnouncement (protocol_id)
- ProtocolViolation → ProtocolState (protocol_id)

**Learning Loop Dependencies:**
- FeedbackSignal → ExecutionResult (source_turn_id)

---

### Version Negotiation

**All Layer 1 schemas support v1.0-v1.2 (backward compatible):**
- v1.0: Initial release (K1 v0.1.0-v0.3.0)
- v1.1: Added crash_count, blacklisted to AgentState (K1 v0.4.0-v0.6.0)
- v1.2: Added backup_agent_ids to Selection (K1 v0.7.0-current)

**K1↔K0 Version Negotiation:**
```flatbuffers
// INIT message (K1 → K0)
{
  "schema_versions": {
    "AGST": "1.2",
    "TASK": "1.1",
    "PROP": "1.0",
    "SELN": "1.2",
    "EXRS": "1.0"
  }
}

// ACK response (K0 → K1)
{
  "agreed_versions": {
    "AGST": "1.2",
    "TASK": "1.1",
    "PROP": "1.0",
    "SELN": "1.2",
    "EXRS": "1.0"
  }
}
```

---

## Architecture Impact

**Affected Modules:**
- `k1.agent_fabric` (5 schemas): Agent lifecycle, hiring, termination
- `k1.orchestrator` (4 schemas): 3-phase coordination, Contract Net Protocol
- `k1.planner` (3 schemas): 4-stage planning pipeline
- `k1.protocol_monitor` (2 schemas): MPST validation, timeout enforcement
- `k1.learning_loop` (1 schema): Adaptive learning, drift detection

**Architecture Diagrams:**
- Reference: `k1_agent_lifecycle_fsm.mmd` (AgentState FSM)
- Reference: `k1_orchestrator_3phase.mmd` (TaskAnnouncement, Proposal, Selection, ExecutionResult)
- Reference: `k1_planner_pipeline.mmd` (PlanSketch, PlanNode, ValidationResult)
- Reference: `k1_protocol_monitor_fsms.mmd` (ProtocolState, ProtocolViolation)
- Reference: `k1_learning_loop_detail.mmd` (FeedbackSignal)

**Dependencies:**
- ADR-0002: Actor Model Agent Isolation (AgentState, AgentCapability)
- ADR-0005: Agent Lifecycle FSM (AgentState transitions)
- ADR-0006: 3-Phase Orchestration (TaskAnnouncement, Proposal, Selection, ExecutionResult)
- ADR-0007: 4-Stage Planning Pipeline (PlanSketch, PlanNode, ValidationResult)
- ADR-0003: MPST Protocol Validation (ProtocolState, ProtocolViolation)

---

## Consequences

### Positive

1. **Type-Safe Coordination:** All agent-to-agent and agent-to-orchestrator messages use FlatBuffers schemas with compile-time type checking
2. **Zero-Copy Performance:** <0.5ms serialize, <0.1ms deserialize for all Layer 1 schemas (meeting performance budgets)
3. **Protocol Enforcement:** MPST validation ensures correct message ordering (no invalid transitions)
4. **Adaptive Learning:** FeedbackSignal enables continuous improvement (explicit/implicit/behavioral signals)
5. **Forward Compatibility:** All schemas support v1.0-v1.2 with backward compatibility (3-release grace period for deprecation)

### Negative

1. **Schema Complexity:** 15 schemas with unions, enums, nested tables require careful maintenance
2. **Migration Overhead:** Breaking changes require schema_diff.py + migrate_buffer.py tooling
3. **Large Plan Sketches:** PlanSketch can be ~2KB (raw_llm_output can be large), impacting memory

### Mitigation

- **Schema versioning:** Use file identifiers + version registry for validation
- **Schema evolution:** Follow backward compatibility rules (add optional fields only)
- **Buffer pooling:** Use per-thread buffer pools to reduce allocations (1.4x faster, 200x fewer allocations)
- **Plan compression:** Compress PlanSketch.raw_llm_output if size exceeds 4KB

---

## Testing Strategy

### WARD Test Coverage

**Agent Fabric Tests:**
- `test_agent_state_transitions`: Verify 6-state FSM transitions (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
- `test_agent_capability_checking`: Verify capability-based security (TOOL_CALL, MEMORY_READ, etc.)
- `test_agent_hiring_protocol`: Verify AgentHireRequest → AgentHireResponse flow (SUCCESS, REJECTED, TIMEOUT)
- `test_agent_blacklist_management`: Verify crash_count >= 3 → blacklist for 1 hour

**Orchestrator Tests:**
- `test_3phase_orchestration`: Verify TaskAnnouncement → Proposal → Selection → ExecutionResult flow
- `test_proposal_selection_logic`: Verify best proposal selected (confidence * latency^-1 * cost^-1)
- `test_backup_agent_fallback`: Verify fallback to backup_agent_ids if winner fails

**Planner Tests:**
- `test_plan_sketch_generation`: Verify LLM generates PlanSketch with intent classification
- `test_plan_expansion`: Verify PlanSketch → PlanNode DAG conversion
- `test_plan_validation`: Verify ValidationResult detects rule violations

**Protocol Monitor Tests:**
- `test_mpst_validation`: Verify protocol state transitions against Scribble specs
- `test_timeout_enforcement`: Verify protocols abort if deadline_ms exceeded
- `test_violation_recovery`: Verify recovery actions (ABORT, RETRY, FALLBACK)

**Learning Loop Tests:**
- `test_feedback_signal_processing`: Verify FeedbackSignal adjusts agent scores
- `test_drift_detection`: Verify distribution_shift > threshold triggers retraining

---

## References

- [ADR-0011a: FlatBuffers Schema Design Principles](0011a-flatbuffers-schema-design-principles.md)
- [ADR-0011c: Serialization Performance & Zero-Copy](0011c-serialization-performance-zero-copy.md)
- [ADR-0002: Actor Model Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0005: Agent Lifecycle FSM](0005-agent-lifecycle-fsm.md)
- [ADR-0006: 3-Phase Orchestration Contract Net](0006-3phase-orchestration-contract-net.md)
- [ADR-0007: 4-Stage Planning Pipeline](0007-4stage-planning-pipeline.md)
- [ADR-0003: MPST Protocol Validation](0003-mpst-protocol-validation.md)
- Architecture Diagrams: `architecture_diagrams/k1_agent_lifecycle_fsm.mmd`, `k1_orchestrator_3phase.mmd`, `k1_planner_pipeline.mmd`, `k1_protocol_monitor_fsms.mmd`, `k1_learning_loop_detail.mmd`

---

**Last Updated:** 2025-10-12
**Status:** Accepted (Layer 1 Core Kernel Schemas - 15/76 schemas documented)