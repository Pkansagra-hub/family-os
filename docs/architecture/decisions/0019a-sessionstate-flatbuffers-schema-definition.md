# ADR-0019a: SessionState FlatBuffers Schema Definition

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0019 (FlatBuffers SessionState Serialization)](0019-flatbuffers-sessionstate-serialization.md)
**Category:** State Management (Layer 2) - Serialization
**Related ADRs:**
- [ADR-0011 (FlatBuffers Serialization)](0011-flatbuffers-serialization.md)
- [ADR-0012 (76 FlatBuffers Schemas)](0012-76-flatbuffers-schemas.md)
- [ADR-0013 (Schema Versioning SemVer 2.0)](0013-schema-versioning-semver-2.md)
- [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
- [ADR-0017a-f (6 Section Sub-ADRs)](0017a-beliefs-section-user-facts-preferences.md)

---

## Context

### Problem Statement

K1's SessionState (ADR-0017) consists of 6 sections totaling 30-56KB per session:

1. **Beliefs** (10-20KB): User facts, preferences (LRU eviction)
2. **Scoreboard** (4-8KB): Common ground, referents, QUD stack
3. **Control** (8-12KB): Agent leases, flow state, turn locks
4. **Persona** (2-4KB): Personality traits, style preferences
5. **Multimodal** (4-8KB): Audio/vision pointers to K0 blob storage
6. **Meta** (2-4KB): Telemetry, performance metrics

To persist this state to K0 storage and enable cross-session recovery, we need:

1. **FlatBuffers Schemas:** Type-safe, zero-copy serialization for all 6 sections
2. **Root Schema:** SessionStateRoot container with all sections + metadata
3. **Delta Schema:** SessionStateDelta for incremental updates (only changed sections)
4. **Schema Versioning:** SemVer 2.0 compatibility per ADR-0013
5. **Size Efficiency:** Minimal overhead (<5% of payload size)

**Key Challenges:**

- **Schema Complexity:** 6 sections with 50+ distinct types (Fact, Entity, AgentLease, Trait, etc.)
- **Delta Representation:** Efficiently encode "section changed" vs "section unchanged" (nullable fields)
- **Backward Compatibility:** Support schema evolution (v1.0.0 → v1.1.0) without breaking K0 storage
- **Nested Tables:** Deep nesting (Control → AgentLease → Capabilities → CapabilitySet)
- **Performance:** Schema size directly impacts serialization/deserialization latency (<1ms budget)

### Current Landscape

**Industry Serialization Schema Patterns:**

1. **Protocol Buffers (Google)**:
   - **Pattern:** .proto files with message definitions, oneof for unions
   - **Advantage:** Mature, excellent tooling, language support
   - **Disadvantage:** Not zero-copy (requires parsing into objects)

2. **Apache Avro**:
   - **Pattern:** JSON schemas with union types, schema evolution via readers/writers
   - **Advantage:** Schema evolution (add fields without breaking readers)
   - **Disadvantage:** Slower than FlatBuffers (parsing overhead)

3. **Cap'n Proto**:
   - **Pattern:** Schema language with zero-copy promise pointers
   - **Advantage:** True zero-copy (even for nested data)
   - **Disadvantage:** Less mature than FlatBuffers, smaller ecosystem

4. **FlatBuffers (Google)**:
   - **Pattern:** .fbs schema files with tables, unions, vectors
   - **Advantage:** Zero-copy deserialization, <1μs access time
   - **Disadvantage:** Requires schema upfront (no dynamic schemas)

### K1 Requirements

**SessionState FlatBuffers Schema Properties:**

1. **6 Section Schemas:** One .fbs file per section (beliefs, scoreboard, control, persona, multimodal, meta)
2. **Root Schema:** SessionStateRoot table with all 6 sections + session_id + metadata
3. **Delta Schema:** SessionStateDelta table with nullable sections (only serialize changed sections)
4. **Schema Versioning:** schema_version field (SemVer 2.0 string, e.g., "1.0.0")
5. **Size Efficiency:** Total schema overhead <2KB (metadata + nullability flags)

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Schema Compilation | <500ms | `flatc` compile time for all 6 section schemas |
| Root Table Size | <2KB | Metadata overhead (session_id, timestamps, schema_version) |
| Delta Table Size | <1KB | Only changed sections + change flags |
| Schema Validation | <100μs | Runtime validation (schema_version check) |

---

## Decision

We will implement **SessionState FlatBuffers schemas** with:

1. **6 Section Schemas:** One .fbs file per section (beliefs, scoreboard, control, persona, multimodal, meta)
2. **Root Schema:** SessionStateRoot table containing all 6 sections + metadata
3. **Delta Schema:** SessionStateDelta table with nullable sections (only changed sections)
4. **Versioning:** schema_version field (SemVer 2.0) with compatibility matrix
5. **Namespace:** `K1.SessionState` namespace for all schemas

### Schema Organization

```
k1/schemas/session_state/
├── session_state_root.fbs           # Root schema (all 6 sections)
├── session_state_delta.fbs          # Delta schema (only changed sections)
├── sections/
│   ├── beliefs_section.fbs          # Beliefs section (facts, preferences)
│   ├── scoreboard_section.fbs       # Scoreboard section (entities, QUD)
│   ├── control_section.fbs          # Control section (agent leases, flow)
│   ├── persona_section.fbs          # Persona section (personality, style)
│   ├── multimodal_section.fbs       # Multimodal section (audio, vision)
│   └── meta_section.fbs             # Meta section (telemetry, metrics)
├── types/
│   ├── fact.fbs                     # Fact type (key-value with confidence)
│   ├── entity.fbs                   # Entity type (referent, salience)
│   ├── agent_lease.fbs              # AgentLease type (agent_id, expiry)
│   ├── personality_trait.fbs        # PersonalityTrait type (trait, value)
│   ├── audio_buffer.fbs             # AudioBuffer type (storage pointer)
│   ├── vision_embedding.fbs         # VisionEmbedding type (CLIP embedding)
│   └── performance_metrics.fbs      # PerformanceMetrics type (TTFT, E2E)
└── enums/
    ├── privacy_band.fbs             # PrivacyBand enum (GREEN, AMBER, RED)
    ├── agent_state.fbs              # AgentState enum (ACTIVE, IDLE, etc.)
    └── flow_phase.fbs               # FlowPhase enum (NEGOTIATION, SELECTION, EXECUTION)
```

---

## Implementation

### Root Schema: SessionStateRoot

```flatbuffers
// k1/schemas/session_state/session_state_root.fbs
namespace K1.SessionState;

include "sections/beliefs_section.fbs";
include "sections/scoreboard_section.fbs";
include "sections/control_section.fbs";
include "sections/persona_section.fbs";
include "sections/multimodal_section.fbs";
include "sections/meta_section.fbs";

// Root container for entire SessionState (all 6 sections)
table SessionStateRoot {
  // Schema versioning (SemVer 2.0)
  schema_version: string (required, id: 0);  // Example: "1.0.0"

  // Session identification
  session_id: string (required, id: 1);      // Unique session ID (UUID)
  cognitive_trace_id: string (id: 2);         // Trace ID for observability

  // 6 SessionState sections (from ADR-0017)
  beliefs: BeliefsSection (id: 10);           // User facts, preferences (10-20KB)
  scoreboard: ScoreboardSection (id: 11);     // Common ground, referents (4-8KB)
  control: ControlSection (id: 12);           // Agent leases, flow state (8-12KB)
  persona: PersonaSection (id: 13);           // Personality, style (2-4KB)
  multimodal: MultimodalSection (id: 14);     // Audio/vision pointers (4-8KB)
  meta: MetaSection (id: 15);                 // Telemetry, metrics (2-4KB)

  // Size tracking (for eviction strategy ADR-0018)
  total_size_bytes: int (id: 20);             // Total SessionState size in bytes
  beliefs_size_kb: float (id: 21);            // Beliefs section size (KB)
  scoreboard_size_kb: float (id: 22);         // Scoreboard section size (KB)
  control_size_kb: float (id: 23);            // Control section size (KB)
  persona_size_kb: float (id: 24);            // Persona section size (KB)
  multimodal_size_kb: float (id: 25);         // Multimodal section size (KB)
  meta_size_kb: float (id: 26);               // Meta section size (KB)

  // Timestamps (Unix milliseconds)
  created_at_ms: long (id: 30);               // Session creation timestamp
  last_updated_ms: long (id: 31);             // Last SessionState update
  last_checkpointed_ms: long (id: 32);        // Last K0 checkpoint timestamp

  // Eviction tracking (from ADR-0018)
  tier1_eviction_count: int (id: 40);         // Number of Tier 1 evictions
  tier2_eviction_count: int (id: 41);         // Number of Tier 2 evictions
  oom_risk_level: float (id: 42);             // OOM risk (0.0-1.0, >0.8 = high risk)
}

root_type SessionStateRoot;
```

### Delta Schema: SessionStateDelta

```flatbuffers
// k1/schemas/session_state/session_state_delta.fbs
namespace K1.SessionState;

include "sections/beliefs_section.fbs";
include "sections/scoreboard_section.fbs";
include "sections/control_section.fbs";
include "sections/persona_section.fbs";
include "sections/multimodal_section.fbs";
include "sections/meta_section.fbs";

// Delta representation (only changed sections)
table SessionStateDelta {
  // Schema versioning (SemVer 2.0)
  schema_version: string (required, id: 0);  // Example: "1.0.0"

  // Session identification
  session_id: string (required, id: 1);      // Unique session ID (UUID)
  cognitive_trace_id: string (id: 2);         // Trace ID for observability

  // Change tracking
  changed_sections: [string] (id: 10);        // List of changed section names
                                              // Example: ["beliefs", "control"]

  // 6 SessionState sections (NULLABLE - only serialize if changed)
  beliefs: BeliefsSection (id: 20);           // null if not changed
  scoreboard: ScoreboardSection (id: 21);     // null if not changed
  control: ControlSection (id: 22);           // null if not changed
  persona: PersonaSection (id: 23);           // null if not changed
  multimodal: MultimodalSection (id: 24);     // null if not changed
  meta: MetaSection (id: 25);                 // null if not changed

  // Delta metadata
  delta_size_bytes: int (id: 30);             // Size of changed sections only
  timestamp_ms: long (id: 31);                // Delta generation timestamp
  sequence_number: long (id: 32);             // Sequence number (WAL ordering)
}

root_type SessionStateDelta;
```

---

## Section Schemas

### 1. Beliefs Section Schema

```flatbuffers
// k1/schemas/session_state/sections/beliefs_section.fbs
namespace K1.SessionState;

include "types/fact.fbs";
include "enums/privacy_band.fbs";

// Beliefs section: User facts, preferences (ADR-0017a)
table BeliefsSection {
  // Facts storage (HashMap: key → Fact)
  facts: [Fact] (id: 0);                      // Vector of facts (key-value pairs)

  // LRU eviction tracking
  lru_order: [string] (id: 1);                // Keys in LRU order (oldest first)
  total_facts: int (id: 2);                   // Total number of facts

  // Privacy classification
  privacy_band: PrivacyBand (id: 10);         // GREEN/AMBER/RED classification

  // Size tracking
  section_size_bytes: int (id: 20);           // Beliefs section size
  last_eviction_ms: long (id: 21);            // Last eviction timestamp
}
```

```flatbuffers
// k1/schemas/session_state/types/fact.fbs
namespace K1.SessionState;

// Fact type: Key-value pair with confidence (ADR-0017a)
table Fact {
  key: string (required, id: 0);              // Fact key (e.g., "user_name")
  value: string (required, id: 1);            // Fact value (e.g., "Alice")
  confidence: float (id: 2);                  // Confidence score (0.0-1.0)

  // Timestamps (Unix milliseconds)
  created_at_ms: long (id: 10);               // Fact creation timestamp
  last_accessed_ms: long (id: 11);            // Last access (LRU tracking)
  updated_at_ms: long (id: 12);               // Last update timestamp

  // Provenance
  source: string (id: 20);                    // Fact source (e.g., "user_input", "llm_inference")
  turn_index: int (id: 21);                   // Turn where fact was created
}
```

### 2. Scoreboard Section Schema

```flatbuffers
// k1/schemas/session_state/sections/scoreboard_section.fbs
namespace K1.SessionState;

include "types/entity.fbs";
include "types/qud_question.fbs";

// Scoreboard section: Common ground, referents, QUD (ADR-0017b)
table ScoreboardSection {
  // Entity tracking (referent resolution)
  entities: [Entity] (id: 0);                 // Vector of entities (referents)
  entity_count: int (id: 1);                  // Total number of entities

  // QUD stack (Question Under Discussion)
  qud_stack: [QUDQuestion] (id: 10);          // Priority-ordered questions (top = index 0)
  current_qud_id: string (id: 11);            // Currently active question

  // Common ground (shared knowledge)
  common_ground_items: [string] (id: 20);     // Established common ground items

  // Size tracking
  section_size_bytes: int (id: 30);           // Scoreboard section size
}
```

```flatbuffers
// k1/schemas/session_state/types/entity.fbs
namespace K1.SessionState;

// Entity type: Referent with salience decay (ADR-0017b)
table Entity {
  entity_id: string (required, id: 0);        // Unique entity ID (UUID)
  entity_type: string (id: 1);                // Entity type (e.g., "person", "document")
  surface_form: string (id: 2);               // Surface form (e.g., "Alice", "the report")

  // Salience tracking
  salience: float (id: 10);                   // Salience score (0.0-1.0)
  decay_rate: float (id: 11);                 // Exponential decay rate (e.g., 0.9)
  turns_since_mention: int (id: 12);          // Turns since last mention

  // Attributes
  attributes: [EntityAttribute] (id: 20);     // Entity attributes (key-value pairs)

  // Timestamps
  created_at_ms: long (id: 30);               // Entity creation timestamp
  last_mentioned_ms: long (id: 31);           // Last mention timestamp
}

table EntityAttribute {
  key: string (required, id: 0);              // Attribute key (e.g., "role", "location")
  value: string (required, id: 1);            // Attribute value (e.g., "manager", "NYC")
}
```

```flatbuffers
// k1/schemas/session_state/types/qud_question.fbs
namespace K1.SessionState;

// QUD question type (Question Under Discussion, ADR-0017b)
table QUDQuestion {
  qud_id: string (required, id: 0);           // Unique question ID (UUID)
  question_text: string (id: 1);              // Question text (e.g., "What is user's favorite color?")
  priority: float (id: 2);                    // Priority score (0.0-1.0, higher = more urgent)
  status: QUDStatus (id: 3);                  // OPEN, ANSWERED, ABANDONED

  // Resolution
  answer: string (id: 10);                    // Answer (null if OPEN)
  answered_at_ms: long (id: 11);              // Answer timestamp

  // Timestamps
  created_at_ms: long (id: 20);               // Question creation timestamp
}

enum QUDStatus : byte {
  OPEN = 0,
  ANSWERED = 1,
  ABANDONED = 2,
}
```

### 3. Control Section Schema

```flatbuffers
// k1/schemas/session_state/sections/control_section.fbs
namespace K1.SessionState;

include "types/agent_lease.fbs";
include "types/flow_state.fbs";
include "types/turn_lock.fbs";
include "enums/agent_state.fbs";

// Control section: Agent leases, flow state, turn locks (ADR-0017c)
table ControlSection {
  // Agent management
  active_agents: [AgentLease] (id: 0);        // Currently active agent leases
  max_agents_per_session: int (id: 1);        // Max concurrent agents (default: 3)

  // Flow state (3-phase orchestration)
  flow_state: FlowState (id: 10);             // Current flow state (negotiation/selection/execution)

  // Turn management
  turn_lock: TurnLock (id: 20);               // Turn lock (prevent concurrent turns)
  current_turn_index: int (id: 21);           // Current turn index (monotonic)

  // Size tracking
  section_size_bytes: int (id: 30);           // Control section size
}
```

```flatbuffers
// k1/schemas/session_state/types/agent_lease.fbs
namespace K1.SessionState;

include "types/capability_set.fbs";
include "enums/agent_state.fbs";

// Agent lease type: Agent with expiration (ADR-0017c)
table AgentLease {
  agent_id: string (required, id: 0);         // Unique agent ID (UUID)
  agent_name: string (id: 1);                 // Agent name (e.g., "planner", "tool_runner")
  state: AgentState (id: 2);                  // PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED

  // Lease management
  lease_start_ms: long (id: 10);              // Lease start timestamp
  lease_expiry_ms: long (id: 11);             // Lease expiry timestamp (30s default)
  renewal_count: int (id: 12);                // Number of lease renewals

  // Capabilities
  capabilities: CapabilitySet (id: 20);       // Agent capabilities (TOOL_CALL, LLM_INFERENCE, etc.)

  // Performance metrics
  avg_latency_ms: float (id: 30);             // Average agent latency (P95)
  success_rate: float (id: 31);               // Success rate (0.0-1.0)
}
```

```flatbuffers
// k1/schemas/session_state/types/capability_set.fbs
namespace K1.SessionState;

// Capability set: Agent capabilities (ADR-0002d)
table CapabilitySet {
  capabilities: [Capability] (id: 0);         // Vector of capabilities
}

enum Capability : byte {
  TOOL_CALL = 0,
  LLM_INFERENCE = 1,
  MEMORY_READ = 2,
  MEMORY_WRITE = 3,
  SESSION_STATE_READ = 4,
  SESSION_STATE_WRITE = 5,
  K0_READ = 6,
  K0_WRITE = 7,
}
```

```flatbuffers
// k1/schemas/session_state/types/flow_state.fbs
namespace K1.SessionState;

include "enums/flow_phase.fbs";

// Flow state: 3-phase orchestration (ADR-0017c)
table FlowState {
  current_phase: FlowPhase (id: 0);           // NEGOTIATION/SELECTION/EXECUTION
  phase_start_ms: long (id: 1);               // Phase start timestamp

  // Phase-specific data
  proposals: [string] (id: 10);               // Negotiation proposals (agent_id list)
  selected_agent_id: string (id: 11);         // Selected agent (from selection phase)
  execution_started_ms: long (id: 12);        // Execution start timestamp
}
```

```flatbuffers
// k1/schemas/session_state/enums/flow_phase.fbs
namespace K1.SessionState;

// Flow phase enum (3-phase orchestration, ADR-0017c)
enum FlowPhase : byte {
  NEGOTIATION = 0,     // Phase 1: Agents propose capabilities
  SELECTION = 1,       // Phase 2: Orchestrator selects best agent
  EXECUTION = 2,       // Phase 3: Selected agent executes task
}
```

```flatbuffers
// k1/schemas/session_state/types/turn_lock.fbs
namespace K1.SessionState;

// Turn lock: Prevent concurrent turns (ADR-0017c)
table TurnLock {
  locked: bool (id: 0);                       // Lock status (true = locked)
  lock_holder_turn_id: string (id: 1);        // Turn ID holding lock
  locked_at_ms: long (id: 2);                 // Lock acquisition timestamp
  lock_timeout_ms: long (id: 3);              // Lock timeout (5s default)
}
```

```flatbuffers
// k1/schemas/session_state/enums/agent_state.fbs
namespace K1.SessionState;

// Agent state enum (ADR-0002, agent lifecycle FSM)
enum AgentState : byte {
  PENDING = 0,         // Initial state (not yet warmed)
  WARMING = 1,         // Loading model/dependencies (200ms timeout)
  ACTIVE = 2,          // Ready to execute tasks
  IDLE = 3,            // No tasks (60s idle timeout)
  DRAINING = 4,        // Completing final tasks before termination
  TERMINATED = 5,      // Terminated (lease expired or crash)
}
```

### 4. Persona Section Schema

```flatbuffers
// k1/schemas/session_state/sections/persona_section.fbs
namespace K1.SessionState;

include "types/personality_trait.fbs";

// Persona section: Personality, style preferences (ADR-0017d)
table PersonaSection {
  // Personality traits
  traits: [PersonalityTrait] (id: 0);         // Vector of personality traits

  // Style preferences
  tone: string (id: 10);                      // Tone (e.g., "casual", "professional")
  verbosity: string (id: 11);                 // Verbosity (e.g., "brief", "detailed")
  formality: string (id: 12);                 // Formality (e.g., "informal", "formal")

  // LLM prompt generation
  system_prompt_template: string (id: 20);    // Template for system prompt injection

  // Size tracking
  section_size_bytes: int (id: 30);           // Persona section size
}
```

```flatbuffers
// k1/schemas/session_state/types/personality_trait.fbs
namespace K1.SessionState;

// Personality trait type (ADR-0017d)
table PersonalityTrait {
  trait_name: string (required, id: 0);       // Trait name (e.g., "friendliness")
  trait_value: float (id: 1);                 // Trait value (0.0-1.0)
  description: string (id: 2);                // Human-readable description
}
```

### 5. Multimodal Section Schema

```flatbuffers
// k1/schemas/session_state/sections/multimodal_section.fbs
namespace K1.SessionState;

include "types/audio_buffer.fbs";
include "types/vision_embedding.fbs";

// Multimodal section: Audio/vision pointers (ADR-0017e)
table MultimodalSection {
  // Audio buffers (pointers to K0 blob storage)
  audio_buffers: [AudioBuffer] (id: 0);       // Vector of audio buffer pointers
  max_audio_buffers: int (id: 1);             // Max audio buffers (default: 5)

  // Vision embeddings (CLIP embeddings)
  vision_embeddings: [VisionEmbedding] (id: 10); // Vector of vision embeddings
  max_vision_embeddings: int (id: 11);        // Max vision embeddings (default: 10)

  // LRU eviction tracking
  audio_lru_order: [string] (id: 20);         // Audio buffer IDs in LRU order
  vision_lru_order: [string] (id: 21);        // Vision embedding IDs in LRU order

  // Size tracking
  section_size_bytes: int (id: 30);           // Multimodal section size
}
```

```flatbuffers
// k1/schemas/session_state/types/audio_buffer.fbs
namespace K1.SessionState;

// Audio buffer type: Pointer to K0 blob storage (ADR-0017e)
table AudioBuffer {
  buffer_id: string (required, id: 0);        // Unique buffer ID (UUID)
  storage_pointer: string (id: 1);            // K0 blob storage pointer (e.g., "k0://session_123/audio/buffer_456")
  duration_ms: int (id: 2);                   // Audio duration (milliseconds)
  sample_rate: int (id: 3);                   // Sample rate (e.g., 16000 Hz)

  // Metadata
  encoding: string (id: 10);                  // Encoding format (e.g., "pcm_16", "opus")
  compressed: bool (id: 11);                  // Compression flag (zstd)

  // Timestamps
  created_at_ms: long (id: 20);               // Buffer creation timestamp
  last_accessed_ms: long (id: 21);            // Last access (LRU tracking)
}
```

```flatbuffers
// k1/schemas/session_state/types/vision_embedding.fbs
namespace K1.SessionState;

// Vision embedding type: CLIP embedding (ADR-0017e)
table VisionEmbedding {
  embedding_id: string (required, id: 0);     // Unique embedding ID (UUID)
  storage_pointer: string (id: 1);            // K0 blob storage pointer (e.g., "k0://session_123/vision/embedding_789")
  embedding_dim: int (id: 2);                 // Embedding dimension (e.g., 512 for CLIP)

  // Metadata
  image_width: int (id: 10);                  // Original image width
  image_height: int (id: 11);                 // Original image height
  model: string (id: 12);                     // Model used (e.g., "CLIP-ViT-B/32")

  // Timestamps
  created_at_ms: long (id: 20);               // Embedding creation timestamp
  last_accessed_ms: long (id: 21);            // Last access (LRU tracking)
}
```

### 6. Meta Section Schema

```flatbuffers
// k1/schemas/session_state/sections/meta_section.fbs
namespace K1.SessionState;

include "types/performance_metrics.fbs";

// Meta section: Telemetry, performance metrics (ADR-0017f)
table MetaSection {
  // Session metadata
  session_id: string (required, id: 0);       // Unique session ID (UUID)
  cognitive_trace_id: string (id: 1);         // Trace ID for observability

  // Performance metrics
  performance_metrics: PerformanceMetrics (id: 10);

  // Turn tracking
  total_turns: int (id: 20);                  // Total turns in session
  successful_turns: int (id: 21);             // Successful turns
  failed_turns: int (id: 22);                 // Failed turns

  // Session lifecycle
  session_start_ms: long (id: 30);            // Session start timestamp
  last_turn_ms: long (id: 31);                // Last turn timestamp
  terminated: bool (id: 32);                  // Termination flag
  termination_reason: string (id: 33);        // Termination reason (e.g., "OOM", "timeout")

  // Size tracking
  section_size_bytes: int (id: 40);           // Meta section size
}
```

```flatbuffers
// k1/schemas/session_state/types/performance_metrics.fbs
namespace K1.SessionState;

// Performance metrics type (ADR-0017f)
table PerformanceMetrics {
  // Latency metrics (P95, milliseconds)
  avg_ttft_ms: float (id: 0);                 // Average Time-To-First-Token
  avg_e2e_latency_ms: float (id: 1);          // Average end-to-end turn latency
  avg_tool_call_ms: float (id: 2);            // Average tool call latency

  // Throughput metrics
  tokens_per_second: float (id: 10);          // Token generation rate
  turns_per_minute: float (id: 11);           // Turn rate

  // Error metrics
  error_rate: float (id: 20);                 // Error rate (0.0-1.0)
  timeout_rate: float (id: 21);               // Timeout rate (0.0-1.0)
}
```

---

## Privacy Band Enum

```flatbuffers
// k1/schemas/session_state/enums/privacy_band.fbs
namespace K1.SessionState;

// Privacy band enum (ADR-0006, privacy classification)
enum PrivacyBand : byte {
  GREEN = 0,           // Low privacy risk (general knowledge)
  AMBER = 1,           // Medium privacy risk (personal preferences)
  RED = 2,             // High privacy risk (PII, sensitive data)
}
```

---

## Schema Compilation

### FlatBuffers Compiler Invocation

```bash
# Compile all SessionState schemas
flatc --python \
  --gen-object-api \
  --gen-mutable \
  -o k1/generated/session_state \
  k1/schemas/session_state/session_state_root.fbs \
  k1/schemas/session_state/session_state_delta.fbs \
  k1/schemas/session_state/sections/*.fbs \
  k1/schemas/session_state/types/*.fbs \
  k1/schemas/session_state/enums/*.fbs
```

### Generated Python API

```python
# Generated by FlatBuffers compiler
from K1.SessionState import SessionStateRoot, SessionStateDelta
from K1.SessionState import BeliefsSection, ScoreboardSection, ControlSection
from K1.SessionState import PersonaSection, MultimodalSection, MetaSection
from K1.SessionState import Fact, Entity, AgentLease, PersonalityTrait
from K1.SessionState import AudioBuffer, VisionEmbedding, PerformanceMetrics
from K1.SessionState import PrivacyBand, AgentState, FlowPhase

# Example: Create SessionStateRoot
import flatbuffers

builder = flatbuffers.Builder(initial_size=65536)

# Build beliefs section
# ... (build each section)

# Build root
SessionStateRoot.Start(builder)
SessionStateRoot.AddSchemaVersion(builder, builder.CreateString("1.0.0"))
SessionStateRoot.AddSessionId(builder, builder.CreateString("session_123"))
SessionStateRoot.AddBeliefs(builder, beliefs_offset)
# ... add other sections
root_offset = SessionStateRoot.End(builder)

builder.Finish(root_offset)
session_state_bytes = bytes(builder.Output())
```

---

## Schema Versioning (SemVer 2.0)

### Version Compatibility Matrix

| K1 Version | Schema Version | Compatibility | Breaking Changes |
|------------|---------------|---------------|------------------|
| v1.0.0 | 1.0.0 | ✅ Baseline | - |
| v1.1.0 | 1.1.0 | ✅ Backward compatible | Add optional field: `audio_buffers.bitrate` |
| v1.2.0 | 1.2.0 | ✅ Backward compatible | Add optional table: `BeliefsSection.preferences` |
| v2.0.0 | 2.0.0 | ❌ Breaking | Remove field: `Meta.deprecated_field` |

### Schema Evolution Rules (ADR-0013)

1. **Add Optional Fields:** Backward compatible (schema v1.0.0 → v1.1.0)
2. **Add Optional Tables:** Backward compatible (schema v1.0.0 → v1.2.0)
3. **Remove Fields:** Breaking (schema v1.x.x → v2.0.0, major version bump)
4. **Change Field Types:** Breaking (schema v1.x.x → v2.0.0, major version bump)

### Runtime Version Check

```python
# k1/session_state/serialization/version_checker.py
from packaging import version

class SchemaVersionChecker:
    """Check FlatBuffers schema version compatibility"""

    CURRENT_SCHEMA_VERSION = "1.0.0"

    def check_compatibility(self, schema_version: str) -> bool:
        """Check if schema version is compatible with current K1 version

        Args:
            schema_version: Schema version from SessionStateRoot.schema_version

        Returns:
            True if compatible, False otherwise
        """
        current = version.parse(self.CURRENT_SCHEMA_VERSION)
        incoming = version.parse(schema_version)

        # Major version must match (no breaking changes)
        if current.major != incoming.major:
            return False

        # Minor version: current >= incoming (backward compatible)
        if current.minor < incoming.minor:
            return False

        return True
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/session_state/serialization/test_schema_definition.py
from ward import test, fixture
import flatbuffers
from K1.SessionState import SessionStateRoot, SessionStateDelta
from K1.SessionState import BeliefsSection, Fact

@fixture
def sample_session_state_root():
    """Fixture for sample SessionStateRoot"""
    builder = flatbuffers.Builder(initial_size=8192)

    # Build beliefs section with 1 fact
    fact_key = builder.CreateString("user_name")
    fact_value = builder.CreateString("Alice")

    Fact.Start(builder)
    Fact.AddKey(builder, fact_key)
    Fact.AddValue(builder, fact_value)
    Fact.AddConfidence(builder, 1.0)
    Fact.AddCreatedAtMs(builder, 1697000000000)
    Fact.AddLastAccessedMs(builder, 1697000000000)
    fact_offset = Fact.End(builder)

    # Build beliefs section
    facts_vector = builder.CreateVector([fact_offset])
    BeliefsSection.Start(builder)
    BeliefsSection.AddFacts(builder, facts_vector)
    BeliefsSection.AddTotalFacts(builder, 1)
    BeliefsSection.AddSectionSizeBytes(builder, 100)
    beliefs_offset = BeliefsSection.End(builder)

    # Build root
    schema_version = builder.CreateString("1.0.0")
    session_id = builder.CreateString("test_session")

    SessionStateRoot.Start(builder)
    SessionStateRoot.AddSchemaVersion(builder, schema_version)
    SessionStateRoot.AddSessionId(builder, session_id)
    SessionStateRoot.AddBeliefs(builder, beliefs_offset)
    SessionStateRoot.AddTotalSizeBytes(builder, 1000)
    SessionStateRoot.AddCreatedAtMs(builder, 1697000000000)
    SessionStateRoot.AddLastUpdatedMs(builder, 1697000000000)
    root_offset = SessionStateRoot.End(builder)

    builder.Finish(root_offset)
    return bytes(builder.Output())

@test("SessionStateRoot serialization produces valid FlatBuffers")
def _(fb_bytes=sample_session_state_root):
    # Deserialize
    root = SessionStateRoot.GetRootAs(fb_bytes, 0)

    # Verify schema version
    assert root.SchemaVersion().decode('utf-8') == "1.0.0"

    # Verify session ID
    assert root.SessionId().decode('utf-8') == "test_session"

    # Verify beliefs section
    beliefs = root.Beliefs()
    assert beliefs is not None
    assert beliefs.TotalFacts() == 1
    assert beliefs.Facts(0).Key().decode('utf-8') == "user_name"
    assert beliefs.Facts(0).Value().decode('utf-8') == "Alice"

@test("SessionStateDelta only serializes changed sections")
def _():
    builder = flatbuffers.Builder(initial_size=4096)

    # Build delta with only beliefs changed
    changed_sections_vector = builder.CreateVector([builder.CreateString("beliefs")])

    # Build beliefs section (same as above)
    # ... (omitted for brevity)

    SessionStateDelta.Start(builder)
    SessionStateDelta.AddSchemaVersion(builder, builder.CreateString("1.0.0"))
    SessionStateDelta.AddSessionId(builder, builder.CreateString("test_session"))
    SessionStateDelta.AddChangedSections(builder, changed_sections_vector)
    SessionStateDelta.AddBeliefs(builder, beliefs_offset)
    # Note: scoreboard, control, persona, multimodal, meta are null
    delta_offset = SessionStateDelta.End(builder)

    builder.Finish(delta_offset)
    delta_bytes = bytes(builder.Output())

    # Verify delta
    delta = SessionStateDelta.GetRootAs(delta_bytes, 0)
    assert delta.ChangedSections(0).decode('utf-8') == "beliefs"
    assert delta.Beliefs() is not None
    assert delta.Scoreboard() is None  # Not changed
    assert delta.Control() is None     # Not changed

@test("Schema version validation rejects incompatible versions")
def _():
    from k1.session_state.serialization.version_checker import SchemaVersionChecker

    checker = SchemaVersionChecker()

    # Compatible versions
    assert checker.check_compatibility("1.0.0") is True
    assert checker.check_compatibility("1.0.1") is True  # Patch version OK

    # Incompatible versions
    assert checker.check_compatibility("2.0.0") is False  # Major version mismatch
    assert checker.check_compatibility("1.1.0") is False  # Minor version > current
```

---

## Performance Benchmarks

### Schema Compilation Time

```bash
# Benchmark schema compilation (all 6 sections + root + delta)
time flatc --python \
  --gen-object-api \
  --gen-mutable \
  -o k1/generated/session_state \
  k1/schemas/session_state/*.fbs \
  k1/schemas/session_state/**/*.fbs

# Expected: <500ms total compilation time
```

### Serialization Size Overhead

| Schema Component | Size | Percentage |
|------------------|------|------------|
| SessionStateRoot metadata | 250 bytes | <0.5% of 50KB payload |
| SessionStateDelta metadata | 150 bytes | <0.3% of 50KB payload |
| Nullable field flags | 6 bytes | <0.01% (1 bit per section × 6) |
| **Total Overhead** | **<500 bytes** | **<1% of payload** |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Schema Validation)
from prometheus_client import Counter, Histogram

