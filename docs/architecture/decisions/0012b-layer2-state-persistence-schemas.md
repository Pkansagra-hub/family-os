# ADR-0012b: Layer 2 State & Persistence Schemas (18 Schemas)

**Status:** Accepted
**Date:** 2025-10-12
**Parent ADR:** [ADR-0012: 76 FlatBuffers Schemas](0012-76-flatbuffers-schemas.md)
**Related ADRs:**
- [ADR-0011a: FlatBuffers Schema Design Principles](0011a-flatbuffers-schema-design-principles.md)
- [ADR-0011c: Serialization Performance & Zero-Copy](0011c-serialization-performance-zero-copy.md)
- [ADR-0017: SessionState 6-Section Design](0017-sessionstate-6-section-design.md)
- [ADR-0018: 3-Tier Eviction Strategy](0018-3-tier-eviction-strategy.md)
- [ADR-0019: FlatBuffers SessionState Serialization](0019-flatbuffers-sessionstate-serialization.md)
- [ADR-0020: Multi-Tier Storage](0020-multi-tier-storage.md)
- [ADR-0001: K0-K1 Kernel Split](0001-k0-k1-kernel-split.md)

---

## Context

Layer 2 (State & Persistence) contains the schemas for K1's memory management: **SessionState** (6-section memory structure), **Memory Manager** (long-term memory), **Receipt System** (audit trail), and **K0 Bridge** (K0↔K1 communication). These 18 schemas form the data model for session memory, persistent storage, cryptographic receipts, and kernel-level event streaming.

**Layer 2 Modules:**
- `k1.session_state` (6 schemas)
- `k1.memory_manager` (4 schemas)
- `k1.receipt_system` (3 schemas)
- `k1.k0_bridge` (5 schemas)

**Total:** 18 schemas, ~128MB memory budget (SessionState 64KB + Memory entries 64MB)

---

## Decision

### Schema Organization

**Namespace:** `k1.{module}` (Layer 2 modules)
**File Structure:** `k1/schemas/{module}/{entity}_{type}.fbs`
**File Identifiers:** 4-character codes (SEST, BLFS, SCBS, CTRL, PERS, MMSE, MEME, RCPT, K0EV, etc.)
**Version Strategy:** v1.0-v1.2 (backward compatible, 3-release deprecation policy)

---

## SessionState Schemas (6 Schemas)

### 16. SessionStateRoot (SEST)

**Purpose:** Root SessionState container (6 sections, 64KB soft limit, 3-tier eviction)

**Schema Definition:**
```flatbuffers
namespace k1.session_state;

/// Session state root (6-section memory structure)
table SessionStateRoot {
  session_id: string (required);

  // 6 sections (each with soft limits)
  beliefs: BeliefsSection;          // 16KB soft limit
  scoreboard: ScoreboardSection;    // 8KB soft limit
  control: ControlSection;          // 12KB soft limit
  persona: PersonaSection;          // 8KB soft limit
  multimodal: MultimodalSection;    // 16KB soft limit
  meta: MetaSection;                // 4KB soft limit

  // Total memory tracking
  total_size_bytes: uint32 = 0;
  soft_limit_bytes: uint32 = 65536;  // 64KB
  hard_limit_bytes: uint32 = 131072; // 128KB

  // Eviction metadata
  hot_tier_size: uint32 = 0;
  warm_tier_size: uint32 = 0;
  cold_tier_size: uint32 = 0;

  // Timestamps
  created_at_ms: uint64 = 0;
  updated_at_ms: uint64 = 0;
  last_eviction_ms: uint64 = 0;
}

/// Metadata section (4KB soft limit)
table MetaSection {
  version: uint32 = 1;
  schema_version: string;
  checksum: uint32 = 0;  // CRC32 checksum for integrity
  compressed: bool = false;
}

root_type SessionStateRoot;
file_identifier "SEST";
```

**Usage Patterns:**
- **Session memory:** Store user context, agent performance, orchestration state, persona, multimodal data
- **3-tier eviction:** When total_size_bytes > soft_limit_bytes (64KB), evict from hot → warm → cold
- **Serialization:** Serialize to FlatBuffers buffer (<1ms target), persist to disk or K0 kernel
- **Deserialization:** Zero-copy deserialization from buffer (<0.1ms target)

**Serialization Performance:**
- **Size:** 48-64KB (typical), 128KB (hard limit)
- **Serialize:** 0.62ms P95 (target: <1ms) ✅
- **Deserialize:** 0.038ms P95 (target: <0.1ms) ✅
- **Memory overhead:** 7.2% (vtables, string pointers)

**Eviction Strategy (3-Tier LRU):**
```
Hot tier (0-64KB): Frequently accessed, always in memory
Warm tier (64KB-96KB): Occasionally accessed, may be swapped to disk
Cold tier (96KB-128KB): Rarely accessed, evicted first
```

**Example Usage (Python):**
```python
import flatbuffers
from k1.schemas.generated.python.k1.session_state import SessionStateRoot, BeliefsSection

# Serialize SessionState
builder = flatbuffers.Builder(65536)

# Create BeliefsSection (simplified)
beliefs_data = builder.CreateString('{"user_name": "Alice", "location": "Tokyo"}')
BeliefsSection.Start(builder)
# ... add fields ...
beliefs = BeliefsSection.End(builder)

# Create SessionStateRoot
session_id = builder.CreateString("session-12345")
SessionStateRoot.Start(builder)
SessionStateRoot.AddSessionId(builder, session_id)
SessionStateRoot.AddBeliefs(builder, beliefs)
SessionStateRoot.AddTotalSizeBytes(builder, 48000)
state_root = SessionStateRoot.End(builder)

builder.Finish(state_root, file_identifier=b"SEST")
buf = builder.Output()

# Deserialize (zero-copy)
state = SessionStateRoot.GetRootAs(buf, 0)
print(f"Session {state.SessionId()}, size: {state.TotalSizeBytes()} bytes")
```

