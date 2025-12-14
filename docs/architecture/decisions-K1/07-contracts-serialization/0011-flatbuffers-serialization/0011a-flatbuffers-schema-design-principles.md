---
adr_number: 0011a
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
- maintainability
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
  - ADR-0001
  - ADR-0011
  - ADR-0011a
  - ADR-0011b
  - ADR-0017
  - ADR-0019
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  - Creating new FlatBuffers schemas
  - Modifying schema design patterns
related_adrs:
- ADR-0001
- ADR-0011
- ADR-0011b
- ADR-0011c
- ADR-0011d
- ADR-0012a
- ADR-0012b
- ADR-0012c
- ADR-0012d
- ADR-0012e
- ADR-0017
- ADR-0019
related_contracts:
- k1/contracts/flatbuffers/layer1_kernel/agent_capability.fbs
- k1/contracts/flatbuffers/layer1_kernel/agent_state.fbs
- k1/contracts/flatbuffers/layer1_kernel/proposal.fbs
- k1/contracts/flatbuffers/layer1_kernel/selection.fbs
- k1/contracts/flatbuffers/layer1_kernel/task_announcement.fbs
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
research_citations:
- 'FlatBuffers: A Memory-Efficient Serialization Library (Google, 2014)'
- 'Protocol Buffers: Google''s data interchange format (Google, 2008)'
- 'Cap''n Proto: Cap''n Proto serialization protocol (Sandstorm, 2013)'
status: ACCEPTED
superseded_by: []
supersedes: []
title: FlatBuffers Schema Design Principles
---

# ADR-0011a: FlatBuffers Schema Design Principles

**Status:** Accepted
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0011: FlatBuffers Serialization](./0011-flatbuffers-serialization.md)

---

## Context

K1 Intelligence Module requires a serialization format that supports:

1. **Zero-copy deserialization** for sub-millisecond performance
2. **Forward/backward compatibility** for schema evolution
3. **Type safety** through generated code
4. **Cross-language support** (Python, C++, Rust)
5. **Compact binary format** (2-5x smaller than JSON)

**Research Foundation:**

- **FlatBuffers** (Google 2014): Zero-copy, forward-compatible, minimal parsing overhead
- **Protocol Buffers** (Google 2008): Compared alternative (requires parsing, slower)
- **Cap'n Proto** (Sandstorm 2013): Compared alternative (less tooling maturity)

**Decision:** Use FlatBuffers for all K1 serialization (agent messages, K0 events, SessionState, API payloads, config files).

This ADR defines schema design principles to ensure consistency, performance, and maintainability across all 76 K1 schemas.

---

## Decision

### 1. Schema Design Patterns

#### 1.1 Forward Compatibility First

**Principle:** All schemas must support adding new fields without breaking existing code.

**Rules:**

- **All fields optional by default** (except explicitly required fields with `required` attribute)
- **Use default values** for optional fields (0 for numbers, "" for strings, null for tables)
- **Never remove or rename fields** (use deprecation + new field instead)
- **Use unions for polymorphism** (avoid inheritance, use `union` type)

**Example:**

```fbs
// ✅ GOOD: All fields optional, with defaults
table AgentState {
  agent_id: string;                      // Required in practice, but optional for forward compat
  state: AgentLifecycleState = PENDING;  // Default value
  memory_mb: uint32 = 0;                 // Default value
  capabilities: [AgentCapability];       // Empty vector by default
}

// ❌ BAD: Required field breaks forward compatibility
table AgentState {
  agent_id: string (required);           // Cannot add this later without breaking old readers
}
```

#### 1.2 Schema Organization

**Principle:** Organize schemas by module and layer for clarity and discoverability.

**Namespace Hierarchy:**

