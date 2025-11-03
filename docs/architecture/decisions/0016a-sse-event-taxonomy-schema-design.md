---
adr_number: 0016a
title: SSE Event Taxonomy & Schema Design (17 Event Types)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0011
- ADR-0012
- ADR-0013
- ADR-0013b
- ADR-0016
- ADR-0016a
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations:
- 0 (2013)
- Events (2015)
- FlatBuffers (2024)
- Webhooks (2024)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0011
  - ADR-0012
  - ADR-0013
  - ADR-0013b
  - ADR-0016
  - ADR-0016a
  affected_contracts:
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
  affected_tests: []
---


# ADR-0016a: SSE Event Taxonomy & Schema Design (17 Event Types)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0016 (SSE Event Schemas)](0016-sse-event-schemas.md)
**Category:** Serialization & Real-Time Communication
**Related ADRs:**
- [ADR-0011 (FlatBuffers Serialization)](0011-flatbuffers-serialization.md)
- [ADR-0012 (76 FlatBuffers Schemas)](0012-76-flatbuffers-schemas.md)
- [ADR-0013 (Pipeline Versioning Policy)](0013-pipeline-versioning-policy.md)

---

## Context

### Problem Statement

ADR-0016 established Server-Sent Events (SSE) as the protocol for read-only server-to-client event streaming in K1. However, the parent ADR focused on protocol selection and infrastructure, leaving detailed event taxonomy and schema design unspecified.

**Key Challenges:**

1. **Event Taxonomy:** What are the 17 event types? How are they categorized?
2. **Schema Design:** What fields does each event type contain? What's required vs optional?
3. **Schema Evolution:** How do schemas version and evolve without breaking clients?
4. **Common Metadata:** What fields are common across all events (trace_id, timestamp, session_id)?
5. **FlatBuffers Integration:** How do we define SSE events using FlatBuffers (single source of truth)?

### Current Landscape

**Industry Event Taxonomies:**