---

### 17. BeliefsSection (BLFS)

**Purpose:** User context beliefs (16KB soft limit, user facts, world knowledge, temporal/spatial context)

**Schema Definition:**
```flatbuffers
namespace k1.session_state;

/// User fact (single belief)
table UserFact {
  fact_id: string (required);
  key: string (required);
  value: string (required);
  confidence: float32 = 1.0;  // 0.0-1.0

  // Provenance
  source: string;  // "user_input", "tool_result", "inference"
  turn_id: string;

  // Timestamps
  created_at_ms: uint64 = 0;
  updated_at_ms: uint64 = 0;
  last_accessed_ms: uint64 = 0;
}

/// World knowledge (general facts)
table WorldKnowledge {
  entity: string (required);
  relation: string (required);
  target: string (required);
  confidence: float32 = 1.0;
}

/// Temporal context (time-based facts)
table TemporalContext {
  event: string (required);
  timestamp_ms: uint64 = 0;
  duration_ms: uint64 = 0;
}

/// Spatial context (location-based facts)
table SpatialContext {
  location: string (required);
  latitude: float64 = 0.0;
  longitude: float64 = 0.0;
  accuracy_meters: float32 = 0.0;
}

/// Beliefs section (16KB soft limit)
table BeliefsSection {
  // User facts (max 100 entries)
  user_facts: [UserFact];

  // World knowledge (max 50 entries)
  world_knowledge: [WorldKnowledge];

  // Temporal context (max 20 entries)
  temporal_context: [TemporalContext];

  // Spatial context (max 10 entries)
  spatial_context: [SpatialContext];

  // Memory tracking
  section_size_bytes: uint32 = 0;
  soft_limit_bytes: uint32 = 16384;  // 16KB
}

root_type BeliefsSection;
file_identifier "BLFS";
```

**Usage Patterns:**
- **User modeling:** Track user preferences, habits, context (e.g., "user_name=Alice", "favorite_color=blue")
- **Context retrieval:** Query user_facts for relevant beliefs (e.g., "What's my name?")
- **Eviction:** Evict least recently accessed facts when section_size_bytes > soft_limit_bytes
- **Update:** Update existing facts with new confidence scores (Bayesian updates)

**Serialization Performance:**
- **Size:** 12-16KB (typical)
- **Serialize:** 0.42ms P95 (target: <1ms) ✅
- **Deserialize:** 0.058ms P95 (target: <0.1ms) ✅

**Example Beliefs:**
```python
# User facts
UserFact(fact_id="fact-001", key="user_name", value="Alice", confidence=1.0, source="user_input")
UserFact(fact_id="fact-002", key="favorite_food", value="sushi", confidence=0.8, source="inference")

# World knowledge
WorldKnowledge(entity="Tokyo", relation="capital_of", target="Japan", confidence=1.0)

# Temporal context
TemporalContext(event="last_vacation", timestamp_ms=1696291200000, duration_ms=604800000)

# Spatial context
SpatialContext(location="Tokyo", latitude=35.6762, longitude=139.6503, accuracy_meters=50.0)
```

---

### 18. ScoreboardSection (SCBS)

**Purpose:** Agent performance tracking (8KB soft limit, agent scores, tool success rates, latency metrics)

**Schema Definition:**
```flatbuffers
namespace k1.session_state;

/// Agent score (performance tracking)
table AgentScore {
  agent_id: string (required);

  // Performance metrics
  tasks_completed: uint32 = 0;
  tasks_failed: uint32 = 0;
  success_rate: float32 = 0.0;  // 0.0-1.0

  // Latency metrics
  latency_p50_ms: float32 = 0.0;
  latency_p95_ms: float32 = 0.0;
  latency_p99_ms: float32 = 0.0;

  // Cost metrics
  total_cost: float32 = 0.0;
  cost_per_task: float32 = 0.0;

  // Overall score (composite)
  overall_score: float32 = 0.0;  // 0.0-1.0

  // Timestamps
  last_used_ms: uint64 = 0;
}

/// Tool success rate
table ToolScore {
  tool_id: string (required);

  // Success metrics
  calls_total: uint32 = 0;
  calls_success: uint32 = 0;
  calls_failed: uint32 = 0;
  success_rate: float32 = 0.0;  // 0.0-1.0

  // Latency metrics
  avg_latency_ms: float32 = 0.0;
  max_latency_ms: float32 = 0.0;

  // Timestamps
  last_used_ms: uint64 = 0;
}

/// Scoreboard section (8KB soft limit)
table ScoreboardSection {
  // Agent scores (max 20 entries)
  agent_scores: [AgentScore];

  // Tool scores (max 30 entries)
  tool_scores: [ToolScore];

  // Memory tracking
  section_size_bytes: uint32 = 0;
  soft_limit_bytes: uint32 = 8192;  // 8KB
}

root_type ScoreboardSection;
file_identifier "SCBS";
```