```
k1.agent_fabric         // Layer 1: Core Kernel
k1.orchestrator
k1.planner
k1.protocol_monitor
k1.learning_loop

k1.session_state        // Layer 2: State & Persistence
k1.memory_manager
k1.receipt_system
k1.k0_bridge

k1.tool_runner          // Layer 3: Execution & Tools
k1.model_hub
k1.mcp_gateway
k1.streaming_engine

k1.api_gateway          // Layer 4: Ingress & Voice
k1.websocket
k1.voice_pipeline
k1.barge_in

k1.config               // Layer 5: Infrastructure
k1.observability
k1.thermal_manager
k1.backpressure
```

**File Structure:**

```
k1/schemas/
├── agent_fabric/
│   ├── agent_state.fbs
│   ├── agent_capability.fbs
│   └── agent_metrics.fbs
├── orchestrator/
│   ├── task_announcement.fbs
│   ├── proposal.fbs
│   └── selection.fbs
├── session_state/
│   ├── beliefs.fbs
│   ├── scoreboard.fbs
│   └── control.fbs
└── ...
```

#### 1.3 Type System Usage

**Scalars (8 types):**

- `bool` - Boolean (1 byte)
- `int8`, `uint8` - 8-bit integers
- `int16`, `uint16` - 16-bit integers
- `int32`, `uint32` - 32-bit integers (most common)
- `int64`, `uint64` - 64-bit integers (timestamps, large counts)
- `float32` - 32-bit float (metrics, scores)
- `float64` - 64-bit float (high-precision calculations)

**Usage Guidelines:**

- Use `uint32` for counts, IDs (unless >4B range needed)
- Use `int64` for Unix timestamps (milliseconds since epoch)
- Use `float32` for metrics, scores, percentages (sufficient precision)
- Use `float64` only for high-precision calculations (rare)

**Vectors (Dynamic Arrays):**

```fbs
table Example {
  ids: [uint32];                    // Vector of scalars
  messages: [string];               // Vector of strings
  capabilities: [AgentCapability];  // Vector of tables
}
```

**Strings (UTF-8):**

```fbs
table Example {
  agent_id: string;                 // UTF-8 encoded, null-terminated
  trace_id: string;                 // ULIDs, UUIDs stored as strings
}
```

**Tables (Reference Types):**

```fbs
table AgentState {
  agent_id: string;
  capabilities: [AgentCapability];  // Reference to other table
}

table AgentCapability {
  cap_id: string;
  resource_type: string;
}
```

**Unions (Polymorphism):**

```fbs
union PlanNodeType {
  LLMInference,
  ToolCall,
  MemoryRead,
  MemoryWrite
}

table PlanNode {
  node_id: string;
  node_type: PlanNodeType;          // Polymorphic type
}

table LLMInference {
  model_id: string;
  prompt: string;
}

table ToolCall {
  tool_name: string;
  args: string;
}
```

**Enums (Fixed Values):**

```fbs
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2,
  IDLE = 3,
  DRAINING = 4,
  TERMINATED = 5
}
```

**Structs (Value Types):**

```fbs
struct Vec3 {
  x: float32;
  y: float32;
  z: float32;
}

table Example {
  position: Vec3;  // Inline value type (not a reference)
}
```

---

### 2. Naming Conventions

#### 2.1 Schema Files

**Convention:** `{entity}_{type}.fbs` (snake_case)

**Examples:**

- `agent_state.fbs`
- `task_announcement.fbs`
- `inference_request.fbs`
- `backpressure_signal.fbs`

#### 2.2 Tables & Structs

**Convention:** PascalCase (each word capitalized)

**Examples:**

- `AgentState`
- `TaskAnnouncement`
- `InferenceRequest`
- `BackpressureSignal`

#### 2.3 Fields

**Convention:** snake_case (lowercase with underscores)

**Examples:**

- `agent_id`
- `task_announcement_id`
- `inference_request_id`
- `backpressure_level`

#### 2.4 Enums

**Convention:** PascalCase for enum name, UPPER_SNAKE_CASE for values

**Examples:**

```fbs
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2
}

enum TaskStatus : uint8 {
  NOT_STARTED = 0,
  IN_PROGRESS = 1,
  COMPLETED = 2,
  FAILED = 3
}
```

