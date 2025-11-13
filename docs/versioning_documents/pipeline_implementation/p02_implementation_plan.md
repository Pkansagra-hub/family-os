# P02 Write Pipeline - K0 Implementation Plan

**Version:** 1.0.0
**Date:** 2025-11-13
**Status:** Planning
**Scope:** Pure K0 kernel implementation - Zero memoryOS_frozen dependencies

---

## 🎯 Executive Summary

Implement P02 Write Pipeline as a pure K0 kernel module that receives envelopes from the Outbox, enriches them through 7 processing stages, and writes to `st_hipp_store` for eventual P03 consolidation.

**Key Principles:**

- ✅ All implementations are pure K0 code
- ✅ Zero dependencies on memoryOS_frozen
- ✅ Leverage existing K0 infrastructure (pipelines, bus, syscalls)
- ✅ Use existing geohash handling from `k0/policy/location_privacy.py`

---

## 📊 Current State Analysis

### What K0 Already Has ✅

| Component | Location | Status |
|-----------|----------|--------|
| Pipeline Framework | `k0/pipelines/protocol.py`, `k0/pipelines/loader.py` | ✅ Complete |
| BusDispatcher | `k0/bus/core.py` | ✅ Topic routing ready |
| App.py Integration | `k0/kernel/app.py` | ✅ Lifespan with pipeline loader |
| Geohash Privacy | `k0/policy/location_privacy.py` | ✅ AMBER/RED masking |
| UnitOfWork | `k0/uow/unit_of_work.py` | ✅ Transaction management |
| Syscalls | `k0/kernel/syscalls.py` | ✅ Capability enforcement |
| Outbox Worker | `k0/kernel/app.py` | ✅ 5s polling loop |
| st_hipp_store Table | `migrations/0006_*.sql` | ⚠️ Missing 10 columns |

### What Needs to be Created 🆕

| Component | Type | Location | Purpose |
|-----------|------|----------|---------|
| Schema Migration | SQL | `k0/contracts/sql/migrations/` | Add 10 missing columns to st_hipp_store |
| P02 Pipeline | Python | `k0/pipelines/` | Main orchestrator implementing PipelineProtocol |
| **Hippocampus Module** | Python | `k0/modules/hippocampus/` | SimHash/MinHash pattern separation |
| **Memory Steward Module** | Python | `k0/modules/memory_steward/` | Consolidation routing logic (8 layers) |
| **Affect Module** | Python | `k0/modules/affect/` | Compute valence, arousal, tags |
| Space Module | Python | `k0/modules/space/` | Determine owner_id, co_owners, visible_to |
| Salience Module | Python | `k0/modules/salience/` | Importance scoring for working memory |
| Workspace Module | Python | `k0/modules/workspace/` | 8-slot working memory + broadcast |
| Syscalls Extension | Python | `k0/kernel/syscalls.py` | Add hipp_store methods |

---

## 🗄️ Schema Changes Required

### Migration: `0013_p02_write_pipeline_enhancements.sql`

**Add 10 Columns to st_hipp_store:**

#### Affect Analysis Fields (6 columns)

```sql
ALTER TABLE st_hipp_store ADD COLUMN affect_valence REAL;
ALTER TABLE st_hipp_store ADD COLUMN affect_arousal REAL;
ALTER TABLE st_hipp_store ADD COLUMN affect_tags TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_confidence REAL;
ALTER TABLE st_hipp_store ADD COLUMN affect_model_version TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_computed_at TEXT;
```

**Purpose**: Emotional intelligence from sentiment analysis

- `affect_valence`: -1.0 (negative) to 1.0 (positive)
- `affect_arousal`: 0.0 (calm) to 1.0 (excited)
- `affect_tags`: JSON array ["urgent", "toxic_light"]
- `affect_confidence`: Confidence score 0.0-1.0

#### Consolidation Routing Fields (4 columns)

```sql
ALTER TABLE st_hipp_store ADD COLUMN consolidation_target TEXT;
ALTER TABLE st_hipp_store ADD COLUMN consolidation_confidence REAL;
ALTER TABLE st_hipp_store ADD COLUMN consolidation_status TEXT
  DEFAULT 'PENDING'
  CHECK (consolidation_status IN ('PENDING', 'CONSOLIDATED', 'FAILED'));
ALTER TABLE st_hipp_store ADD COLUMN consolidated_at TEXT;
```