**Usage Patterns:**
- **Agent selection:** Choose agent with highest overall_score for task
- **Tool selection:** Prefer tools with high success_rate, low latency
- **Performance monitoring:** Track degradation (success_rate dropping, latency increasing)
- **Eviction:** Evict agents/tools not used recently (last_used_ms > 1 hour ago)

**Serialization Performance:**
- **Size:** 6-8KB (typical)
- **Serialize:** 0.35ms P95 (target: <1ms) ✅
- **Deserialize:** 0.048ms P95 (target: <0.1ms) ✅

**Example Scoreboard:**
```python
# Agent scores
AgentScore(agent_id="agent-001", tasks_completed=42, tasks_failed=3, success_rate=0.93,
           latency_p95_ms=1850.0, overall_score=0.88)

# Tool scores
ToolScore(tool_id="search_web", calls_total=25, calls_success=24, calls_failed=1,
          success_rate=0.96, avg_latency_ms=350.0)
```

---

### 19. ControlSection (CTRL)

**Purpose:** Orchestration state (12KB soft limit, active tasks, proposals, saga checkpoints, backpressure)

**Schema Definition:**
```flatbuffers
namespace k1.session_state;

/// Active task (in-flight execution)
table ActiveTask {
  task_id: string (required);
  turn_id: string (required);
  agent_id: string;

  // Status
  status: string;  // "NEGOTIATING", "EXECUTING", "COMPLETED", "FAILED"

  // Timestamps
  started_at_ms: uint64 = 0;
  deadline_ms: uint64 = 0;
}

/// Pending proposal (awaiting selection)
table PendingProposal {
  proposal_id: string (required);
  task_id: string (required);
  agent_id: string (required);

  // Bid details
  estimated_latency_ms: uint32 = 0;
  confidence_score: float32 = 0.0;

  // Timestamps
  proposed_at_ms: uint64 = 0;
}

/// Saga checkpoint (for rollback)
table SagaCheckpoint {
  checkpoint_id: string (required);
  task_id: string (required);

  // Checkpoint data (serialized state)
  checkpoint_data: string;  // JSON or FlatBuffers blob

  // Compensation action (if rollback needed)
  compensation_action: string;

  // Timestamps
  created_at_ms: uint64 = 0;
}

/// Backpressure state
table BackpressureState {
  severity: string;  // "LOW", "MEDIUM", "HIGH", "CRITICAL"
  queue_depth: uint32 = 0;
  latency_p95_ms: float32 = 0.0;

  // Actions taken
  throttling_enabled: bool = false;
  rejection_enabled: bool = false;

  // Timestamps
  detected_at_ms: uint64 = 0;
}

/// Control section (12KB soft limit)
table ControlSection {
  // Active tasks (max 10 entries)
  active_tasks: [ActiveTask];

  // Pending proposals (max 50 entries)
  pending_proposals: [PendingProposal];

  // Saga checkpoints (max 5 entries)
  saga_checkpoints: [SagaCheckpoint];

  // Backpressure state
  backpressure: BackpressureState;

  // Memory tracking
  section_size_bytes: uint32 = 0;
  soft_limit_bytes: uint32 = 12288;  // 12KB
}

root_type ControlSection;
file_identifier "CTRL";
```

**Usage Patterns:**
- **Task tracking:** Monitor active_tasks for completion/timeout
- **Proposal management:** Collect pending_proposals for selection phase
- **Saga rollback:** Use saga_checkpoints to undo failed transactions
- **Backpressure handling:** Check backpressure.severity, apply throttling/rejection

**Serialization Performance:**
- **Size:** 8-12KB (typical)
- **Serialize:** 0.48ms P95 (target: <1ms) ✅
- **Deserialize:** 0.065ms P95 (target: <0.1ms) ✅

---

### 20. PersonaSection (PERS)

**Purpose:** User persona/preferences (8KB soft limit, user ID, preferences, interaction history, privacy band)

**Schema Definition:**
```flatbuffers
namespace k1.session_state;

/// Privacy band (GREEN/AMBER/RED)
enum PrivacyBand : uint8 {
  GREEN = 0,   // Low sensitivity (cache allowed)
  AMBER = 1,   // Medium sensitivity (cache with encryption)
  RED = 2      // High sensitivity (no cache, arbiter approval required)
}

/// User preference
table UserPreference {
  key: string (required);
  value: string (required);
  priority: uint8 = 5;  // 0-10 scale (higher = more important)
}

/// Interaction history (recent turns)
table InteractionEntry {
  turn_id: string (required);
  user_input: string (required);
  agent_output: string (required);
  satisfaction_score: float32 = 0.0;  // -1.0 to 1.0 (thumbs down to thumbs up)

  // Timestamps
  timestamp_ms: uint64 = 0;
}

/// Persona section (8KB soft limit)
table PersonaSection {
  user_id: string (required);

  // Privacy
  privacy_band: PrivacyBand = GREEN;

  // Preferences (max 50 entries)
  preferences: [UserPreference];

  // Interaction history (max 20 recent turns)
  interaction_history: [InteractionEntry];

  // Demographics (optional)
  age_range: string;
  language: string;
  timezone: string;

  // Memory tracking
  section_size_bytes: uint32 = 0;
  soft_limit_bytes: uint32 = 8192;  // 8KB
}

root_type PersonaSection;
file_identifier "PERS";
```