#### 2.5 Namespaces

**Convention:** Lowercase with dots (module hierarchy)

**Examples:**

- `namespace k1.agent_fabric;`
- `namespace k1.orchestrator;`
- `namespace k1.session_state;`

---

### 3. Schema Metadata

#### 3.1 File Identifier (Required)

**Principle:** Every root table must have a 4-character file identifier for versioning and validation.

**Format:** 4 uppercase ASCII characters (letters or digits)

**Examples:**

```fbs
table AgentState {
  agent_id: string;
}
file_identifier "AGST";  // AGent STate

table TaskAnnouncement {
  task_id: string;
}
file_identifier "TASK";  // TASK announcement

table InferenceRequest {
  request_id: string;
}
file_identifier "INRQ";  // INference ReQuest
```

**Registry (76 file identifiers):**

```
AGST - AgentState
AGCP - AgentCapability
AGMT - AgentMetrics
TASK - TaskAnnouncement
PROP - Proposal
SELN - Selection
PLSK - PlanSketch
PLND - PlanNode
BLFS - Beliefs
SCBD - Scoreboard
CTRL - Control
PRSN - Persona
TLRQ - ToolRequest
TLRS - ToolResponse
INRQ - InferenceRequest
INRS - InferenceResponse
... (70 more)
```

#### 3.2 Root Type (Required)

**Principle:** Specify the root table type for every schema file.

**Syntax:** `root_type {TableName};`

**Example:**

```fbs
namespace k1.agent_fabric;

table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
}

file_identifier "AGST";
root_type AgentState;
```

#### 3.3 Documentation Comments

**Principle:** Document every schema, field, enum, and union with inline comments.

**Format:** `///` for documentation comments (exported to generated code)

**Example:**

```fbs
namespace k1.agent_fabric;

/// Agent lifecycle state in the K1 agent fabric.
///
/// Represents the current state of an agent in the 6-state FSM:
/// PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
///
/// Size: ~256 bytes (with 3 capabilities)
/// Serialization: <0.3ms
/// Deserialization: <0.05ms (zero-copy)
table AgentState {
  /// Unique agent identifier (ULID format: 26 characters)
  agent_id: string;

  /// Current FSM state (default: PENDING)
  state: AgentLifecycleState = PENDING;

  /// Memory allocated to agent in megabytes (0 = not yet allocated)
  memory_mb: uint32 = 0;

  /// Capabilities granted to agent (empty vector = default capabilities only)
  capabilities: [AgentCapability];

  /// Performance metrics (null = no metrics yet)
  metrics: AgentMetrics;

  /// Unix timestamp (milliseconds) when agent was hired (0 = not yet hired)
  hired_at_ms: int64 = 0;

  /// Unix timestamp (milliseconds) when agent last transitioned state
  last_transition_ms: int64 = 0;
}

/// Agent FSM states (6 states)
enum AgentLifecycleState : uint8 {
  /// Initial state: Agent created, not yet allocated resources
  PENDING = 0,

  /// Transitional state: Agent warming up KV cache, loading model
  WARMING = 1,

  /// Operational state: Agent actively processing tasks
  ACTIVE = 2,

  /// Idle state: Agent waiting for tasks (eligible for eviction)
  IDLE = 3,

  /// Draining state: Agent finishing tasks before termination
  DRAINING = 4,

  /// Terminal state: Agent terminated, resources released
  TERMINATED = 5
}

file_identifier "AGST";
root_type AgentState;
```

---

### 4. Deprecation Strategy

#### 4.1 Deprecation Attribute

**Principle:** Mark deprecated fields with `(deprecated)` attribute instead of removing them.

**Syntax:** `field_name: type (deprecated);`

**Example:**

```fbs
table AgentState {
  agent_id: string;

  // ❌ DON'T DO THIS: Removed field breaks old readers
  // old_field: string;

  // ✅ DO THIS: Deprecated field, use new_field instead
  old_field: string (deprecated);

  // New field added in v1.2
  new_field: string;
}
```