**Purpose**: P03 consolidation to 8 memory layers

- `consolidation_target`: epi|sem|proc|social|spatial|meta|working|prospective
- `consolidation_confidence`: 0.0-1.0
- `consolidation_status`: PENDING (initial) → CONSOLIDATED (after P03)

#### Indexes

```sql
CREATE INDEX idx_hipp_affect_valence ON st_hipp_store(affect_valence)
  WHERE affect_valence IS NOT NULL;
CREATE INDEX idx_hipp_consolidation ON st_hipp_store(consolidation_status)
  WHERE consolidation_status = 'PENDING';
```

**Note**: `location_geohash` and `location_precision_m` already exist in envelope processing via `k0/policy/location_privacy.py` ✅

---

## 🏗️ Module Architecture

### Directory Structure

```
k0/
├── modules/                           [NEW FOLDER] Cognitive assistant modules
│   ├── __init__.py                    [NEW] Module exports
│   ├── hippocampus/                   [NEW] Pattern separation
│   │   ├── __init__.py
│   │   ├── dentate_gyrus.py           SimHash/MinHash/novelty
│   │   └── pattern_separation.py      Duplicate detection
│   ├── memory_steward/                [NEW] Content classification
│   │   ├── __init__.py
│   │   ├── classifier.py              Consolidation routing logic
│   │   └── routing_rules.py           8 memory layer rules
│   ├── affect/                        [NEW] Sentiment analysis
│   │   ├── __init__.py
│   │   ├── analyzer.py                Valence/arousal computation
│   │   └── lexicon.py                 Emotion dictionary
│   ├── space/                         [NEW] Space resolution
│   │   ├── __init__.py
│   │   └── resolver.py                Owner/visibility determination
│   ├── salience/                      [NEW] Importance scoring
│   │   ├── __init__.py
│   │   └── scorer.py                  Working memory prioritization
│   └── workspace/                     [NEW] Working memory
│       ├── __init__.py
│       ├── manager.py                 8-slot working memory
│       └── broadcaster.py             Global workspace broadcast
├── pipelines/
│   └── p02_episodic_write.py          [NEW] Main P02 pipeline orchestrator
├── kernel/
│   └── syscalls.py                    [EXTEND] Add hipp_store methods
└── contracts/
    └── sql/
        └── migrations/
            └── 0013_p02_write_pipeline_enhancements.sql [NEW]
```

---

## 📦 Module Specifications

### Overview: Module Organization

All cognitive assistant modules live in `k0/modules/` and expose simple interfaces:

```python
# k0/modules/hippocampus/dentate_gyrus.py
def compute_pattern_separation(text: str, space_id: str) -> dict: ...

# k0/modules/memory_steward/classifier.py
def classify_memory(envelope: dict) -> dict: ...

# k0/modules/affect/analyzer.py
def analyze_affect(text: str, context: dict) -> dict: ...

# k0/modules/space/resolver.py
def resolve_space(actor: str, space_id: str, participants: list) -> dict: ...

# k0/modules/salience/scorer.py
def compute_salience(created_at: str, novelty: float, affect_tags: list) -> dict: ...

# k0/modules/workspace/manager.py
def update_working_memory(event_id: str, salience: float, summary: str) -> dict: ...
```

**P02 Pipeline orchestrates all modules sequentially.**

---

### 1. P02 Pipeline (`k0/pipelines/p02_episodic_write.py`)

**Contract:**

```python
pipeline_id = "P02"
contract_version = 1
declared_topics = ["cognitive.memory.write.committed.v1"]
concurrency = 1  # Sequential per space
max_queue = 512
required_caps = [
    "st_hipp_store.write",
    "st_pipeline_processed.write",
    "st_pipeline_status.write"
]
```

**Responsibilities:**

1. Subscribe to "cognitive.memory.write.committed.v1" via declared_topics
2. Parse BusMessage payload (envelope from Outbox)
3. Check idempotency (st_pipeline_processed)
4. Orchestrate 7 enrichment stages
5. Write to st_hipp_store via syscalls
6. Mark processed + emit receipt

**Processing Stages:**