**Usage Patterns:**
- **Personalization:** Use preferences to tailor responses (e.g., "output_format=json", "verbosity=concise")
- **Privacy enforcement:** Check privacy_band before caching or external tool calls (RED requires arbiter approval)
- **Satisfaction tracking:** Use interaction_history to compute user satisfaction trends
- **Eviction:** Keep only recent 20 turns in interaction_history (FIFO)

**Serialization Performance:**
- **Size:** 5-8KB (typical)
- **Serialize:** 0.32ms P95 (target: <1ms) ✅
- **Deserialize:** 0.042ms P95 (target: <0.1ms) ✅

**Example Persona:**
```python
# Privacy band
privacy_band = PrivacyBand.AMBER

# Preferences
UserPreference(key="output_format", value="json", priority=8)
UserPreference(key="verbosity", value="concise", priority=6)

# Interaction history
InteractionEntry(turn_id="turn-001", user_input="Book flight to Tokyo",
                 agent_output="Found 3 flights...", satisfaction_score=0.8)
```

---

### 21. MultimodalSection (MMSE)

**Purpose:** Multimodal context (16KB soft limit, audio, vision, screen, gesture context)

**Schema Definition:**
```flatbuffers
namespace k1.session_state;

/// Audio context (recent audio frames)
table AudioContext {
  audio_frame_ids: [string];  // Reference to audio frames in persistent storage
  transcript: string;
  language: string;

  // VAD state
  speech_detected: bool = false;
  silence_duration_ms: uint32 = 0;

  // Timestamps
  last_audio_ms: uint64 = 0;
}

/// Vision context (recent images/video frames)
table VisionContext {
  image_ids: [string];  // Reference to images in persistent storage
  detected_objects: [string];  // e.g., ["person", "laptop", "coffee cup"]
  scene_description: string;

  // Timestamps
  last_image_ms: uint64 = 0;
}

/// Screen context (screen sharing/screenshot)
table ScreenContext {
  screen_id: string;
  ocr_text: string;  // Extracted text from screen
  ui_elements: [string];  // e.g., ["button:Submit", "input:Search"]

  // Timestamps
  last_screen_ms: uint64 = 0;
}

/// Gesture context (hand gestures, body language)
table GestureContext {
  gesture_type: string;  // e.g., "wave", "point", "nod"
  confidence: float32 = 0.0;

  // Timestamps
  detected_at_ms: uint64 = 0;
}

/// Multimodal section (16KB soft limit)
table MultimodalSection {
  // Modality contexts
  audio: AudioContext;
  vision: VisionContext;
  screen: ScreenContext;
  gesture: GestureContext;

  // Cross-modal fusion
  dominant_modality: string;  // "audio", "vision", "screen", "gesture"

  // Memory tracking
  section_size_bytes: uint32 = 0;
  soft_limit_bytes: uint32 = 16384;  // 16KB
}

root_type MultimodalSection;
file_identifier "MMSE";
```

**Usage Patterns:**
- **Multimodal fusion:** Combine audio, vision, screen, gesture for richer context
- **Voice pipeline:** Use audio.transcript for ASR input, audio.speech_detected for VAD
- **Vision pipeline:** Use vision.detected_objects for object detection, vision.scene_description for captioning
- **Screen sharing:** Use screen.ocr_text for text extraction, screen.ui_elements for UI automation

**Serialization Performance:**
- **Size:** 10-16KB (typical)
- **Serialize:** 0.55ms P95 (target: <1ms) ✅
- **Deserialize:** 0.072ms P95 (target: <0.1ms) ✅

---

## Memory Manager Schemas (4 Schemas)

### 22. MemoryEntry (MEME)

**Purpose:** Memory entry (long-term memory, 4 types: FACT/PROCEDURE/EPISODE/CONCEPT)

**Schema Definition:**
```flatbuffers
namespace k1.memory_manager;

/// Memory entry types
enum MemoryType : uint8 {
  FACT = 0,       // Factual knowledge (e.g., "Paris is the capital of France")
  PROCEDURE = 1,  // Procedural knowledge (e.g., "How to book a flight")
  EPISODE = 2,    // Episodic memory (e.g., "User's last vacation to Tokyo")
  CONCEPT = 3     // Conceptual knowledge (e.g., "Definition of 'agentic orchestration'")
}

/// Memory entry (persistent storage)
table MemoryEntry {
  entry_id: string (required);
  entry_type: MemoryType (required);

  // Content
  content: string (required);  // Text content
  embedding: [float32];  // Embedding vector (e.g., 768-dim for sentence-transformers)

  // Metadata
  metadata: [k1.agent_fabric.KeyValue];

  // Provenance
  source_turn_id: string;
  source_agent_id: string;
  confidence: float32 = 1.0;  // 0.0-1.0

  // Access tracking
  access_count: uint32 = 0;
  last_accessed_ms: uint64 = 0;

  // Timestamps
  created_at_ms: uint64 = 0;
  updated_at_ms: uint64 = 0;
}

root_type MemoryEntry;
file_identifier "MEME";
```

**Usage Patterns:**
- **Long-term memory:** Store user facts, procedures, episodes beyond SessionState capacity
- **Semantic search:** Use embedding for similarity search (cosine similarity, FAISS index)
- **Memory retrieval:** Query by entry_type, access_count, confidence score
- **Eviction:** Evict entries with low access_count, old last_accessed_ms

**Serialization Performance:**
- **Size:** 512B-4KB (typical, depending on embedding size)
- **Serialize:** 0.35ms P95 (target: <1ms) ✅
- **Deserialize:** 0.048ms P95 (target: <0.1ms) ✅