#### 4.2 Deprecation Timeline

**Process:**

1. **Release N:** Add new field, mark old field as `(deprecated)`, update documentation
2. **Release N+1:** Emit warnings when old field is read/written
3. **Release N+2:** Remove old field from generated code (schema remains for compatibility)
4. **Release N+3:** Remove old field from schema file (3-release grace period)

**Example Timeline:**

```
K1 v1.0 (Release N):     AgentState has `memory_mb: uint32`
K1 v1.1 (Release N+1):   Add `memory_bytes: uint64`, deprecate `memory_mb`
K1 v1.2 (Release N+2):   Emit warnings when `memory_mb` is accessed
K1 v1.3 (Release N+3):   Remove `memory_mb` from generated code
K1 v1.4 (Release N+4):   Remove `memory_mb` from schema file (after 3 releases)
```

#### 4.3 Migration Tooling

**Principle:** Provide migration scripts for breaking changes (rare).

**Migration Script Pattern:**

```python
# migrate_agent_state_v1_to_v2.py

def migrate(old_buffer: bytes) -> bytes:
    """Migrate AgentState from v1 (memory_mb) to v2 (memory_bytes)"""
    old_state = AgentState.GetRootAsAgentState(old_buffer, 0)

    builder = flatbuffers.Builder(256)

    # Copy all fields
    agent_id = builder.CreateString(old_state.AgentId().decode())

    # Migrate deprecated field
    memory_bytes = old_state.MemoryMb() * 1024 * 1024  # MB to bytes

    AgentState.Start(builder)
    AgentState.AddAgentId(builder, agent_id)
    AgentState.AddMemoryBytes(builder, memory_bytes)
    new_state = AgentState.End(builder)

    builder.Finish(new_state, file_identifier=b"AGST")
    return bytes(builder.Output())
```

---

### 5. Performance Considerations

#### 5.1 Memory Alignment

**Principle:** Use `force_align` attribute for hot-path structs to enable SIMD optimizations.

**Example:**

```fbs
// Hot-path struct: used in tight loops, SIMD-friendly
struct Vec3 (force_align: 16) {
  x: float32;
  y: float32;
  z: float32;
}

// Not hot-path: alignment overhead not worth it
struct Metadata {
  version: uint32;
  checksum: uint32;
}
```

**When to Use `force_align`:**

- Structs used in audio/video processing (16-byte alignment for SSE/SIMD)
- Structs used in tight loops (cache-line alignment)
- Structs with many float32/float64 fields (vectorized operations)

**When NOT to Use `force_align`:**

- Tables (alignment handled automatically)
- Structs with few fields (<4 scalars)
- Cold-path structs (config, metadata)

#### 5.2 Vtable Compression

**Principle:** FlatBuffers automatically shares vtables across instances. Design schemas to maximize sharing.

**Pattern:**

- **Group related fields together** (same order across instances)
- **Use consistent default values** (enables vtable sharing)
- **Avoid large optional fields** (breaks vtable sharing)

**Example:**

```fbs
// ✅ GOOD: Consistent field order, shared vtable
table AgentState {
  agent_id: string;
  state: AgentLifecycleState = PENDING;  // Consistent default
  memory_mb: uint32 = 0;                 // Consistent default
}

// ❌ BAD: Large optional field breaks vtable sharing
table AgentState {
  agent_id: string;
  state: AgentLifecycleState = PENDING;
  large_data: [ubyte];  // If some instances have 1MB, some have 0, vtables differ
}
```

**Vtable Overhead:**

- **Without sharing:** 16-24 bytes per instance (vtable + size + alignment)
- **With sharing:** 2-4 bytes per instance (vtable offset only)
- **Savings:** 10-20 bytes per instance (for schemas with 5-10 fields)

#### 5.3 String Deduplication