1. **Kubernetes Event API** (Cloud-Native Events):
   - **Pattern:** Resource-based events (Pod.Created, Deployment.Updated, Node.Failed)
   - **Advantage:** Clear resource hierarchy, standardized structure
   - **Disadvantage:** Too generic (doesn't capture domain-specific agent/turn semantics)

2. **GitHub Webhooks** (Developer Platform Events):
   - **Pattern:** Action-based events (push, pull_request.opened, issue.closed)
   - **Advantage:** Action verbs clarify intent
   - **Disadvantage:** Flat namespace (no categories), hard to filter

3. **AWS CloudWatch Events** (Infrastructure Monitoring):
   - **Pattern:** Service-based events (EC2.StateChange, RDS.Failover, Lambda.Invocation)
   - **Advantage:** Service prefix enables filtering by category
   - **Disadvantage:** Verbose naming, inconsistent structure

4. **Slack Events API** (Messaging Platform):
   - **Pattern:** Resource.Action events (message.posted, user.joined, file.uploaded)
   - **Advantage:** Consistent resource.action pattern
   - **Disadvantage:** Limited to messaging domain

### K1 Requirements

**Event Categories (5 Total):**

1. **Agent Lifecycle** (4 events): Agent hiring, firing, crashing, blacklisting
2. **Turn Events** (4 events): Turn start, completion, failure, interruption (barge-in)
3. **Tool Events** (4 events): Tool call started, completed, failed, approval required
4. **Session Events** (3 events): Session creation, termination, crash
5. **System Events** (2 events): Heartbeat (keepalive), error notifications

**Schema Requirements:**

- **Common Metadata:** All events share trace_id, session_id, timestamp, event_type
- **Versioning:** SemVer 2.0 (MAJOR.MINOR.PATCH) per ADR-0013
- **FlatBuffers First:** Define in FlatBuffers, serialize to JSON for SSE
- **Backward Compatibility:** New optional fields OK, removing fields requires MAJOR bump
- **Forward Compatibility:** Old clients ignore unknown fields

---

## Decision

We will define **17 SSE event types organized into 5 categories** using **FlatBuffers schemas** as the single source of truth:

### Event Naming Convention

**Pattern:** `{category}.{action}`

**Categories:**
- `agent.*` — Agent lifecycle events
- `turn.*` — Turn execution events
- `tool.*` — Tool execution events
- `session.*` — Session lifecycle events
- `system.*` — System-wide events

**Examples:**
- `agent.hired` — Agent hired by orchestrator
- `turn.started` — User turn started
- `tool.executed` — Tool execution completed
- `session.created` — New session created
- `system.heartbeat` — Keepalive event

---

## Event Schemas

### Common Event Envelope

**All events inherit from EventEnvelope:**

```flatbuffers
// schemas/sse/event_envelope.fbs
namespace k1.sse;

/// Semantic version for schema evolution (MAJOR.MINOR.PATCH)
struct SchemaVersion {
  major: uint16 = 1;
  minor: uint16 = 0;
  patch: uint16 = 0;
}

/// Common metadata for all SSE events
table EventMetadata {
  /// Unique event ID (UUID v4)
  event_id: string (required);

  /// Event type discriminator (e.g., "agent.hired", "turn.started")
  event_type: string (required);

  /// Unix timestamp in milliseconds (event occurrence time)
  timestamp_ms: uint64 (required);

  /// Cognitive trace ID (end-to-end observability)
  trace_id: string (required);

  /// Session ID (if event is session-scoped, empty for system events)
  session_id: string;

  /// Schema version (SemVer 2.0)
  schema_version: SchemaVersion (required);
}

/// Root event envelope (wraps all event types)
table EventEnvelope {
  /// Event metadata (required for all events)
  metadata: EventMetadata (required);

  /// Event payload (union of all 17 event types)
  payload: EventPayload (required);
}

/// Union of all event payload types
union EventPayload {
  // Agent lifecycle (4 events)
  AgentHired,
  AgentFired,
  AgentCrashed,
  AgentRestarted,

  // Turn events (4 events)
  TurnStarted,
  TurnCompleted,
  TurnFailed,
  TurnInterrupted,

  // Tool events (4 events)
  ToolCallStarted,
  ToolCallCompleted,
  ToolCallFailed,
  ToolApprovalRequired,

  // Session events (3 events)
  SessionCreated,
  SessionTerminated,
  SessionCrashed,

  // System events (2 events)
  Heartbeat,
  Error,
}
```

**Envelope Size:** ~150-200 bytes (JSON overhead).

---

### Category 1: Agent Lifecycle Events (4 Events)

#### **1. agent.hired — Agent Hired Event**

**Purpose:** Emitted when orchestrator hires a new agent (Contract Net selection phase).

```flatbuffers
// schemas/sse/agent_hired.fbs
namespace k1.sse;

/// Agent hired event (Contract Net selection result)
table AgentHired {
  /// Unique agent identifier
  agent_id: string (required);

  /// Agent type (e.g., "planner", "tool_runner", "safety_watch")
  agent_type: string (required);

  /// Agent version hash (for blacklist tracking, crash correlation)
  version_hash: string (required);

  /// Capabilities granted to agent (e.g., ["TOOL_CALL", "MEMORY_WRITE"])
  capabilities: [string] (required);

  /// Supervisor ID (agent's supervisor for health monitoring)
  supervisor_id: string (required);

  /// Hiring score (0.0-1.0, from Contract Net negotiation)
  hiring_score: float;

  /// Initial agent state (typically "WARMING")
  initial_state: string (required);

  /// Task announcement ID (which task this agent was hired for)
  task_id: string;
}
```

**Example JSON (SSE data field):**

```json
{
  "metadata": {
    "event_id": "evt-123abc",
    "event_type": "agent.hired",
    "timestamp_ms": 1697123456789,
    "trace_id": "trace-abc-123",
    "session_id": "sess-xyz-789",
    "schema_version": {"major": 1, "minor": 0, "patch": 0}
  },
  "payload": {
    "agent_id": "agent-planner-001",
    "agent_type": "planner",
    "version_hash": "v1.2.3-abc123",
    "capabilities": ["TOOL_CALL", "MEMORY_WRITE", "MODEL_CALL"],
    "supervisor_id": "supervisor-1",
    "hiring_score": 0.87,
    "initial_state": "WARMING",
    "task_id": "task-plan-456"
  }
}
```

---

#### **2. agent.fired — Agent Terminated Event**

**Purpose:** Emitted when agent gracefully terminates (DRAINING → TERMINATED).

```flatbuffers
// schemas/sse/agent_fired.fbs
namespace k1.sse;

/// Reason for agent termination
enum TerminationReason : byte {
  IDLE_TIMEOUT = 0,        // IDLE → DRAINING (60s timeout)
  MEMORY_PRESSURE = 1,     // High memory pressure triggered eviction
  SESSION_END = 2,         // Session terminated, agent no longer needed
  MANUAL_SHUTDOWN = 3,     // Admin request or orchestrator decision
  TASK_COMPLETED = 4,      // Task completed, agent no longer needed
}

/// Agent gracefully terminated event
table AgentFired {
  /// Agent identifier
  agent_id: string (required);

  /// Agent type
  agent_type: string (required);

  /// Termination reason
  termination_reason: TerminationReason (required);

  /// Final agent state (should be "TERMINATED")
  final_state: string (required);

  /// Agent lifetime duration (milliseconds from HIRED to TERMINATED)
  lifetime_ms: uint64 (required);

  /// Number of tasks completed during lifetime
  tasks_completed: uint32;

  /// Was termination graceful? (true = DRAINING completed, false = forced)
  graceful: bool = true;
}
```

---

#### **3. agent.crashed — Agent Crashed Event**

**Purpose:** Emitted when agent crashes unexpectedly (supervisor detected failure).

```flatbuffers
// schemas/sse/agent_crashed.fbs
namespace k1.sse;

/// Agent crashed event (unplanned termination)
table AgentCrashed {
  /// Agent identifier
  agent_id: string (required);

  /// Agent type
  agent_type: string (required);

  /// Agent version hash (for blacklist tracking)
  version_hash: string (required);

  /// Crash reason (error message)
  crash_reason: string (required);

  /// Error trace (stack trace, logs, up to 2KB)
  error_trace: string;

  /// Will supervisor restart this agent?
  will_restart: bool (required);

  /// Restart delay (milliseconds, exponential backoff)
  restart_delay_ms: uint32;

  /// Recent crash count for this agent type (last 10 minutes)
  crash_count_recent: uint32 (required);

  /// Is this agent version blacklisted now?
  blacklisted: bool (required);

  /// Supervisor ID
  supervisor_id: string (required);
}
```

---

#### **4. agent.restarted — Agent Restarted Event**

**Purpose:** Emitted when supervisor restarts a crashed agent.

```flatbuffers
// schemas/sse/agent_restarted.fbs
namespace k1.sse;

/// Agent restarted after crash
table AgentRestarted {
  /// New agent ID (different from crashed agent)
  agent_id: string (required);

  /// Original crashed agent ID
  original_agent_id: string (required);

  /// Agent type (same as crashed agent)
  agent_type: string (required);

  /// Agent version hash (may be different if new version deployed)
  version_hash: string (required);

  /// Restart attempt number (1, 2, 3, ...)
  restart_attempt: uint32 (required);

  /// Restart delay that was applied (exponential backoff)
  restart_delay_ms: uint32 (required);

  /// Supervisor ID
  supervisor_id: string (required);
}
```

---

### Category 2: Turn Events (4 Events)

#### **5. turn.started — Turn Started Event**

**Purpose:** Emitted when user turn begins (user message received by K1).

```flatbuffers
// schemas/sse/turn_started.fbs
namespace k1.sse;

/// Turn started event
table TurnStarted {
  /// Unique turn identifier
  turn_id: string (required);

  /// User message preview (first 100 characters, truncated)
  user_message_preview: string (required);

  /// Number of multimodal attachments (images, audio, video)
  attachment_count: uint32;

  /// Detected intent (e.g., "search_web", "book_restaurant", "chat")
  intent: string;

  /// Expected agents (from planning stage, may be empty if not planned yet)
  expected_agents: [string];

  /// Privacy band for this turn (GREEN, AMBER, RED)
  privacy_band: string (required);
}
```

---

#### **6. turn.completed — Turn Completed Event**

**Purpose:** Emitted when turn successfully completes (response sent to user).

```flatbuffers
// schemas/sse/turn_completed.fbs
namespace k1.sse;

/// Turn completed successfully
table TurnCompleted {
  /// Turn identifier
  turn_id: string (required);

  /// Turn duration (milliseconds from start to completion)
  duration_ms: uint64 (required);

  /// Performance metrics
  ttft_ms: uint32;           // Time to first token (P95 target: 150ms)
  tokens_generated: uint32;  // Total output tokens
  tools_called: uint32;      // Number of tool calls executed

  /// Agents involved in turn execution
  agents_used: [string] (required);

  /// Belief deltas written to K0 (number of facts updated)
  belief_deltas: uint32;

  /// Final turn outcome (e.g., "success", "partial_success", "user_satisfied")
  outcome: string;
}
```

---

#### **7. turn.failed — Turn Failed Event**

**Purpose:** Emitted when turn fails to complete (error occurred).

```flatbuffers
// schemas/sse/turn_failed.fbs
namespace k1.sse;

/// Reason for turn failure
enum FailureReason : byte {
  AGENT_CRASH = 0,           // Agent crashed during turn
  TOOL_FAILURE = 1,          // Tool execution failed
  TIMEOUT = 2,               // Turn timeout (> 2000ms P95)
  VALIDATION_ERROR = 3,      // Plan validation failed
  INTERNAL_ERROR = 4,        // K1 internal error
  SAFETY_FILTER = 5,         // Safety Watch rejected turn
}

/// Recovery action taken after failure
enum RecoveryAction : byte {
  NONE = 0,                  // No recovery attempted
  RETRY = 1,                 // Retry turn with same plan
  FALLBACK_AGENT = 2,        // Use fallback agent
  SAGA_ROLLBACK = 3,         // Rollback state (compensating transactions)
  DEGRADE_GRACEFULLY = 4,    // Return partial result or error message
}

/// Turn failed event
table TurnFailed {
  /// Turn identifier
  turn_id: string (required);

  /// Failure reason
  failure_reason: FailureReason (required);

  /// Human-readable error message
  error_message: string (required);

  /// Recovery action taken
  recovery_action: RecoveryAction (required);

  /// Turn duration before failure (milliseconds)
  duration_ms: uint64 (required);

  /// Which agent crashed (if AGENT_CRASH)
  failed_agent_id: string;

  /// Which tool failed (if TOOL_FAILURE)
  failed_tool_name: string;
}
```

---

#### **8. turn.interrupted — Turn Interrupted Event**

**Purpose:** Emitted when turn is interrupted mid-execution (barge-in or system interruption).

```flatbuffers
// schemas/sse/turn_interrupted.fbs
namespace k1.sse;

/// Reason for turn interruption
enum InterruptReason : byte {
  BARGE_IN_STOP = 0,         // User explicitly stopped turn
  BARGE_IN_NEW_TURN = 1,     // User started new turn (interrupts current)
  TIMEOUT = 2,               // Turn timeout (safety mechanism)
  MEMORY_PRESSURE = 3,       // System memory pressure
  THERMAL_THROTTLE = 4,      // Device overheating
}

/// Turn interrupted event
table TurnInterrupted {
  /// Turn identifier (interrupted turn)
  turn_id: string (required);

  /// Interrupt reason
  interrupt_reason: InterruptReason (required);

  /// Duration before interrupt (milliseconds)
  duration_before_interrupt_ms: uint64 (required);

  /// Tokens generated before interrupt
  tokens_before_interrupt: uint32;

  /// New turn ID (if BARGE_IN_NEW_TURN)
  new_turn_id: string;

  /// Was state rolled back? (Saga compensation)
  state_rolled_back: bool;
}
```

---

### Category 3: Tool Events (4 Events)

#### **9. tool.call_started — Tool Call Started Event**

**Purpose:** Emitted when agent starts tool execution.

```flatbuffers
// schemas/sse/tool_call_started.fbs
namespace k1.sse;

/// Privacy band for tool execution
enum PrivacyBand : byte {
  GREEN = 0,   // Low sensitivity (public APIs, local tools)
  AMBER = 1,   // Medium sensitivity (calendar, email, bank read-only)
  RED = 2,     // High sensitivity (financial transactions, health data)
  BLACK = 3,   // Critical (admin operations, system config)
}

/// Tool call started event
table ToolCallStarted {
  /// Unique tool call identifier
  tool_call_id: string (required);

  /// Turn context
  turn_id: string (required);
  agent_id: string (required);

  /// Tool details
  tool_name: string (required);
  tool_arguments: string (required);  // JSON-encoded arguments

  /// Privacy band for this tool call
  band: PrivacyBand (required);

  /// Does this tool call require arbiter approval?
  requires_approval: bool;

  /// Sandbox type (MCP, WASM, Process)
  sandbox_type: string (required);
}
```

---

#### **10. tool.call_completed — Tool Call Completed Event**

**Purpose:** Emitted when tool execution completes successfully.

```flatbuffers
// schemas/sse/tool_call_completed.fbs
namespace k1.sse;

/// Tool call completed successfully
table ToolCallCompleted {
  /// Tool call identifier
  tool_call_id: string (required);
  turn_id: string (required);
  agent_id: string (required);

  /// Tool result (JSON-encoded, up to 10KB)
  result: string (required);

  /// Execution metrics
  duration_ms: uint64 (required);
  result_size_bytes: uint32 (required);

  /// Tool runner ID (which runner executed this tool)
  tool_runner_id: string (required);

  /// Was result cached? (KV cache hit)
  cached: bool;
}
```

---

#### **11. tool.call_failed — Tool Call Failed Event**

**Purpose:** Emitted when tool execution fails.

```flatbuffers
// schemas/sse/tool_call_failed.fbs
namespace k1.sse;

/// Tool error codes
enum ToolErrorCode : uint32 {
  UNKNOWN = 0,
  TIMEOUT = 1,               // Tool execution timeout (> 3000ms)
  NETWORK_ERROR = 2,         // Network connectivity issue
  INVALID_ARGUMENTS = 3,     // Tool arguments invalid
  UNAUTHORIZED = 4,          // Missing capability or permission
  TOOL_CRASHED = 5,          // Tool sandbox crashed
  RATE_LIMIT = 6,            // API rate limit exceeded
  RESOURCE_UNAVAILABLE = 7,  // Tool resource not available
}

/// Tool call failed event
table ToolCallFailed {
  /// Tool call identifier
  tool_call_id: string (required);
  turn_id: string (required);
  agent_id: string (required);
  tool_name: string (required);

  /// Failure details
  error_message: string (required);
  error_code: ToolErrorCode (required);

  /// Retry policy
  retryable: bool (required);
  retry_count: uint32;       // Current retry attempt
  max_retries: uint32;       // Maximum retries allowed
}
```

---

#### **12. tool.approval_required — Tool Approval Required Event**

**Purpose:** Emitted when tool requires arbiter approval (RED/BLACK band).

```flatbuffers
// schemas/sse/tool_approval_required.fbs
namespace k1.sse;

/// Tool approval required event (arbiter intervention)
table ToolApprovalRequired {
  /// Tool call identifier
  tool_call_id: string (required);
  turn_id: string (required);
  agent_id: string (required);

  /// Tool details
  tool_name: string (required);
  tool_arguments: string (required);  // JSON-encoded
  band: PrivacyBand (required);

  /// Arbiter policy that triggered approval
  policy_rule: string (required);

  /// Approval timeout (milliseconds, default 30000ms)
  approval_timeout_ms: uint32;

  /// Human-readable approval prompt
  approval_prompt: string;
}
```

---

### Category 4: Session Events (3 Events)

#### **13. session.created — Session Created Event**

**Purpose:** Emitted when new user session is created.

```flatbuffers
// schemas/sse/session_created.fbs
namespace k1.sse;

/// Session created event
table SessionCreated {
  /// Session identifier
  session_id: string (required);

  /// User identifier
  user_id: string (required);

  /// Session metadata
  initial_persona: string (required);      // Persona name (e.g., "default", "child")
  initial_beliefs: string;                 // JSON-encoded initial facts
  space: string (required);                // Space name (e.g., "family", "work")

  /// Session configuration
  max_turns: uint32;                       // Maximum turns allowed (0 = unlimited)
  session_timeout_ms: uint64;              // Session timeout (milliseconds)

  /// Device metadata
  device_id: string;
  device_type: string;                     // "phone", "tablet", "laptop", "watch"
}
```

---

#### **14. session.terminated — Session Terminated Event**

**Purpose:** Emitted when session terminates gracefully.

```flatbuffers
// schemas/sse/session_terminated.fbs
namespace k1.sse;

/// Reason for session termination
enum SessionTerminationReason : byte {
  USER_LOGOUT = 0,           // User logged out
  SESSION_TIMEOUT = 1,       // Session timeout (inactivity)
  MAX_TURNS_REACHED = 2,     // Max turns limit reached
  MANUAL_ADMIN = 3,          // Admin forced termination
  SYSTEM_SHUTDOWN = 4,       // K1 system shutdown
}

/// Session terminated gracefully
table SessionTerminated {
  /// Session identifier
  session_id: string (required);

  /// Termination reason
  termination_reason: SessionTerminationReason (required);

  /// Session metrics
  total_turns: uint32 (required);
  total_duration_ms: uint64 (required);
  total_tokens: uint64;
  total_tools_called: uint32;

  /// K0 grounding status
  final_receipt_id: string (required);     // Last K0 receipt
  all_deltas_committed: bool (required);   // All state deltas written to K0
}
```

---

#### **15. session.crashed — Session Crashed Event**

**Purpose:** Emitted when session crashes unrecoverably.

```flatbuffers
// schemas/sse/session_crashed.fbs
namespace k1.sse;

/// Session crashed event
table SessionCrashed {
  /// Session identifier
  session_id: string (required);

  /// Crash details
  crash_reason: string (required);
  error_trace: string;

  /// Recovery status
  recoverable: bool (required);
  recovery_session_id: string;  // New session ID (if recovered)

  /// Lost data
  uncommitted_deltas: uint32;   // State deltas not written to K0
  last_receipt_id: string;      // Last successful K0 receipt
}
```

---

### Category 5: System Events (2 Events)

#### **16. system.heartbeat — Heartbeat Event**

**Purpose:** Keepalive event (every 30s) to prevent SSE timeout, provides system health.

```flatbuffers
// schemas/sse/heartbeat.fbs
namespace k1.sse;

/// System heartbeat event (keepalive + health)
table Heartbeat {
  /// Server health
  server_id: string (required);
  uptime_ms: uint64 (required);

  /// Current load
  active_sessions: uint32 (required);
  active_agents: uint32 (required);
  active_tools: uint32;

  /// Resource usage
  cpu_usage_percent: float;     // 0.0-100.0
  memory_usage_mb: uint32;
  memory_limit_mb: uint32;

  /// Thermal state
  device_temperature_celsius: int32;
  thermal_state: string;        // "NORMAL", "WARM", "HOT", "THROTTLING"
}
```

---

#### **17. system.error — Error Event**

**Purpose:** System-wide error notification (critical errors, service unavailability).

```flatbuffers
// schemas/sse/error.fbs
namespace k1.sse;

/// Error severity levels
enum Severity : byte {
  INFO = 0,      // Informational (not an error)
  WARNING = 1,   // Warning (degraded but functional)
  ERROR = 2,     // Error (operation failed)
  CRITICAL = 3,  // Critical (system instability)
}

/// System error codes
enum ErrorCode : uint32 {
  UNKNOWN = 0,
  INTERNAL_SERVER_ERROR = 500,
  SERVICE_UNAVAILABLE = 503,
  SESSION_NOT_FOUND = 1001,
  AGENT_UNAVAILABLE = 1002,
  TOOL_UNAVAILABLE = 1003,
  K0_UNAVAILABLE = 1004,
  MODEL_HUB_UNAVAILABLE = 1005,
}

/// System error event
table Error {
  /// Error classification
  error_code: ErrorCode (required);
  error_message: string (required);

  /// Context
  trace_id: string (required);
  session_id: string;

  /// Severity
  severity: Severity (required);

  /// Recovery information
  recoverable: bool (required);
  retry_after_ms: uint32;    // Suggested retry delay

  /// Component that failed
  component: string;         // "orchestrator", "model_hub", "k0_bridge", etc.
}
```

---

## Schema Evolution Strategy

### Versioning Rules (SemVer 2.0)

Following ADR-0013 (Pipeline Versioning Policy):

1. **MAJOR version** (1.0.0 → 2.0.0): Breaking changes
   - Remove required field
   - Change field type (e.g., string → int)
   - Remove event type from union

2. **MINOR version** (1.0.0 → 1.1.0): Backward-compatible additions
   - Add optional field
   - Add new event type to union
   - Add new enum value

3. **PATCH version** (1.0.0 → 1.0.1): Bug fixes, documentation
   - Fix typo in comment
   - Clarify field description
   - No schema changes

### Forward/Backward Compatibility

**Backward Compatibility (old clients, new server):**
- ✅ **Add optional field:** Old clients ignore new fields (FlatBuffers default values)
- ✅ **Add new event type:** Old clients ignore unknown event types
- ❌ **Remove field:** Breaks old clients expecting the field (MAJOR bump required)
- ❌ **Change field type:** Breaks old clients parsing the field (MAJOR bump required)

**Forward Compatibility (new clients, old server):**
- ✅ **Add optional field:** New clients use default values if field missing
- ✅ **Add new event type:** New clients handle unknown event types gracefully
- ❌ **Remove field:** New clients fail if they require the field (MAJOR bump)

### Deprecation Policy (90 Days)

Per ADR-0013, deprecated fields follow 90-day timeline:

1. **Day 0:** Announce deprecation in release notes, mark field `[deprecated]` in schema
2. **Day 30:** Emit warning logs when deprecated field is used
3. **Day 60:** Emit error logs (but still functional)
4. **Day 90:** Remove field (MAJOR version bump, breaking change)

**Example:**

```flatbuffers
// Version 1.0.0
table AgentHired {
  agent_id: string (required);
  agent_type: string (required);
  version_hash: string (required);      // Deprecated in v1.1.0, remove in v2.0.0
  agent_version: string (required);     // New field in v1.1.0 (replaces version_hash)
}

// Version 1.1.0 (90 days before v2.0.0)
// - version_hash marked [deprecated]
// - agent_version added (optional for backward compat)

// Version 2.0.0 (after 90 days)
// - version_hash removed (MAJOR bump)
// - agent_version now required
```

---

## Implementation Plan

### Phase 1: Schema Definition (Week 1-2)

**Deliverables:**
- ✅ 17 FlatBuffers schemas (agent_hired.fbs, turn_started.fbs, etc.)
- ✅ EventEnvelope union (wraps all 17 event types)
- ✅ EventMetadata table (common fields)
- ✅ Enum definitions (TerminationReason, FailureReason, PrivacyBand, etc.)

**Tasks:**
1. Create `schemas/sse/` directory
2. Define EventEnvelope.fbs (common envelope)
3. Define 17 event schemas (4 agent + 4 turn + 4 tool + 3 session + 2 system)
4. Define enums (TerminationReason, FailureReason, InterruptReason, ToolErrorCode, etc.)
5. Validate schemas with `flatc --python` (generate Python bindings)

---

### Phase 2: Schema Validation & Testing (Week 3)

**Deliverables:**
- ✅ Schema validation tests (17 event types × FlatBuffers compilation)
- ✅ JSON serialization tests (FlatBuffers → JSON → verify structure)
- ✅ Compatibility tests (v1.0.0 → v1.1.0 backward/forward compat)

**Tasks:**
1. Write WARD tests for each event type (17 tests)
2. Test FlatBuffers → JSON serialization (verify field names, types)
3. Test schema evolution (add optional field, verify old clients work)
4. Test enum additions (add new TerminationReason, verify compatibility)
5. Benchmark serialization latency (<2ms per event)

---

### Phase 3: Documentation & Integration (Week 4)

**Deliverables:**
- ✅ Schema documentation (17 event types with examples)
- ✅ Versioning guide (MAJOR/MINOR/PATCH rules)
- ✅ Migration guide (v1.0.0 → v1.1.0 → v2.0.0)
- ✅ Integration with 0016b (FlatBuffers-to-JSON serializer)

**Tasks:**
1. Document all 17 event types (purpose, fields, examples)
2. Create compatibility matrix (v1.0.0, v1.1.0, v2.0.0)
3. Write migration guide (how to upgrade clients)
4. Integrate with 0016b serializer (feed schemas to serializer)
5. Code review and approval

---

## Consequences

### Positive Consequences

#### ✅ **Single Source of Truth (FlatBuffers)**

- **Benefit:** All 17 event schemas defined in FlatBuffers (no manual JSON maintenance)
- **Impact:** Zero schema drift (JSON auto-generated from FlatBuffers), type safety enforced
- **Example:** Add optional field to AgentHired → FlatBuffers compiler validates → JSON serializer auto-updated

#### ✅ **Clear Event Taxonomy (5 Categories)**

- **Benefit:** Clients can filter by category (agent.*, turn.*, tool.*, session.*, system.*)
- **Impact:** Reduced bandwidth (subscribe to agent.* only, ignore tool.*)
- **Example:** Admin dashboard subscribes to agent.* + system.*, saves 60% bandwidth

#### ✅ **Schema Evolution Support (SemVer 2.0)**

- **Benefit:** Add optional fields without breaking old clients (backward compatible)
- **Impact:** Zero downtime upgrades (deploy new server with v1.1.0, old clients v1.0.0 still work)
- **Example:** Add `agent_version` field in v1.1.0, old clients ignore it, new clients use it

#### ✅ **Common Metadata (trace_id, session_id, timestamp)**

- **Benefit:** All events have trace_id for end-to-end observability
- **Impact:** Easier debugging (trace request from WebSocket → SSE → K0)
- **Example:** User reports "turn took 5s", search SSE events by trace_id, find slow tool call

---

### Negative Consequences

#### ❌ **FlatBuffers Learning Curve**

- **Cost:** Team must learn FlatBuffers schema language (union, enum, table)
- **Mitigation:** Provide training, examples, schema templates
- **Impact:** 1-2 weeks initial learning curve

#### ❌ **Schema Evolution Complexity**

- **Cost:** MAJOR/MINOR/PATCH versioning requires discipline (manual version bumps)
- **Mitigation:** Automated version bump validation (ADR-0013b tool)
- **Impact:** Risk of accidental breaking change if version bump forgotten

#### ❌ **17 Schemas to Maintain**

- **Cost:** 17 schemas × maintenance (documentation, tests, evolution)
- **Mitigation:** Auto-generate documentation from schemas, automated tests
- **Impact:** Ongoing maintenance effort (~4 hours/month)

---

## Alternatives Considered

### Alternative 1: JSON Schemas Only (No FlatBuffers)

**Pattern:** Define SSE events using JSON Schema (OpenAPI-style).

**Advantages:**
- ✅ Simpler (no FlatBuffers learning curve)
- ✅ Native JSON format (no conversion overhead)

**Disadvantages:**
- ❌ Schema drift risk (manual JSON maintenance, no single source of truth)
- ❌ No type safety (runtime errors, not compile-time)
- ❌ Inconsistent with ADR-0012 (76 FlatBuffers schemas, why special-case SSE?)

**Why Rejected:** FlatBuffers single source of truth prevents schema drift, consistent with ADR-0012.

---

### Alternative 2: Dynamic Event Schemas (No Predefined Types)

**Pattern:** Events have no fixed schema (arbitrary JSON payloads).

**Advantages:**
- ✅ Flexible (no schema changes needed)

**Disadvantages:**
- ❌ No type safety (runtime errors, hard to debug)
- ❌ Schema drift risk (every event can have different fields)
- ❌ No versioning (how to evolve events?)

**Why Rejected:** Defeats purpose of schemas (type safety, versioning, documentation).

---

### Alternative 3: One Schema Per Category (Not Per Event)

**Pattern:** AgentLifecycleEvent (union of hired/fired/crashed), TurnEvent (union of started/completed/failed).

**Advantages:**
- ✅ Fewer schemas (5 instead of 17)

**Disadvantages:**
- ❌ Harder to filter (can't subscribe to agent.hired only, must take all agent.*)
- ❌ Larger payloads (must include discriminator field)
- ❌ Harder to evolve (changing one event type affects entire category)

**Why Rejected:** Granular event types enable fine-grained filtering, easier evolution.

---

## Security Considerations

### Sensitive Data in Events

**Risk:** Events contain PII (user_id, session_id, tool arguments).

**Mitigation:**
1. **PII Redaction:** Redact sensitive fields in tool_arguments (e.g., credit card numbers)
2. **Event Filtering:** Clients only receive events for sessions they own (authorization)
3. **Audit Logging:** All SSE connections logged (who subscribed to what events)

---

### Event Injection Attacks

**Risk:** Attacker crafts fake SSE events (spoofing).

**Mitigation:**
1. **Server-Side Only:** SSE is server → client only (no client → server events)
2. **Authentication:** SSE connections require session token (validated on connect)
3. **Signature:** Events signed with HMAC-SHA256 (optional, for high-security environments)

---

## Monitoring & Observability

### Prometheus Metrics

```python
sse_events_emitted_total = Counter(
    'sse_events_emitted_total',
    'Total SSE events emitted',
    ['event_type', 'session_id']
)

sse_event_serialization_duration_ms = Histogram(
    'sse_event_serialization_duration_ms',
    'SSE event serialization duration (FlatBuffers → JSON)',
    ['event_type'],
    buckets=[0.5, 1, 2, 5, 10]
)

sse_schema_version_gauge = Gauge(
    'sse_schema_version_gauge',
    'Current SSE schema version',
    ['version_major', 'version_minor', 'version_patch']
)
```

---

## Documentation

**Schema Documentation:**
- Auto-generated from FlatBuffers schemas (using flatc)
- Include examples for each event type
- Version history (v1.0.0, v1.1.0, v2.0.0 changes)

**Migration Guides:**
- How to upgrade from v1.0.0 → v1.1.0 (no breaking changes)
- How to upgrade from v1.X.X → v2.0.0 (breaking changes, 90-day deprecation)

---

## Research Citations

1. **Google FlatBuffers (2024).** *"Schema Evolution."* https://google.github.io/flatbuffers/flatbuffers_guide_schema_evolution.html — Forward/backward compatibility strategies.

2. **Semantic Versioning 2.0.0 (2013).** *"SemVer Specification."* https://semver.org/ — MAJOR.MINOR.PATCH versioning rules.

3. **GitHub Webhooks (2024).** *"Event Types."* https://docs.github.com/en/developers/webhooks-and-events — Event taxonomy patterns.

4. **W3C Server-Sent Events (2015).** *"EventSource API."* https://html.spec.whatwg.org/multipage/server-sent-events.html — SSE protocol, event format.

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-12
**Target Completion:** 2025-11-09 (4 weeks)
**Blocked By:** None (foundational sub-ADR)
**Blocks:** 0016b (Serialization), 0016c (Filtering), 0016d (Browser Integration)

---

### Committee Approval

| Committee | Approval Status | Date | Notes |
|-----------|----------------|------|-------|
| **Architecture Committee** | ⏳ Pending | TBD | Review 17 event types, taxonomy |
| **K1 Kernel Team** | ⏳ Pending | TBD | Validate FlatBuffers schemas |
| **Frontend Team** | ⏳ Pending | TBD | Review JSON structure, browser compatibility |
| **Security Team** | ⏳ Pending | TBD | PII redaction, event filtering |

---

**END OF ADR-0016a**