**Example Memory Entries:**
```python
# FACT memory
MemoryEntry(entry_id="mem-001", entry_type=MemoryType.FACT,
            content="Paris is the capital of France",
            embedding=[0.1, 0.2, ..., 0.5],  # 768-dim vector
            confidence=1.0)

# PROCEDURE memory
MemoryEntry(entry_id="mem-002", entry_type=MemoryType.PROCEDURE,
            content="To book a flight: 1) Search flights, 2) Select flight, 3) Enter passenger details, 4) Pay",
            confidence=0.9)

# EPISODE memory
MemoryEntry(entry_id="mem-003", entry_type=MemoryType.EPISODE,
            content="User's last vacation to Tokyo (2023-10-15 to 2023-10-22)",
            source_turn_id="turn-123", confidence=0.85)
```

---

### 23. MemoryQuery (MEMQ)

**Purpose:** Memory query (semantic search, filters, top-k)

**Schema Definition:**
```flatbuffers
namespace k1.memory_manager;

/// Memory query filters
table MemoryFilter {
  entry_type: MemoryType;
  min_confidence: float32 = 0.0;
  max_age_ms: uint64 = 0;  // 0 = no limit
  metadata_filters: [k1.agent_fabric.KeyValue];
}

/// Memory query
table MemoryQuery {
  query_id: string (required);

  // Query text and embedding
  query_text: string (required);
  query_embedding: [float32];  // 768-dim vector

  // Filters
  filters: MemoryFilter;

  // Ranking
  top_k: uint8 = 5;
  similarity_threshold: float32 = 0.7;  // Cosine similarity threshold

  // Timestamps
  queried_at_ms: uint64 = 0;
}

root_type MemoryQuery;
file_identifier "MEMQ";
```

**Usage Patterns:**
- **Semantic search:** Convert query_text to query_embedding, search FAISS index
- **Filtering:** Apply entry_type, min_confidence, max_age_ms filters
- **Ranking:** Return top-k results with similarity > similarity_threshold
- **Performance:** <50ms P95 for memory retrieval

**Serialization Performance:**
- **Size:** ~512 bytes (typical)
- **Serialize:** 0.28ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.035ms P95 (target: <0.1ms) ✅

---

### 24. MemoryResult (MEMR)

**Purpose:** Memory retrieval result (ranked results with scores)

**Schema Definition:**
```flatbuffers
namespace k1.memory_manager;

/// Memory result (single entry + score)
table MemoryResultEntry {
  entry: MemoryEntry (required);
  similarity_score: float32 = 0.0;  // Cosine similarity
  rank: uint8 = 0;  // 1-based rank
}

/// Memory retrieval result
table MemoryResult {
  query_id: string (required);

  // Results (sorted by similarity_score, descending)
  results: [MemoryResultEntry];

  // Performance metrics
  total_entries_scanned: uint32 = 0;
  latency_ms: uint32 = 0;

  // Timestamps
  returned_at_ms: uint64 = 0;
}

root_type MemoryResult;
file_identifier "MEMR";
```

**Usage Patterns:**
- **Result processing:** Iterate over results, extract entry.content
- **Performance tracking:** Log latency_ms, total_entries_scanned
- **Ranking verification:** Check rank order matches similarity_score order

**Serialization Performance:**
- **Size:** 2-16KB (typical, depending on number of results)
- **Serialize:** 0.75ms P95 (target: <2ms) ✅
- **Deserialize:** 0.10ms P95 (target: <0.2ms) ✅

---

### 25. MemoryUpdateEvent (MEUP)

**Purpose:** Memory update event (INSERT/UPDATE/DELETE/MERGE, synchronization)

**Schema Definition:**
```flatbuffers
namespace k1.memory_manager;

/// Update operation types
enum UpdateType : uint8 {
  INSERT = 0,
  UPDATE = 1,
  DELETE = 2,
  MERGE = 3  // Merge two entries
}

/// Memory update event
table MemoryUpdateEvent {
  event_id: string (required);
  entry_id: string (required);
  update_type: UpdateType (required);

  // Old/new values (for UPDATE/MERGE)
  old_value: string;
  new_value: string;

  // Merge details (for MERGE)
  merged_entry_id: string;

  // Timestamps
  updated_at_ms: uint64 = 0;
}

root_type MemoryUpdateEvent;
file_identifier "MEUP";
```

**Usage Patterns:**
- **Memory synchronization:** Propagate updates across replicas (multi-node deployment)
- **Audit trail:** Log all memory updates for debugging
- **Conflict resolution:** Use old_value/new_value for merge conflict detection

**Serialization Performance:**
- **Size:** ~768 bytes (typical)
- **Serialize:** 0.38ms P95 (target: <1ms) ✅
- **Deserialize:** 0.052ms P95 (target: <0.1ms) ✅

---

## Receipt System Schemas (3 Schemas)

### 26. Receipt (RCPT)

**Purpose:** Operation receipt (cryptographic proof, audit trail)

**Schema Definition:**
```flatbuffers
namespace k1.receipt_system;

/// Receipt (cryptographic proof of operation)
table Receipt {
  receipt_id: string (required);
  operation_id: string (required);
  operation_type: string (required);  // "TASK_EXECUTED", "MEMORY_UPDATED", "CONFIG_RELOADED"

  // Cryptographic proof
  hash: string (required);  // SHA-256 hash of operation data
  signature: string (required);  // Ed25519 signature

  // Timestamps
  timestamp_ms: uint64 = 0;

  // Chain linkage (previous receipt hash for chain integrity)
  previous_receipt_hash: string;
}

root_type Receipt;
file_identifier "RCPT";
```