**Principle:** FlatBuffers automatically deduplicates strings within a single buffer. Use this for repeated values.

**Example:**

```fbs
table TaskAnnouncement {
  task_id: string;
  tool_name: string;  // "search_web" repeated 100 times in batch
  agent_ids: [string];  // ["agent_1", "agent_2", "agent_1", "agent_2"] -> deduplicated
}
```

**Deduplication Savings:**

- **Without deduplication:** 100 instances of "search_web" = 100 * 11 bytes = 1,100 bytes
- **With deduplication:** 1 instance of "search_web" + 100 offsets = 11 + (100 * 4) = 411 bytes
- **Savings:** 689 bytes (62% reduction)

#### 5.4 Buffer Pooling

**Principle:** Reuse buffers across serializations to reduce allocations.

**Pattern:**

```python
# Per-thread buffer pool (avoid locking)
_buffer_pools = threading.local()

def get_builder(size_hint: int = 256) -> flatbuffers.Builder:
    """Get a builder from thread-local pool"""
    if not hasattr(_buffer_pools, 'builders'):
        _buffer_pools.builders = {}

    # Size classes: 256B, 1KB, 4KB, 16KB, 64KB
    size_class = 256
    while size_class < size_hint:
        size_class *= 4

    if size_class not in _buffer_pools.builders:
        _buffer_pools.builders[size_class] = flatbuffers.Builder(size_class)

    builder = _buffer_pools.builders[size_class]
    builder.Reset()  # Clear for reuse
    return builder
```

**Pooling Benefits:**

- **Allocation overhead:** ~100-500ns per allocation (amortized to 0 with pooling)
- **Memory pressure:** Reduces GC churn (Python: 10-50% reduction in GC pauses)
- **Cache locality:** Reused buffers stay hot in CPU cache

---

### 6. Schema Examples

#### 6.1 Simple Schema (AgentState)

```fbs
namespace k1.agent_fabric;

/// Agent lifecycle state in the K1 agent fabric.
table AgentState {
  /// Unique agent identifier (ULID format)
  agent_id: string;

  /// Current FSM state
  state: AgentLifecycleState = PENDING;

  /// Memory allocated in megabytes
  memory_mb: uint32 = 0;

  /// Capabilities granted to agent
  capabilities: [AgentCapability];

  /// Performance metrics
  metrics: AgentMetrics;

  /// Unix timestamp (ms) when agent was hired
  hired_at_ms: int64 = 0;
}

/// Agent FSM states (6 states)
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2,
  IDLE = 3,
  DRAINING = 4,
  TERMINATED = 5
}

/// Agent performance metrics
table AgentMetrics {
  /// Number of tasks completed
  tasks_completed: uint32 = 0;

  /// Number of tasks failed
  tasks_failed: uint32 = 0;

  /// Average task duration (milliseconds)
  avg_duration_ms: float32 = 0.0;

  /// P95 task duration (milliseconds)
  p95_duration_ms: float32 = 0.0;
}

file_identifier "AGST";
root_type AgentState;
```

#### 6.2 Complex Schema (SessionState)