# Schema validation metrics
schema_version_mismatch_total = Counter(
    'schema_version_mismatch_total',
    'Total schema version mismatches detected',
    labelnames=['expected_version', 'actual_version']
)

schema_validation_latency_us = Histogram(
    'schema_validation_latency_us',
    'Schema validation latency in microseconds',
    buckets=[10, 50, 100, 200, 500]
)
```

---

## Research Citations

1. **Google FlatBuffers Documentation.** *"FlatBuffers: Memory Efficient Serialization Library."* — Zero-copy deserialization patterns.

2. **Semantic Versioning 2.0.0.** *"SemVer Specification."* — Schema versioning rules (ADR-0013).

3. **Protocol Buffers (Google).** *"Protocol Buffers Language Guide."* — Schema evolution best practices.

---

## Consequences

### Positive

1. **Type Safety:** FlatBuffers schemas enforce type safety at compile time (catch errors early)
2. **Zero-Copy:** Direct buffer access without deserialization (critical for <1ms budget)
3. **Size Efficiency:** <1% overhead for metadata (schema_version, session_id, timestamps)
4. **Delta Compression:** SessionStateDelta only serializes changed sections (60-90% size savings)
5. **Backward Compatibility:** SemVer 2.0 versioning with compatibility matrix

### Negative

1. **Schema Complexity:** 6 section schemas + 15+ type schemas (maintenance burden)
2. **Compilation Required:** Must run `flatc` compiler before Python usage (build step)
3. **Nullable Overhead:** SessionStateDelta nullable sections add complexity (need null checks)

### Mitigations

1. **Schema Generation:** Consider codegen from ADR-0017 specifications (reduce manual errors)
2. **CI/CD Integration:** Automate `flatc` compilation in build pipeline
3. **Schema Registry:** Track schema versions in K0 (detect version drift)

---

## Roadmap

### Week 1: Schema Definition

- [ ] Define SessionStateRoot schema (root + 6 sections)
- [ ] Define SessionStateDelta schema (delta + nullable sections)
- [ ] Define 6 section schemas (beliefs, scoreboard, control, persona, multimodal, meta)
- [ ] Define 15+ type schemas (Fact, Entity, AgentLease, etc.)

### Week 2: Schema Compilation & Code Generation

- [ ] Compile schemas with `flatc` (Python output)
- [ ] Integrate into K1 build pipeline (Makefile/CI)
- [ ] Generate Python API docs (Sphinx)

### Week 3: Schema Versioning

- [ ] Implement SchemaVersionChecker (runtime validation)
- [ ] Define compatibility matrix (v1.0.0, v1.1.0, v2.0.0)
- [ ] Write migration guide for breaking changes

### Week 4: Testing & Validation

- [ ] Write WARD unit tests (serialization, deserialization, validation)
- [ ] Benchmark schema compilation time (<500ms target)
- [ ] Measure serialization size overhead (<1% target)
- [ ] Integrate with K0 bridge (test end-to-end persistence)

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** ADR-0017a-f (6 SessionState section sub-ADRs)
**Blocks:** 0019b (Delta Serialization Pipeline), 0019d (Zero-Copy Deserialization)

---

**END OF ADR-0019a**