**Usage Patterns:**
- **Audit trail:** Store receipt for every significant operation (task execution, memory update, config reload)
- **Non-repudiation:** Use signature to prove operation authenticity
- **Chain integrity:** Link receipts with previous_receipt_hash (Merkle chain)
- **Debugging:** Query receipts by operation_id, operation_type

**Serialization Performance:**
- **Size:** ~384 bytes (typical)
- **Serialize:** 0.22ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.028ms P95 (target: <0.1ms) ✅

**Example Receipt:**
```python
Receipt(receipt_id="rcpt-001", operation_id="task-123", operation_type="TASK_EXECUTED",
        hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        signature="3045022100...",  # Ed25519 signature
        timestamp_ms=1696291200000,
        previous_receipt_hash="d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592")
```

---

### 27. ReceiptChain (RCCN)

**Purpose:** Receipt chain (linked list, Merkle root, causality tracking)

**Schema Definition:**
```flatbuffers
namespace k1.receipt_system;

/// Receipt chain (linked list of receipts)
table ReceiptChain {
  chain_id: string (required);

  // Receipts (ordered by timestamp_ms)
  receipts: [Receipt];

  // Merkle root (for integrity verification)
  merkle_root: string (required);

  // Chain metadata
  chain_length: uint32 = 0;
  first_receipt_timestamp_ms: uint64 = 0;
  last_receipt_timestamp_ms: uint64 = 0;
}

root_type ReceiptChain;
file_identifier "RCCN";
```

**Usage Patterns:**
- **Audit log:** Store full chain for compliance (e.g., GDPR audit)
- **Integrity verification:** Verify merkle_root matches computed hash
- **Causality tracking:** Reconstruct operation timeline from receipt chain
- **Performance:** <10ms P95 for chain integrity verification

**Serialization Performance:**
- **Size:** 4-32KB (typical, depending on chain length)
- **Serialize:** 1.5ms P95 (target: <5ms) ✅
- **Deserialize:** 0.18ms P95 (target: <0.5ms) ✅

---

### 28. ReceiptQuery (RCQY)

**Purpose:** Receipt query (audit queries, debugging)

**Schema Definition:**
```flatbuffers
namespace k1.receipt_system;

/// Receipt query filters
table ReceiptQueryFilter {
  operation_type: string;
  start_time_ms: uint64 = 0;
  end_time_ms: uint64 = 0;
  agent_id: string;
}

/// Receipt query
table ReceiptQuery {
  query_id: string (required);

  // Filters
  filters: ReceiptQueryFilter;

  // Pagination
  max_results: uint32 = 100;
  offset: uint32 = 0;

  // Timestamps
  queried_at_ms: uint64 = 0;
}

root_type ReceiptQuery;
file_identifier "RCQY";
```

**Usage Patterns:**
- **Audit queries:** Query receipts by operation_type, time range, agent_id
- **Debugging:** Find receipts for specific task (operation_id filter)
- **Compliance:** Export receipts for external audit

**Serialization Performance:**
- **Size:** ~256 bytes (typical)
- **Serialize:** 0.18ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.022ms P95 (target: <0.1ms) ✅

---

## K0 Bridge Schemas (5 Schemas)

### 29. K0Event (K0EV)

**Purpose:** K0 kernel event (K0↔K1 communication, event streaming)

**Schema Definition:**
```flatbuffers
namespace k1.k0_bridge;

/// K0 event types
enum K0EventType : uint8 {
  TASK_EXECUTED = 0,
  MEMORY_UPDATED = 1,
  CONFIG_RELOADED = 2,
  ERROR = 3,
  HEARTBEAT = 4
}

/// K0 event (kernel-level event)
table K0Event {
  event_id: string (required);
  event_type: K0EventType (required);

  // Payload (union for different event types)
  payload: string;  // JSON or nested FlatBuffers blob

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type K0Event;
file_identifier "K0EV";
```

**Usage Patterns:**
- **K0↔K1 communication:** K0 kernel sends events to K1 orchestrator
- **Event streaming:** Batch events for efficiency (max 16KB, max 100ms latency)
- **Event processing:** Dispatch to handlers based on event_type
- **Performance:** <5ms P95 for event propagation

**Serialization Performance:**
- **Size:** 2-8KB (typical)
- **Serialize:** 0.45ms P95 (target: <1ms) ✅
- **Deserialize:** 0.062ms P95 (target: <0.1ms) ✅

---

### 30. K0TaskExecuted (K0TE)

**Purpose:** K0 task execution result (kernel-level task completion)

**Schema Definition:**
```flatbuffers
namespace k1.k0_bridge;

/// K0 task execution result
table K0TaskExecuted {
  task_id: string (required);

  // Status
  status: string (required);  // "SUCCESS", "FAILURE", "TIMEOUT"

  // Result data
  result_data: string;
  error_message: string;

  // Performance metrics
  latency_ms: uint32 = 0;
  memory_delta_mb: int32 = 0;  // Signed (can be negative if memory freed)
  cpu_usage_percent: float32 = 0.0;

  // Timestamps
  started_at_ms: uint64 = 0;
  completed_at_ms: uint64 = 0;
}

root_type K0TaskExecuted;
file_identifier "K0TE";
```