```fbs
namespace k1.session_state;

/// SessionState: 6-section memory structure for K1 agents.
///
/// Sections:
/// 1. Beliefs: Semantic understanding (4KB)
/// 2. Scoreboard: Execution tracking (2KB)
/// 3. Control: Orchestration state (1KB)
/// 4. Persona: User profile (8KB)
/// 5. Multimodal: Audio/image refs (2KB)
/// 6. Meta: Session metadata (512B)
///
/// Total size: ~18KB (soft limit: 64KB)
/// Serialization: <1ms
/// Deserialization: <0.1ms (zero-copy)
table SessionState {
  /// Session ID (ULID format)
  session_id: string;

  /// Beliefs section (semantic understanding)
  beliefs: Beliefs;

  /// Scoreboard section (execution tracking)
  scoreboard: Scoreboard;

  /// Control section (orchestration state)
  control: Control;

  /// Persona section (user profile, privacy_band=AMBER)
  persona: Persona;

  /// Multimodal section (audio/image references)
  multimodal: Multimodal;

  /// Meta section (session metadata)
  meta: Meta;

  /// Unix timestamp (ms) when session was created
  created_at_ms: int64 = 0;

  /// Unix timestamp (ms) when session was last updated
  updated_at_ms: int64 = 0;

  /// Total size in bytes (for eviction policy)
  size_bytes: uint32 = 0;
}

/// Beliefs: Semantic understanding (4KB)
table Beliefs {
  /// User intent (classified by planner)
  user_intent: string;

  /// Extracted entities (NER)
  entities: [Entity];

  /// Conversation topics
  topics: [string];

  /// Confidence score (0.0-1.0)
  confidence: float32 = 0.0;
}

/// Entity extracted from user message
table Entity {
  /// Entity text
  text: string;

  /// Entity type (PERSON, LOCATION, DATE, etc.)
  entity_type: string;

  /// Confidence score (0.0-1.0)
  confidence: float32 = 0.0;
}

/// Scoreboard: Execution tracking (2KB)
table Scoreboard {
  /// Total turns in session
  total_turns: uint32 = 0;

  /// Total tool calls
  total_tool_calls: uint32 = 0;

  /// Total cost (USD)
  total_cost_usd: float32 = 0.0;

  /// Average turn latency (ms)
  avg_turn_latency_ms: float32 = 0.0;

  /// Last 10 tool calls
  recent_tool_calls: [ToolCallRecord];
}

/// Tool call record (for scoreboard)
table ToolCallRecord {
  /// Tool name
  tool_name: string;

  /// Execution time (ms)
  execution_time_ms: uint32;

  /// Status (success, error)
  status: string;

  /// Unix timestamp (ms)
  timestamp_ms: int64;
}

/// Control: Orchestration state (1KB)
table Control {
  /// Current turn number
  current_turn: uint32 = 0;

  /// Active agents (agent IDs)
  active_agents: [string];

  /// Pending tasks (task IDs)
  pending_tasks: [string];

  /// Orchestration mode (SERIAL, PARALLEL, SAGA)
  orchestration_mode: string;
}

/// Persona: User profile (8KB, privacy_band=AMBER)
table Persona {
  /// User name (PII)
  name: string;

  /// User preferences
  preferences: [Preference];

  /// Conversation history (last 10 messages)
  recent_messages: [Message];

  /// Privacy band (GREEN, AMBER, RED)
  privacy_band: string = "AMBER";
}

/// User preference
table Preference {
  /// Preference key
  key: string;

  /// Preference value
  value: string;
}

/// Message in conversation history
table Message {
  /// Role (user, assistant, system)
  role: string;

  /// Message content
  content: string;

  /// Unix timestamp (ms)
  timestamp_ms: int64;
}

/// Multimodal: Audio/image references (2KB)
table Multimodal {
  /// Audio clip references
  audio_refs: [AudioRef];

  /// Image references
  image_refs: [ImageRef];
}

/// Audio clip reference
table AudioRef {
  /// Audio clip ID
  clip_id: string;

  /// Storage URI (S3, local file)
  uri: string;

  /// Duration (milliseconds)
  duration_ms: uint32;
}

/// Image reference
table ImageRef {
  /// Image ID
  image_id: string;

  /// Storage URI (S3, local file)
  uri: string;

  /// Width (pixels)
  width: uint32;

  /// Height (pixels)
  height: uint32;
}

/// Meta: Session metadata (512B)
table Meta {
  /// K1 version
  k1_version: string;

  /// Client version
  client_version: string;

  /// Cognitive trace ID (for tracing)
  trace_id: string;

  /// Session tags
  tags: [string];
}

file_identifier "SEST";
root_type SessionState;
```

#### 6.3 Union Schema (PlanNode)