```python
from k0.modules.space import resolver as space_resolver
from k0.modules.affect import analyzer as affect_analyzer
from k0.modules.hippocampus import dentate_gyrus as hippocampus
from k0.modules.memory_steward import classifier as memory_steward
from k0.modules.salience import scorer as salience_scorer
from k0.modules.workspace import manager as workspace_manager

# 1. Parse envelope → extract fields
envelope = msg.payload["envelope"]

# 2. Space module → owner_id, visible_to
space_data = space_resolver.resolve_space(
    actor=envelope["actor"],
    space_id=envelope["space_id"],
    participants=envelope.get("participants", [])
)

# 3. Affect module → valence, arousal, tags
affect_data = affect_analyzer.analyze_affect(
    text=envelope["payload"]["text"],
    context=envelope.get("context", {})
)

# 4. Hippocampus module → simhash, novelty, near_duplicates
hipp_data = hippocampus.compute_pattern_separation(
    text=envelope["payload"]["text"],
    space_id=envelope["space_id"]
)

# 5. Memory Steward module → consolidation_target
consolidation_data = memory_steward.classify_memory(envelope)

# 6. Salience module → salience score
salience_data = salience_scorer.compute_salience(
    created_at=envelope["created_at"],
    novelty=hipp_data["novelty"],
    affect_tags=affect_data["affect_tags"]
)

# 7. Workspace module → working memory + broadcast
workspace_manager.update_working_memory(
    event_id=envelope["event_id"],
    salience=salience_data["salience"],
    summary=envelope["payload"]["text"][:100]
)

# 8. Syscalls.hipp_store_upsert() → write enriched memory
# 9. Mark processed → idempotency watermark
```

**Error Handling:**