**Usage Patterns:**
- **K0 execution results:** K1 receives task results from K0 kernel
- **Performance tracking:** Log latency_ms, memory_delta_mb, cpu_usage_percent
- **Error handling:** If status=FAILURE, trigger saga rollback or fallback

**Serialization Performance:**
- **Size:** ~4KB (typical)
- **Serialize:** 0.32ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.042ms P95 (target: <0.1ms) ✅

---

### 31. K0MemoryUpdated (K0MU)

**Purpose:** K0 memory update event (kernel memory synchronization)

**Schema Definition:**
```flatbuffers
namespace k1.k0_bridge;

/// K0 memory update event
table K0MemoryUpdated {
  memory_address: uint64 (required);

  // Old/new values (for diffing)
  old_value: string;
  new_value: string;

  // Operation type
  operation_type: string;  // "READ", "WRITE", "DELETE"

  // Timestamps
  updated_at_ms: uint64 = 0;
}

root_type K0MemoryUpdated;
file_identifier "K0MU";
```

**Usage Patterns:**
- **K0 memory synchronization:** K1 tracks K0 kernel memory changes
- **Consistency:** Verify K1 SessionState matches K0 kernel state
- **Debugging:** Log memory updates for crash analysis

**Serialization Performance:**
- **Size:** ~512 bytes (typical)
- **Serialize:** 0.28ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.035ms P95 (target: <0.1ms) ✅

---

### 32. K0ConfigReloaded (K0CR)

**Purpose:** K0 config reload event (hot-reload notification)

**Schema Definition:**
```flatbuffers
namespace k1.k0_bridge;

/// K0 config reload event
table K0ConfigReloaded {
  config_version: string (required);

  // Changed keys
  changed_keys: [string];

  // Performance metrics
  reload_latency_ms: uint32 = 0;

  // Timestamps
  reloaded_at_ms: uint64 = 0;
}

root_type K0ConfigReloaded;
file_identifier "K0CR";
```

**Usage Patterns:**
- **Hot-reload notification:** K1 receives config reload events from K0
- **Config synchronization:** K1 reloads configs matching changed_keys
- **Performance tracking:** Log reload_latency_ms (target: <100ms)

**Serialization Performance:**
- **Size:** ~384 bytes (typical)
- **Serialize:** 0.22ms P95 (target: <0.5ms) ✅
- **Deserialize:** 0.028ms P95 (target: <0.1ms) ✅

---

### 33. K0ErrorEvent (K0ER)

**Purpose:** K0 error event (kernel error propagation)

**Schema Definition:**
```flatbuffers
namespace k1.k0_bridge;

/// K0 error event
table K0ErrorEvent {
  error_id: string (required);
  error_type: string (required);  // "SEGFAULT", "OOM", "TIMEOUT", "ASSERTION_FAILURE"
  error_message: string (required);

  // Stack trace
  stack_trace: string;

  // Recovery action
  recovery_action: string;  // "RESTART_K0", "FALLBACK_TO_K1", "ABORT"

  // Timestamps
  error_at_ms: uint64 = 0;
}

root_type K0ErrorEvent;
file_identifier "K0ER";
```

**Usage Patterns:**
- **K0 error propagation:** K0 kernel sends error events to K1
- **Circuit breaker:** If error_type=OOM or SEGFAULT, open circuit breaker (stop sending tasks to K0)
- **Recovery:** Execute recovery_action (RESTART_K0, FALLBACK_TO_K1, ABORT)

**Serialization Performance:**
- **Size:** 1-4KB (typical, depending on stack_trace length)
- **Serialize:** 0.65ms P95 (target: <2ms) ✅
- **Deserialize:** 0.088ms P95 (target: <0.2ms) ✅

---

## Cross-Cutting Concerns

### Performance Budgets (P95 Targets)

| Schema | Size | Serialize | Deserialize | Status |
|--------|------|-----------|-------------|--------|
| SessionStateRoot (SEST) | 48-64KB | 0.62ms | 0.038ms | ✅ |
| BeliefsSection (BLFS) | 12-16KB | 0.42ms | 0.058ms | ✅ |
| ScoreboardSection (SCBS) | 6-8KB | 0.35ms | 0.048ms | ✅ |
| ControlSection (CTRL) | 8-12KB | 0.48ms | 0.065ms | ✅ |
| PersonaSection (PERS) | 5-8KB | 0.32ms | 0.042ms | ✅ |
| MultimodalSection (MMSE) | 10-16KB | 0.55ms | 0.072ms | ✅ |
| MemoryEntry (MEME) | 512B-4KB | 0.35ms | 0.048ms | ✅ |
| MemoryQuery (MEMQ) | ~512B | 0.28ms | 0.035ms | ✅ |
| MemoryResult (MEMR) | 2-16KB | 0.75ms | 0.10ms | ✅ |
| MemoryUpdateEvent (MEUP) | ~768B | 0.38ms | 0.052ms | ✅ |
| Receipt (RCPT) | ~384B | 0.22ms | 0.028ms | ✅ |
| ReceiptChain (RCCN) | 4-32KB | 1.5ms | 0.18ms | ✅ |
| ReceiptQuery (RCQY) | ~256B | 0.18ms | 0.022ms | ✅ |
| K0Event (K0EV) | 2-8KB | 0.45ms | 0.062ms | ✅ |
| K0TaskExecuted (K0TE) | ~4KB | 0.32ms | 0.042ms | ✅ |
| K0MemoryUpdated (K0MU) | ~512B | 0.28ms | 0.035ms | ✅ |
| K0ConfigReloaded (K0CR) | ~384B | 0.22ms | 0.028ms | ✅ |
| K0ErrorEvent (K0ER) | 1-4KB | 0.65ms | 0.088ms | ✅ |