```fbs
namespace k1.planner;

/// PlanNode: A step in the 4-stage planning pipeline.
table PlanNode {
  /// Node ID (ULID format)
  node_id: string;

  /// Parent node ID (null = root node)
  parent_id: string;

  /// Node type (polymorphic)
  node_type: PlanNodeType;

  /// Validation status
  status: ValidationStatus = NOT_VALIDATED;

  /// Arbiter approval required
  arbiter_approval_required: bool = false;

  /// Arbiter decision (null = not yet reviewed)
  arbiter_decision: string;
}

/// Polymorphic node types
union PlanNodeType {
  LLMInference,
  ToolCall,
  MemoryRead,
  MemoryWrite,
  Loop,
  Condition
}

/// LLM inference node
table LLMInference {
  /// Model ID (gemma-2b, gpt-4o-mini, gpt-4o)
  model_id: string;

  /// Prompt template
  prompt: string;

  /// Max tokens
  max_tokens: uint32 = 100;

  /// Temperature
  temperature: float32 = 0.7;
}

/// Tool call node
table ToolCall {
  /// Tool name (search_web, book_hotel, etc.)
  tool_name: string;

  /// Tool arguments (JSON)
  args: string;

  /// Timeout (milliseconds)
  timeout_ms: uint32 = 3000;
}

/// Memory read node
table MemoryRead {
  /// Section (beliefs, scoreboard, control, etc.)
  section: string;

  /// Key (null = read entire section)
  key: string;
}

/// Memory write node
table MemoryWrite {
  /// Section (beliefs, scoreboard, control, etc.)
  section: string;

  /// Key
  key: string;

  /// Value (JSON)
  value: string;
}

/// Loop node (for repetition)
table Loop {
  /// Loop body (node IDs)
  body: [string];

  /// Max iterations
  max_iterations: uint32 = 10;

  /// Exit condition (expression)
  exit_condition: string;
}

/// Condition node (if/else)
table Condition {
  /// Condition expression
  condition: string;

  /// Then branch (node IDs)
  then_branch: [string];

  /// Else branch (node IDs)
  else_branch: [string];
}

/// Validation status
enum ValidationStatus : uint8 {
  NOT_VALIDATED = 0,
  VALID = 1,
  INVALID = 2,
  ARBITER_REVIEW = 3
}

file_identifier "PLND";
root_type PlanNode;
```

---

## Consequences

### Positive

1. **Consistency:** All 76 K1 schemas follow same design patterns (forward compatibility, naming, documentation)
2. **Maintainability:** Clear deprecation strategy prevents breaking changes
3. **Performance:** Alignment, vtable compression, string deduplication optimize memory and speed
4. **Discoverability:** Namespace hierarchy and file organization make schemas easy to find
5. **Type Safety:** Generated code with type hints (Python), concepts (C++), traits (Rust)

### Negative

1. **Learning Curve:** Team must learn FlatBuffers schema language and tooling
2. **Verbosity:** Schema files require more boilerplate than JSON (but gain type safety)
3. **Tooling Dependency:** Requires `flatc` compiler in build pipeline (adds complexity)
4. **Migration Cost:** Existing JSON/Protocol Buffers code must be ported (one-time cost)

### Risks

1. **Schema Bloat:** 76 schemas may grow over time without discipline (mitigation: ADR reviews)
2. **Breaking Changes:** Accidental field removal breaks compatibility (mitigation: CI/CD validation)
3. **Performance Regression:** Improper use of force_align or large optional fields (mitigation: benchmarking)

---

## Implementation Notes

### Schema Validation (CI/CD)

**Pre-commit Hook:**

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Validate all FlatBuffers schemas
flatc --schema -o /tmp k1/schemas/**/*.fbs
if [ $? -ne 0 ]; then
  echo "FlatBuffers schema validation failed"
  exit 1
fi

# Check for breaking changes
python scripts/check_schema_breaking_changes.py
if [ $? -ne 0 ]; then
  echo "Breaking schema changes detected"
  exit 1