- Transient errors: Raise exception (BusDispatcher retries with backoff)
- Permanent errors: Log + emit ERROR receipt (don't raise)
- DLQ: After 5 retries, moved to st_dlq

**Performance Target:**

- P95 < 100ms per message
- Sequential processing (concurrency=1) for per-space ordering

---

### 2. Space Module (`k0/modules/space/resolver.py`)

**Purpose:** Determine memory ownership and visibility rules

**Input:**

```python
{
    "actor": "person-alice",
    "space_id": "shared:household",
    "participants": ["person-emma"],
    "policy": {"abac": {"roles": ["parent"]}}
}
```

**Logic:**

1. **Owner determination**: `owner_id = actor` (person who created memory)
2. **Co-owners**: If `shared:*` space and multiple participants → co-owners
3. **Visibility**: Based on space policy + ABAC roles
   - `personal:alice` → visible_to = ["person-alice"]
   - `shared:household` → visible_to = all household members
4. **Space validation**: Ensure actor has write permission

**Output:**

```python
{
    "owner_id": "person-alice",
    "co_owners": ["person-emma"],
    "visible_to": ["person-alice", "person-bob", "person-emma"],
    "space_validated": True
}
```

**Dependencies:** Pure K0 logic (no external dependencies)

---

### 3. Affect Module (`k0/modules/affect/analyzer.py`)

**Purpose:** Compute emotional valence and arousal from text

**Input:**

```python
{
    "text": "Reminder: Pick up Emma from soccer practice at 5pm on Friday",
    "context": {"urgency": "high"}
}
```

**Algorithm:**

1. **Lexicon-based scoring**: Check text against emotion dictionary
2. **VADER sentiment**: Use VADER for valence baseline
3. **Context signals**: Urgency markers (!, reminder, ASAP)
4. **Arousal estimation**: Exclamation marks, ALL CAPS, urgency keywords
5. **Confidence scoring**: Based on signal strength

**Output:**

```python
{
    "affect_valence": 0.1,           # -1.0 to 1.0 (neutral-positive)
    "affect_arousal": 0.4,           # 0.0 to 1.0 (moderate)
    "affect_tags": ["urgent"],       # JSON array
    "affect_confidence": 0.72,       # 0.0 to 1.0
    "affect_model_version": "k0-affect-v1.0",
    "affect_computed_at": "2025-11-13T14:23:46.050Z"
}
```

**Dependencies:** VADER library (optional), pure Python lexicon

---

### 4. Hippocampus Module (`k0/modules/hippocampus/dentate_gyrus.py`)

**Purpose:** Pattern separation via SimHash/MinHash

**Input:**

```python
{
    "text": "Reminder: Pick up Emma from soccer practice at 5pm on Friday",
    "space_id": "shared:household"
}
```

**Algorithms:**

**SimHash (512-bit):**

1. Tokenize text → k-grams (k=3)
2. Hash each k-gram to 512-bit vector
3. Weighted sum across all k-grams
4. Binarize: positive → 1, negative → 0
5. Result: `0xabcd1234...` (128 hex chars)

**MinHash (64 sketches):**

1. Apply 64 hash permutations
2. For each permutation, keep minimum hash
3. Result: `[12345, 67890, ...]` (64 integers)

**Novelty Scoring:**

1. Query existing memories in same space
2. Compute Hamming distance to top-K similar
3. Formula: `novelty = σ(6·(d_H/512) - 1·dup_rate)`
4. Range: [0.0, 1.0], higher = more novel

**Near-Duplicate Detection:**

1. Find memories with Jaccard similarity > 0.8
2. Return: `[["evt-123", 0.85], ["evt-456", 0.82]]`

**Output:**

```python
{
    "simhash_hex": "abcd1234ef567890...",
    "simhash_bits": 512,
    "minhash32": "[12345, 67890, 23456, ...]",
    "novelty": 0.73,
    "near_duplicates": [["evt-2025-11-10-00456", 0.82]],
    "hipp_version": "k0-dg-v1.0"
}
```

**Dependencies:** Pure Python (hashlib, no external libs)

---

### 5. Memory Steward Module (`k0/modules/memory_steward/classifier.py`)

**Purpose:** Classify memories for P03 consolidation routing

**Classification Rules:**

**Episodic (autobiographical events):**

- Has participants + location + temporal sequence
- Narrative structure
- Score: 0.3×participants + 0.2×location + 0.2×temporal + 0.2×event_type + 0.1×length

**Semantic (facts, concepts):**

- Timeless statements
- No specific temporal target
- Conceptual relationships
- Score: 0.3×timeless + 0.2×no_participants + 0.3×fact_type + 0.2×definition

**Procedural (skills, routines):**

- Step-by-step sequences
- Routine patterns
- Habitual actions
- Score: 0.4×routine + 0.3×steps + 0.2×repeated + 0.1×habit

**Social (relationships):**

- Multi-person interactions (≥2 participants)
- Relationship context
- Social dynamics
- Score: 0.3×multi_person + 0.3×relationship + 0.2×social_category + 0.2×affect

**Spatial (location-based):**

- Primary focus on location
- Navigation, wayfinding
- Place-specific events
- Score: 0.4×location + 0.3×coords + 0.2×navigation + 0.1×place_type

**Metacognitive (self-reflection):**

- Self-referential thoughts
- Learning strategies
- Mental state awareness
- Score: 0.3×reflection + 0.3×introspection + 0.2×learning + 0.2×realization

**Prospective (future intent):**

- Future temporal reference
- Intent markers ("will", "plan to", "remind me")
- Scheduled actions
- Score: 0.4×future_temporal + 0.3×target_time + 0.2×reminder + 0.1×intent

**Output:**

```python
{
    "consolidation_target": "prospective",  # Primary target
    "consolidation_confidence": 0.95,       # 0.0-1.0
    "consolidation_status": "PENDING",
    "secondary_targets": ["social", "spatial"]  # Optional multi-layer
}
```

**Dependencies:** Pure K0 rules-based logic

---

### 6. Salience Module (`k0/modules/salience/scorer.py`)

**Purpose:** Compute memory importance for working memory

**Formula:**

```
S = θ_r × recency           [0.9]
  + θ_n × novelty           [0.6]
  + θ_a × affect_nudge      [0.2]
  + θ_t × circadian_fit     [0.5]
  - θ_c × cost              [0.3]
```

**Input:**

```python
{
    "created_at": "2025-11-13T14:23:45Z",
    "novelty": 0.73,
    "affect_tags": ["urgent"],
    "activity_type": "reminder"
}
```

**Scoring:**

1. **Recency**: `2^(-Δt/72hr)` (exponential decay, 72hr half-life)
2. **Novelty**: From hippocampus_dg (0.0-1.0)
3. **Affect nudge**: +0.1 if "urgent" in tags
4. **Circadian fit**: Time-of-day alignment (morning/afternoon/evening)
5. **Cost**: Compute cost (~0.05 for simple memory)

**Normalization:**

- Raw score: Sum weighted components
- Normalized: softmax(T=0.6) → [0.0, 1.0]

**Output:**

```python
{
    "salience": 0.81,  # Normalized score
    "components": {
        "recency": 1.0,
        "novelty": 0.73,
        "affect_nudge": 0.1,
        "circadian_fit": 0.6,
        "cost": 0.05
    }
}
```

**Dependencies:** Pure K0 math (no external libs)

---

### 7. Workspace Module (`k0/modules/workspace/manager.py`)

**Purpose:** Update working memory and broadcast to global workspace

**Working Memory (8 slots):**

- Decay-based eviction (half-life 90s)
- Weight-based sorting (highest salience first)
- Slot capacity: 8 memories

**Operations:**

1. **Update**: Insert new memory, decay existing, evict lowest weight if >8 slots
2. **Broadcast**: Publish to BusDispatcher topic "workspace.broadcast.v1"

**Input:**

```python
{
    "event_id": "evt-2025-11-13-00123",
    "salience": 0.81,
    "summary": "Reminder: Pick up Emma from soccer practice",
    "expires_at": "2025-11-13T14:28:46Z"  # +5 minutes
}
```

**Working Memory State:**

```python
{
    "slots": [
        {
            "slot": 0,
            "event_id": "evt-2025-11-13-00123",
            "weight": 0.81,
            "summary": "Reminder: Pick up Emma...",
            "expires_at": "2025-11-13T14:28:46Z"
        },
        # ... 7 more slots
    ],
    "decay_rate": 0.5,
    "half_life_s": 90
}
```

**Workspace Broadcast:**

```python
{
    "topic": "workspace.broadcast.v1",
    "payload": {
        "space_id": "shared:household",
        "wm": {
            "slots": [...],  # All 8 slots
            "context": {
                "band": "AMBER",
                "time_budget_ms": 25,
                "now": "2025-11-13T14:23:46.200Z"
            }
        },
        "trace_id": "trace-abc123"
    }
}
```

**Subscribers:**

- Arbiter (action planning)
- Retrieval (context-aware search)
- Learning (reinforcement signals)
- Prospective (reminder scheduling)

**Dependencies:** BusDispatcher for broadcast

---

### 8. Syscalls Extension (`k0/kernel/syscalls.py`)

**Add 3 Methods:**

#### `hipp_store_upsert(space_id, event_id, payload, cognitive_trace_id)`

- **Capability**: `"st_hipp_store.write"`
- **Purpose**: Insert enriched memory (74 columns)
- **Returns**: None (raises on error)

#### `mark_processed(pipeline_id, space_id, wal_pos, processed_at)`

- **Capability**: `"st_pipeline_processed.write"`
- **Purpose**: Idempotency watermark
- **Table**: `st_pipeline_processed`

#### `emit_receipt(pipeline_id, wal_pos, status, duration_ms, updated_at)`

- **Capability**: `"st_pipeline_status.write"`
- **Purpose**: Pipeline processing receipt
- **Table**: `st_pipeline_status`

---

## 🔄 Data Flow (End-to-End)

```
1. K1 Envelope
   ↓
2. POST /k0/command.submit → Gate validates
   ↓
3. Policy Enforcement → apply_location_privacy() [EXISTING]
   ↓ (location_geohash + location_precision_m added to envelope)
4. UnitOfWork → WAL + Outbox commit
   ↓
5. st_outbox row created
   topic: "cognitive.memory.write.committed.v1"
   payload: {wal_pos, space_id, event_id, envelope}
   ↓
6. Outbox Worker Loop (app.py) [EXISTING]
   polls st_outbox every 5s
   ↓
7. BusDispatcher.dispatch(messages)
   ↓
8. P02.handle(msg) [AUTO-SUBSCRIBED via declared_topics]
   ↓
   8a. Parse envelope from msg.payload
   8b. Check idempotency (st_pipeline_processed)
   8c. Space Resolver → owner_id, co_owners, visible_to
   8d. Affect Analyzer → valence, arousal, tags
   8e. Hippocampus DG → simhash, novelty, near_duplicates
   8f. Content Classifier → consolidation_target
   8g. Salience Scorer → salience
   8h. Syscalls.hipp_store_upsert() → st_hipp_store (74 columns)
   8i. Workspace Manager → working memory + broadcast
   8j. Mark processed (st_pipeline_processed)
   8k. Emit receipt (st_pipeline_status)
   ↓
9. st_hipp_store row created (all enrichment fields populated)
   ↓
10. Workspace broadcast → downstream services
    (arbiter, retrieval, learning, prospective)
```

**Zero memoryOS_frozen dependencies** ✅

---

## 📋 Implementation Phases

### Phase 1: Schema Migration (Day 1)

**Tasks:**

1. Create `0013_p02_write_pipeline_enhancements.sql`
2. Add 10 columns (6 affect + 4 consolidation)
3. Add indexes (affect_valence, consolidation_status)
4. Test migration locally
5. Verify column count: 64 + 10 = 74 columns

**Deliverables:**

- Migration file in `k0/contracts/sql/migrations/`
- Migration tested against local K0 database

---

### Phase 2: Core K0 Modules (Days 2-5)

**Day 2: Core Modules (Space, Affect, Hippocampus)**

1. `k0/modules/space/resolver.py` - Owner/visibility determination
2. `k0/modules/affect/analyzer.py` - Sentiment analysis (VADER + lexicon)
3. `k0/modules/affect/lexicon.py` - Emotion dictionary

**Day 3: Hippocampus Module**

4. `k0/modules/hippocampus/dentate_gyrus.py` - SimHash/MinHash/novelty
5. `k0/modules/hippocampus/pattern_separation.py` - Duplicate detection

**Day 4: Memory Steward & Salience**

6. `k0/modules/memory_steward/classifier.py` - Consolidation routing
7. `k0/modules/memory_steward/routing_rules.py` - 8 memory layer rules
8. `k0/modules/salience/scorer.py` - Importance scoring

**Day 5: Workspace & Syscalls**

9. `k0/modules/workspace/manager.py` - 8-slot working memory
10. `k0/modules/workspace/broadcaster.py` - Global workspace broadcast
11. `k0/kernel/syscalls.py` - Add 3 new methods

**Deliverables:**

- `k0/modules/` folder with 6 module packages
- 11 new module files with docstrings
- Unit tests for each module
- Zero imports from memoryOS_frozen

---

### Phase 3: P02 Pipeline Integration (Days 6-7)

**Day 6: Pipeline Implementation**

1. Create `k0/pipelines/p02_episodic_write.py`
2. Implement PipelineProtocol contract
3. Wire all 7 enrichment stages
4. Add error handling + logging

**Day 7: Orchestration & Error Handling**
5. Idempotency checks (st_pipeline_processed)
6. Receipt emission (st_pipeline_status)
7. Retry logic for transient errors
8. DLQ handling for permanent errors

**Deliverables:**

- Complete P02 pipeline
- Auto-discovered by loader (p*.py pattern)
- Auto-subscribed to "cognitive.memory.write.committed.v1"

---

### Phase 4: Testing & Validation (Days 8-10)

**Day 8: Unit Tests**

1. Test each module individually
2. Mock dependencies (syscalls, BusMessage)
3. Coverage target: >80%

**Day 9: Integration Tests**

1. End-to-end: K1 envelope → P02 → st_hipp_store
2. Verify all 74 columns populated
3. Test idempotency (duplicate messages)
4. Test error scenarios (transient, permanent)

**Day 10: Performance & Load Testing**

1. Measure P95 latency (<100ms target)
2. Load test: 1000 messages/min
3. Memory profiling (no leaks)
4. Verify workspace broadcast delivery

**Deliverables:**

- Test suite in `tests/k0/pipelines/test_p02.py`
- Performance report
- Integration test documentation

---

## 🎯 Success Criteria

### Functional Requirements ✅

- [ ] P02 pipeline auto-discovered by loader
- [ ] Subscribes to "cognitive.memory.write.committed.v1"
- [ ] All 74 columns populated in st_hipp_store
- [ ] Idempotency: Duplicate messages handled correctly
- [ ] Error handling: Transient errors retry, permanent errors → DLQ
- [ ] Workspace broadcast delivered to subscribers

### Performance Requirements ✅

- [ ] P95 latency < 100ms per message
- [ ] Throughput: >1000 messages/min
- [ ] Memory: No leaks after 10K messages
- [ ] CPU: <50% utilization at 500 msg/min

### Code Quality Requirements ✅

- [ ] Zero imports from memoryOS_frozen
- [ ] All modules have docstrings
- [ ] Unit test coverage >80%
- [ ] Integration tests pass
- [ ] Type hints on all functions
- [ ] Logging with cognitive_trace_id

---

## 🚫 Anti-Patterns (What NOT to Do)

### ❌ DO NOT

1. Import anything from `memoryOS_frozen/`
2. Modify existing pipeline framework (protocol.py, loader.py)
3. Change app.py lifespan (already correct)
4. Modify BusDispatcher API
5. Add geohash columns to st_hipp_store (already in envelope)
6. Call frozen module functions
7. Create bridges/adapters to frozen code

### ✅ DO

1. Create pure K0 implementations
2. Use existing K0 infrastructure (pipelines, bus, syscalls)
3. Leverage existing geohash handling (`k0/policy/location_privacy.py`)
4. Follow PipelineProtocol contract
5. Use BusDispatcher topic subscriptions
6. Write comprehensive tests
7. Log with structured context (trace_id, space_id)

---

## 📚 Reference Documentation

### Internal Docs

- `docs/versioning_documents/pipeline_implementation/p02_writepipeline.md` - Complete spec
- `k0/pipelines/protocol.py` - Pipeline contract
- `k0/pipelines/loader.py` - Auto-discovery
- `k0/bus/core.py` - Topic routing
- `k0/policy/location_privacy.py` - Geohash handling

### Schema

- `k0/contracts/sql/migrations/0006_phase1_core_memory_foundation.sql` - st_hipp_store base
- `k0/contracts/sql/migrations/0012_pipeline_infrastructure.sql` - st_pipeline_processed/status

### Research Citations

- SimHash: Charikar 2002 (similarity-preserving hash functions)
- MinHash: Broder 1997 (Jaccard similarity estimation)
- VADER: Hutto & Gilbert 2014 (sentiment analysis)
- Pipeline pattern: Hohpe & Woolf 2003 (Enterprise Integration Patterns)

---

## 🔍 Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Performance degradation | High | Profiling + caching + batch operations |
| Memory leaks | High | Bounded queues + memory profiling |
| Idempotency bugs | Medium | Comprehensive watermark tests |
| Error handling gaps | Medium | Test all error paths + DLQ verification |
| Schema migration issues | Low | Test on dev DB first, rollback plan |
| Integration gaps | Medium | End-to-end tests before production |

---

## 📅 Timeline

| Phase | Duration | Dates (Example) | Owner |
|-------|----------|-----------------|-------|
| Phase 1: Schema | 1 day | Day 1 | TBD |
| Phase 2: Core Modules | 4 days | Days 2-5 | TBD |
| Phase 3: P02 Pipeline | 2 days | Days 6-7 | TBD |
| Phase 4: Testing | 3 days | Days 8-10 | TBD |
| **Total** | **10 days** | - | - |

---

## ✅ Acceptance Checklist

Before marking P02 as complete:

### Schema ✅

- [ ] Migration 0013 applied successfully
- [ ] 10 new columns exist in st_hipp_store
- [ ] Indexes created (affect_valence, consolidation_status)

### Code ✅

- [ ] `k0/modules/` folder created with 6 module packages
- [ ] 3 core modules: hippocampus, memory_steward, affect
- [ ] 3 support modules: space, salience, workspace
- [ ] P02 pipeline implements PipelineProtocol
- [ ] Pipeline imports from k0.modules.* (not k0.kernel)
- [ ] Zero imports from memoryOS_frozen
- [ ] Type hints on all functions
- [ ] Docstrings on all classes/functions

### Testing ✅

- [ ] Unit tests pass (>80% coverage)
- [ ] Integration tests pass (envelope → st_hipp_store)
- [ ] Performance tests pass (P95 < 100ms)
- [ ] Idempotency tests pass (duplicate handling)
- [ ] Error handling tests pass (transient, permanent, DLQ)

### Integration ✅

- [ ] P02 auto-discovered by pipeline loader
- [ ] Subscribed to "cognitive.memory.write.committed.v1"
- [ ] Workspace broadcast delivered to subscribers
- [ ] Observability: trace_id in all logs
- [ ] Metrics: p02_messages_processed_total increments

### Documentation ✅

- [ ] README.md in `k0/pipelines/` updated
- [ ] Architecture diagrams updated (if needed)
- [ ] Runbook created for P02 troubleshooting

---

## 🎉 Completion Criteria

**P02 Write Pipeline is complete when:**

1. ✅ All 74 columns in st_hipp_store populated correctly
2. ✅ Performance: P95 < 100ms, throughput >1000 msg/min
3. ✅ Quality: >80% test coverage, zero frozen imports
4. ✅ Integration: Auto-discovered, subscribed, broadcasting
5. ✅ Observability: Metrics, logs, traces all working
6. ✅ End-to-end test: K1 envelope → P02 → st_hipp_store → workspace broadcast

---

**Version History:**

- v1.0.0 (2025-11-13): Initial planning document