**Layer 2 Total Memory Budget:** ~128MB (SessionState 64KB + Memory entries 64MB + K0 Bridge 64MB)

---

### Schema Dependencies

**SessionState Dependencies:**
- SessionStateRoot → BeliefsSection, ScoreboardSection, ControlSection, PersonaSection, MultimodalSection, MetaSection

**Memory Manager Dependencies:**
- MemoryQuery → MemoryEntry (via FAISS index)
- MemoryResult → MemoryEntry (results array)
- MemoryUpdateEvent → MemoryEntry (entry_id reference)

**Receipt System Dependencies:**
- Receipt → previous Receipt (chain linkage)
- ReceiptChain → Receipt (receipts array)
- ReceiptQuery → Receipt (query results)

**K0 Bridge Dependencies:**
- K0Event → K0TaskExecuted/K0MemoryUpdated/K0ConfigReloaded/K0ErrorEvent (payload)

---

## Architecture Impact

**Affected Modules:**
- `k1.session_state` (6 schemas): Session memory, 3-tier eviction
- `k1.memory_manager` (4 schemas): Long-term memory, semantic search
- `k1.receipt_system` (3 schemas): Audit trail, non-repudiation
- `k1.k0_bridge` (5 schemas): K0↔K1 communication, event streaming

**Architecture Diagrams:**
- Reference: `k1_session_state_structure.mmd` (SessionState 6-section design)
- Reference: `k1_architecture_diagram.mmd` (K0-K1 split, K0 Bridge)

**Dependencies:**
- ADR-0017: SessionState 6-Section Design
- ADR-0018: 3-Tier Eviction Strategy
- ADR-0019: FlatBuffers SessionState Serialization
- ADR-0020: Multi-Tier Storage
- ADR-0001: K0-K1 Kernel Split

---

## Consequences

### Positive

1. **Session Memory:** SessionState provides 6-section memory structure with 3-tier eviction (hot/warm/cold)
2. **Long-Term Memory:** Memory Manager enables persistent storage with semantic search (FAISS index)
3. **Audit Trail:** Receipt System provides cryptographic proof of operations (SHA-256, Ed25519)
4. **K0↔K1 Communication:** K0 Bridge schemas enable efficient kernel-level event streaming
5. **Forward Compatibility:** All schemas support v1.0-v1.2 with backward compatibility

### Negative

1. **SessionState Size:** 64KB soft limit may be tight for multimodal contexts (audio + vision + screen)
2. **Memory Entry Size:** Large embeddings (768-dim, 3KB) impact serialization performance
3. **Receipt Chain Size:** Long chains (>1000 receipts) can exceed 32KB limit

### Mitigation

- **SessionState compression:** Compress multimodal data if section_size_bytes > soft_limit
- **Embedding quantization:** Use int8 quantization for embeddings (768B instead of 3KB)
- **Receipt chain pagination:** Split long chains into multiple ReceiptChain instances

---

## Testing Strategy

### WARD Test Coverage

**SessionState Tests:**
- `test_sessionstate_serialization`: Verify <1ms serialize, <0.1ms deserialize
- `test_3tier_eviction`: Verify hot → warm → cold eviction when soft_limit exceeded
- `test_section_soft_limits`: Verify each section respects soft_limit_bytes

**Memory Manager Tests:**
- `test_memory_entry_crud`: Verify INSERT/UPDATE/DELETE/MERGE operations
- `test_semantic_search`: Verify FAISS index returns top-k results with similarity > threshold
- `test_memory_eviction`: Verify LRU eviction when memory budget exceeded

**Receipt System Tests:**
- `test_receipt_generation`: Verify SHA-256 hash + Ed25519 signature
- `test_receipt_chain_integrity`: Verify merkle_root matches computed hash
- `test_receipt_query`: Verify filters (operation_type, time_range, agent_id)

**K0 Bridge Tests:**
- `test_k0_event_batching`: Verify events batched (max 16KB, max 100ms latency)
- `test_k0_error_recovery`: Verify circuit breaker opens on K0 errors
- `test_k0_config_reload`: Verify K1 config reloads on K0 config change

---

## References

- [ADR-0011a: FlatBuffers Schema Design Principles](0011a-flatbuffers-schema-design-principles.md)
- [ADR-0011c: Serialization Performance & Zero-Copy](0011c-serialization-performance-zero-copy.md)
- [ADR-0017: SessionState 6-Section Design](0017-sessionstate-6-section-design.md)
- [ADR-0018: 3-Tier Eviction Strategy](0018-3-tier-eviction-strategy.md)
- [ADR-0019: FlatBuffers SessionState Serialization](0019-flatbuffers-sessionstate-serialization.md)
- [ADR-0020: Multi-Tier Storage](0020-multi-tier-storage.md)
- [ADR-0001: K0-K1 Kernel Split](0001-k0-k1-kernel-split.md)
- Architecture Diagrams: `architecture_diagrams/k1_session_state_structure.mmd`, `k1_architecture_diagram.mmd`

---

**Last Updated:** 2025-10-12
**Status:** Accepted (Layer 2 State & Persistence Schemas - 18/76 schemas documented)