fi
```

**Breaking Change Detection:**

```python
# scripts/check_schema_breaking_changes.py

def check_breaking_changes(old_schema: str, new_schema: str) -> List[str]:
    """Check for breaking changes between schema versions"""
    old_ast = parse_schema(old_schema)
    new_ast = parse_schema(new_schema)

    errors = []

    for table in old_ast.tables:
        new_table = new_ast.get_table(table.name)
        if not new_table:
            errors.append(f"Table {table.name} removed (BREAKING)")
            continue

        for field in table.fields:
            new_field = new_table.get_field(field.name)
            if not new_field:
                errors.append(f"Field {table.name}.{field.name} removed (BREAKING)")
            elif new_field.type != field.type:
                errors.append(f"Field {table.name}.{field.name} type changed (BREAKING)")

    return errors
```

### Schema Generation

**Build Script:**

```bash
#!/bin/bash
# scripts/generate_schemas.sh

# Generate Python bindings
flatc --python -o k1/schemas/generated/python k1/schemas/**/*.fbs

# Generate C++ bindings
flatc --cpp -o k1/schemas/generated/cpp k1/schemas/**/*.fbs

# Generate Rust bindings
flatc --rust -o k1/schemas/generated/rust k1/schemas/**/*.fbs

# Run type checking
mypy k1/schemas/generated/python --strict
```

### Testing Strategy (WARD)

**Schema Serialization Tests:**

```python
from ward import test
import flatbuffers
from k1.schemas.generated.python.agent_fabric import AgentState

@test("AgentState serialization roundtrip")
def _():
    builder = flatbuffers.Builder(256)

    # Create AgentState
    agent_id = builder.CreateString("agent_xyz")
    AgentState.Start(builder)
    AgentState.AddAgentId(builder, agent_id)
    AgentState.AddState(builder, AgentLifecycleState.ACTIVE)
    AgentState.AddMemoryMb(builder, 512)
    state = AgentState.End(builder)

    builder.Finish(state, file_identifier=b"AGST")
    buf = bytes(builder.Output())

    # Deserialize (zero-copy)
    deserialized = AgentState.GetRootAsAgentState(buf, 0)

    assert deserialized.AgentId().decode() == "agent_xyz"
    assert deserialized.State() == AgentLifecycleState.ACTIVE
    assert deserialized.MemoryMb() == 512

@test("AgentState forward compatibility (ignore unknown fields)")
def _():
    # Simulate old schema with new field
    builder = flatbuffers.Builder(256)
    agent_id = builder.CreateString("agent_xyz")

    AgentState.Start(builder)
    AgentState.AddAgentId(builder, agent_id)
    AgentState.AddState(builder, AgentLifecycleState.ACTIVE)
    # Future field: AddNewField(builder, value) - ignored by old code
    state = AgentState.End(builder)

    builder.Finish(state, file_identifier=b"AGST")
    buf = bytes(builder.Output())

    # Old code can still deserialize
    deserialized = AgentState.GetRootAsAgentState(buf, 0)
    assert deserialized.AgentId().decode() == "agent_xyz"
```

---

## References

- **FlatBuffers Documentation:** <https://google.github.io/flatbuffers/>
- **FlatBuffers Schema Language:** <https://google.github.io/flatbuffers/flatbuffers_guide_writing_schema.html>
- **FlatBuffers Internals:** <https://google.github.io/flatbuffers/flatbuffers_internals.html>
- **Protocol Buffers Comparison:** <https://google.github.io/flatbuffers/flatbuffers_benchmarks.html>
- **ADR-0001:** K0-K1 Kernel Split (FlatBuffers for K0 ↔ K1 communication)
- **ADR-0017:** SessionState 6-Section Design (SessionState schemas)
- **ADR-0019:** FlatBuffers SessionState Serialization (<1ms budget)

---

**Status:** ✅ Accepted
**Next ADR:** [ADR-0011b: FlatBuffers Code Generation & Integration](./0011b-flatbuffers-code-generation-integration.md)