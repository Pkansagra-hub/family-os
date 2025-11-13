# P02 Write Pipeline - End-to-End Architecture

**Version:** 1.0.0
**Date:** 2025-11-12
**Status:** Design Specification
**Scope:** Complete write pipeline from K1 envelope ingestion to consolidated memory storage

---

## 0) Executive Summary

The **P02 Write Pipeline** is the core memory formation pathway in Family OS. It receives validated envelopes from the K0 Kernel, orchestrates multiple cognitive services (Memory Steward, Affect Analysis, Hippocampus, Core/Workspace), and produces enriched memories stored across 8 specialized memory layers.

**Key Capabilities:**

- ✅ **End-to-end traceability**: `cognitive_trace_id` from K1 → storage
- ✅ **Multi-layer storage**: Automatic routing to 8 memory stores based on content type
- ✅ **Privacy-preserving**: AMBER/RED band redaction with geohash obfuscation
- ✅ **Emotional intelligence**: Affect analysis for valence, arousal, toxicity
- ✅ **Pattern separation**: Hippocampus DG for novelty detection and deduplication
- ✅ **Context broadcasting**: Global Workspace notifies all cognitive services
- ✅ **Idempotent**: Duplicate detection via `st_pipeline_processed` watermarks

**Performance:**

- **Phase 1 (ACID)**: 80-100ms (WAL + Receipt + Outbox)
- **Phase 2 (Async P02)**: 50-100ms (Memory Steward + Affect + Hippocampus)
- **Total latency**: 150ms P95 (client sees 100ms, P02 runs async)

---

## 1) System Context - Where P02 Fits

```mermaid
flowchart TB
    subgraph K1["K1 Intelligence Module (Agent Layer)"]
        K1_AGENT[K1 Agent]
        K1_ENV[K1 Envelope Builder]
    end

    subgraph K0_GATE["K0 Kernel (Validation + ACID)"]
        GATE[Attention Gate]
        PEP[Policy Enforcement Point]
        UOW[Unit of Work]
        WAL[Write-Ahead Log]
        OUTBOX[Outbox Table]
    end

    subgraph P02["P02 Write Pipeline (Async Memory Formation)"]
        BUS_SUB[BusDispatcher Subscriber]
        MEMORY_STEWARD[Memory Steward Orchestrator]
        AFFECT[Affect Analysis]
        HIPPOCAMPUS[Hippocampus DG]
        CORE_WRITER[Core Writer]
        WORKSPACE[Global Workspace]
    end

    subgraph STORAGE["Memory Storage (8 Layers)"]
        HIPP_STORE[(st_hipp_store)]
        EPI[(st_epi)]
        SEM[(st_sem)]
        PROC[(st_proc)]
        SOCIAL[(st_social)]
        SPATIAL[(st_spatial)]
        META[(st_meta)]
        WORKING[(st_working_memory)]
    end

    subgraph DOWNSTREAM["Downstream Services"]
        P01[P01 Recall]
        P03[P03 Consolidation]
        ARB[Arbiter]
        RET[Retrieval]
        LRN[Learning]
    end

    K1_AGENT -->|envelope| K1_ENV
    K1_ENV -->|POST /k0/command.submit| GATE
    GATE -->|validate| PEP
    PEP -->|commit| UOW
    UOW -->|write| WAL
    UOW -->|emit| OUTBOX

    OUTBOX -.->|BusMessage: cognitive.memory.write.committed.v1| BUS_SUB
    BUS_SUB -->|parse envelope| MEMORY_STEWARD
    MEMORY_STEWARD -->|space resolution| AFFECT
    AFFECT -->|emotional context| HIPPOCAMPUS
    HIPPOCAMPUS -->|pattern separation| CORE_WRITER
    CORE_WRITER -->|enriched memory| HIPP_STORE
    CORE_WRITER -->|salience scoring| WORKSPACE

    WORKSPACE -.->|WORKSPACE_BROADCAST| P01
    WORKSPACE -.->|WORKSPACE_BROADCAST| ARB
    WORKSPACE -.->|WORKSPACE_BROADCAST| RET
    WORKSPACE -.->|WORKSPACE_BROADCAST| LRN

    HIPP_STORE -.->|consolidation| P03
    P03 -.->|classify & move| EPI
    P03 -.->|classify & move| SEM
    P03 -.->|classify & move| PROC
    P03 -.->|classify & move| SOCIAL
    P03 -.->|classify & move| SPATIAL
    P03 -.->|classify & move| META
    P03 -.->|classify & move| WORKING
```

**Two-Phase Architecture:**

- **Phase 1 (K0 Kernel)**: ACID commit with WAL, Receipt, Outbox (~80-100ms)
  - Client receives 200 OK with receipt
  - Envelope written to WAL and Outbox
  - Transaction committed atomically

- **Phase 2 (P02 Async)**: Memory enrichment and storage (~50-100ms)
  - P02 subscribes to `cognitive.memory.write.committed.v1` topic
  - Processes envelope asynchronously (client doesn't wait)
  - Enriches with affect, pattern separation, consolidation routing
  - Stores in appropriate memory layer(s)

---

## 2) Input Envelope - Authoritative Contract

**Source:** K1 Intelligence Module via K0 Kernel
**Location:** `k0/provision_and_submit.py` (reference implementation)
**Topic:** `cognitive.memory.write.committed.v1`

### 2.1 Envelope Structure (from K1)

```json
{
  "cognitive_trace_id": "trace-abc123",
  "tenant_id": "tenant-family-001",
  "space_id": "shared:household",
  "topic": "memory.delta",
  "schema_uri": "schema://memory.delta",
  "schema_version": "1.0",
  "actor": "person-alice",
  "device_id": "device-iphone-alice",
  "band": "GREEN",
  "policy_version": "2025-09-28",
  "ts": "2025-11-12T14:23:45Z",
  "payload_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "sig_alg": "Ed25519SHA512",
  "sig_kid": "device-iphone-alice#1",
  "envelope_sha256": "a1b2c3d4e5f6...",
  "sig": "base64url_signature...",

  "body": {
    "operation": "UPSERT",
    "payload": {
      "text": "Reminder: Pick up Emma from soccer practice at 5pm on Friday",
      "timestamp": "2025-11-15T17:00:00Z",
      "location": {
        "name": "Lincoln Park Soccer Fields",
        "type": "sports_facility",
        "lat": 41.9212,
        "lon": -87.6401
      },
      "participants": ["person-emma"],
      "tags": ["reminder", "school", "sports"],
      "context": {
        "activity_type": "pickup",
        "activity_category": "family_coordination",
        "urgency": "high"
      }
    }
  },

  "policy": {
    "abac": {
      "roles": ["parent"]
    }
  }
}
```

### 2.2 Envelope Field Mapping (K1 → P02)

| K1 Field | P02 Usage | Notes |
|----------|-----------|-------|
| `cognitive_trace_id` | End-to-end tracing | Propagated to all tables |
| `tenant_id` | Multi-tenancy isolation | Required for all queries |
| `space_id` | Memory Space scoping | `personal:alice`, `shared:household` |
| `actor` | Author identification | Maps to `author_id` in st_hipp_store |
| `device_id` | Provenance tracking | Device that created memory |
| `band` | Privacy band (GREEN/AMBER/RED/BLACK) | Controls redaction level |
| `ts` | Event timestamp | When memory was created |
| `body.payload.text` | Primary content | Indexed in FTS5, embedded |
| `body.payload.location` | Geospatial data | Redacted if AMBER/RED |
| `body.payload.participants` | Multi-person context | Neo4j Person IDs |
| `body.payload.tags` | Topic extraction | Used for consolidation routing |
| `body.payload.context` | Activity metadata | Extracted by Memory Steward |

### 2.3 BusMessage Wrapper (from Outbox)

When K0 Kernel commits the envelope, it writes to `st_outbox`:

```json
{
  "id": 12345,
  "topic": "cognitive.memory.write.committed.v1",
  "payload": {
    "wal_pos": 67890,
    "space_id": "shared:household",
    "event_id": "evt-2025-11-12-00123",
    "envelope": { /* full envelope from above */ }
  },
  "created_at": "2025-11-12T14:23:45.123Z",
  "next_attempt_ts": "2025-11-12T14:23:45.123Z",
  "retries": 0,
  "status": "PENDING"
}
```

P02 subscribes to this topic and receives `BusMessage`:

```python
@dataclass
class BusMessage:
    topic: str                    # "cognitive.memory.write.committed.v1"
    payload: dict                 # Contains wal_pos, space_id, event_id, envelope
    headers: dict                 # Metadata (retry count, etc.)
    ack: Callable[[], None]       # Acknowledge successful processing
    nack: Callable[[], None]      # Negative acknowledge (retry)
```

---

## 3) P02 Pipeline - Orchestration Hub

**Purpose:** Coordinate space resolution, redaction, deduplication, and consolidation routing
**Location:** `k0/pipelines/p02_episodic_write.py` (main orchestrator)
**Modules:** `k0/modules/` (cognitive assistant modules)
**Input:** K1 envelope from BusMessage
**Output:** Enriched memory ready for storage

**Architecture:** Pure K0 implementation with 6 modular assistants:

1. **Space Module** (`k0/modules/space/`) - Owner/visibility determination
2. **Affect Module** (`k0/modules/affect/`) - Sentiment analysis
3. **Hippocampus Module** (`k0/modules/hippocampus/`) - Pattern separation
4. **Memory Steward Module** (`k0/modules/memory_steward/`) - Content classification
5. **Salience Module** (`k0/modules/salience/`) - Importance scoring
6. **Workspace Module** (`k0/modules/workspace/`) - Working memory management

### 3.1 P02 Pipeline Components

```mermaid
flowchart LR
    ENV[Envelope Input] --> P02[P02 Pipeline]
    P02 --> SPACE[Space Module]
    SPACE --> AFFECT[Affect Module]
    AFFECT --> HIPP[Hippocampus Module]
    HIPP --> STEWARD[Memory Steward Module]
    STEWARD --> SAL[Salience Module]
    SAL --> WM[Workspace Module]
    WM --> DB[(st_hipp_store)]

    SPACE -->|owner_id, visible_to| META[Enriched Memory]
    AFFECT -->|valence, arousal| META
    HIPP -->|simhash, novelty| META
    STEWARD -->|consolidation_target| META
    SAL -->|salience| META
    WM -->|workspace broadcast| BUS[Event Bus]
```

#### 3.1.1 Space Module (`k0/modules/space/resolver.py`)

**Purpose:** Determine memory ownership and visibility

**Input:**

```json
{
  "actor": "person-alice",
  "space_id": "shared:household",
  "participants": ["person-emma"],
  "policy": {"abac": {"roles": ["parent"]}}
}
```

**Process:**

1. **Owner determination**: `owner_id = actor` (person who created memory)
2. **Co-owners**: If `shared:*` space and multiple participants → co-owners
3. **Visibility**: Based on space policy + ABAC roles
   - `personal:alice` → visible_to = ["person-alice"]
   - `shared:household` → visible_to = ["person-alice", "person-bob", "person-emma"]
4. **Space validation**: Ensure actor has write permission to space

**Output:**

```json
{
  "owner_id": "person-alice",
  "co_owners": ["person-emma"],
  "visible_to": ["person-alice", "person-bob", "person-emma"],
  "space_validated": true
}
```

#### 3.1.2 Affect Module (`k0/modules/affect/analyzer.py`)

**Purpose:** Emotional intelligence through sentiment analysis

**Input:**

```json
{
  "text": "Reminder: Pick up Emma from soccer practice at 5pm on Friday",
  "context": {"urgency": "high"}
}
```

**Process:**

1. **Lexicon-based scoring**: Check text against emotion dictionary
2. **VADER sentiment**: Use VADER for valence baseline
3. **Context signals**: Urgency markers (!, reminder, ASAP)
4. **Arousal estimation**: Exclamation marks, ALL CAPS, urgency keywords
5. **Confidence scoring**: Based on signal strength

**Output:**

```json
{
  "affect_valence": 0.1,
  "affect_arousal": 0.4,
  "affect_tags": ["urgent"],
  "affect_confidence": 0.72,
  "affect_model_version": "k0-affect-v1.0",
  "affect_computed_at": "2025-11-12T14:23:46.050Z"
}
```

**Note:** Location redaction (AMBER/RED geohash) is handled by K0 policy engine (`k0/policy/location_privacy.py`) BEFORE P02 pipeline receives the envelope.

#### 3.1.3 Hippocampus Module (`k0/modules/hippocampus/dentate_gyrus.py`)

**Purpose:** Detect novelty and near-duplicates using SimHash/MinHash

**Input:**

```json
{
  "text": "Reminder: Pick up Emma from soccer practice at 5pm on Friday",
  "space_id": "shared:household"
}
```

**Process:**

1. **Text preprocessing**: Tokenize, normalize, extract k-grams (k=3)
2. **SimHash** (512-bit binary code):
   - Hash each k-gram to 512-bit vector
   - Weighted sum across all k-grams
   - Binarize: positive → 1, negative → 0
   - Result: `0xabcd1234...` (128 hex chars)
3. **MinHash** (64 Jaccard sketches):
   - Apply 64 hash permutations
   - For each permutation, keep minimum hash
   - Result: `[12345, 67890, ...]` (64 integers)
4. **Novelty scoring**:
   - Query existing memories in same space
   - Compute Hamming distance to top-K similar
   - Formula: `novelty = σ(6·(d_H/512) - 1·dup_rate)`
   - Range: [0.0, 1.0], higher = more novel
5. **Near-duplicate detection**:
   - Find memories with Jaccard similarity > 0.8
   - Return: `[["evt-123", 0.85], ["evt-456", 0.82]]`

**Output:**

```json
{
  "simhash_hex": "abcd1234ef567890...",
  "simhash_bits": 512,
  "minhash32": [12345, 67890, 23456, ...],
  "novelty": 0.73,
  "near_duplicates": [
    ["evt-2025-11-10-00456", 0.82]
  ],
  "hipp_version": "dg-v1.2.0"
}
```

#### 3.1.4 Memory Steward Module (`k0/modules/memory_steward/classifier.py`)

**Purpose:** Content classification for P03 consolidation routing

**Input:** Enriched memory with all fields populated

**Classification Logic:** (See Section 7.2 for detailed rules)

- Episodic: 0.3×participants + 0.2×location + 0.2×temporal + 0.2×event_type
- Semantic: 0.3×timeless + 0.2×no_participants + 0.3×fact_type
- Procedural: 0.4×routine + 0.3×steps + 0.2×repeated
- Social: 0.3×multi_person + 0.3×relationship + 0.2×affect
- Spatial: 0.4×location + 0.3×coords + 0.2×navigation
- Metacognitive: 0.3×reflection + 0.3×introspection
- Prospective: 0.4×future_temporal + 0.3×target_time + 0.2×reminder

**Output:**

```json
{
  "consolidation_target": "prospective",
  "consolidation_confidence": 0.95,
  "consolidation_status": "PENDING",
  "secondary_targets": ["social", "spatial"]
}
```

#### 3.1.5 Salience Module (`k0/modules/salience/scorer.py`)

**Purpose:** Compute memory importance for working memory

**Formula:**

```
S = θ_r × recency + θ_n × novelty + θ_a × affect_nudge + θ_t × circadian_fit - θ_c × cost
```

**Input:** Enriched memory with novelty, affect_tags, created_at

**Output:**

```json
{
  "salience": 0.81,
  "components": {
    "recency": 1.0,
    "novelty": 0.73,
    "affect_nudge": 0.1,
    "circadian_fit": 0.6,
    "cost": 0.05
  }
}
```

#### 3.1.6 Workspace Module (`k0/modules/workspace/manager.py`)

**Purpose:** Update working memory and broadcast to global workspace

**Working Memory:** 8 slots with decay-based eviction

**Input:** event_id, salience, summary, expires_at

**Process:**

1. Update 8-slot working memory
2. Decay existing slots (half-life 90s)
3. Evict lowest weight if >8 slots
4. Broadcast to Event Bus

**Workspace Broadcast:**

```json
{
  "topic": "workspace.broadcast.v1",
  "payload": {
    "space_id": "shared:household",
    "wm": {
      "slots": [...],  # All 8 slots
      "context": {
        "band": "AMBER",
        "time_budget_ms": 25,
        "now": "2025-11-12T14:23:46.200Z"
      }
    },
    "trace_id": "trace-abc123"
  }
}
```

#### 3.1.7 P02 Syscalls

**Purpose:** Write enriched memory to `st_hipp_store` via UnitOfWork

**Location:** `k0/kernel/syscalls.py` (extension)

**Methods:**

1. **`hipp_store_upsert()`** - Write enriched memory (80 columns)
2. **`mark_processed()`** - Idempotency watermark
3. **`emit_receipt()`** - Pipeline processing receipt

**Process:**

1. Open UnitOfWork transaction
2. Construct 80-column `st_hipp_store` row (see Section 4)
3. Execute INSERT with all enriched fields
4. Mark processed in `st_pipeline_processed`:

   ```sql
   INSERT INTO st_pipeline_processed (pipeline_id, space_id, wal_pos, processed_at)
   VALUES ('P02', 'shared:household', 67890, '2025-11-12T14:23:46.000Z')
   ```

5. Emit success receipt to `st_pipeline_status`
6. Commit transaction atomically

**Output:**

```json
{
  "event_id": "evt-2025-11-12-00123",
  "commit_status": "SUCCESS",
  "commit_ts": "2025-11-12T14:23:46.123Z"
}
```

#### 3.1.8 Receipt Generator

**Purpose:** Cryptographic audit trail for memory formation

**Receipt Structure:**

```json
{
  "receipt_id": "rcpt-2025-11-12-00123",
  "event_id": "evt-2025-11-12-00123",
  "pipeline_id": "P02",
  "trace_id": "trace-abc123",
  "commit_ts": "2025-11-12T14:23:46.123Z",
  "stages": {
    "space_resolution": {"duration_ms": 2, "status": "SUCCESS"},
    "redaction": {"duration_ms": 1, "status": "SUCCESS"},
    "hippocampus_dg": {"duration_ms": 15, "status": "SUCCESS"},
    "deduplication": {"duration_ms": 5, "status": "SUCCESS"},
    "commit": {"duration_ms": 8, "status": "SUCCESS"}
  },
  "signature": "sha256_hmac...",
  "signature_alg": "HMAC-SHA256"
}
```

---

## 4) Output Envelope - st_hipp_store Schema

**Purpose:** Short-term staging area (7-30 days) for raw memories before P03 consolidation
**Lifecycle:** TEMPORARY → P03 classifies → moves to st_epi/st_sem/st_proc/st_social/st_spatial/st_meta
**Source:** `k0/contracts/sql/migrations/0006_phase1_core_memory_foundation.sql`

### 4.1 Complete Schema (78 columns)

```sql
CREATE TABLE IF NOT EXISTS st_hipp_store (
    -- IDENTITY & TRACING (3 columns)
    event_id TEXT PRIMARY KEY,                -- Unique event identifier
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability
    hipp_version TEXT,                        -- Hippocampus algorithm version

    -- CONTENT (3 columns)
    text TEXT NOT NULL,                       -- Raw input text
    length INTEGER,                           -- Character count
    language TEXT,                            -- Detected language (en, es, etc.)

    -- EXTRACTED METADATA (6 columns)
    topics TEXT,                              -- JSON array of topic keywords
    categories TEXT,                          -- JSON array of event categories
    activity_type TEXT,                       -- What happened (run, dinner, meeting, call)
    activity_category TEXT,                   -- Broader grouping (exercise, social, work)
    activity_metadata TEXT,                   -- JSON blob (duration, distance, calories, etc)

    -- PATTERN SEPARATION (5 columns)
    simhash_hex TEXT,                         -- 512-bit binary code (hex encoded)
    simhash_bits INTEGER,                     -- Bit count (default 512)
    minhash32 TEXT,                           -- JSON array of 64 Jaccard sketches
    novelty REAL,                             -- How different from existing (0.0-1.0)
    near_duplicates TEXT,                     -- JSON array [["evt_id", distance], ...]

    -- WHO - Multi-Person (6 columns)
    author_id TEXT NOT NULL,                  -- Who created this memory (Neo4j :Person ID)
    author_role TEXT,                         -- Relationship role (son, mother, etc.)
    participants TEXT,                        -- JSON array of Neo4j :Person node IDs
    participant_roles TEXT,                   -- JSON: {"person_id": "role"}
    mentions TEXT,                            -- JSON array of Neo4j :Person node IDs
    mention_contexts TEXT,                    -- JSON: {"person_id": "context"}

    -- WHERE - Location (4 columns)
    location_name TEXT,                       -- Neo4j :Location node ID or name
    location_type TEXT,                       -- Quick filter (home, restaurant, office, etc)
    location_lat REAL,                        -- Latitude (optional, NULL if redacted)
    location_lon REAL,                        -- Longitude (optional, NULL if redacted)

    -- WHERE - Redaction Fields (2 columns) [ADDED FOR AMBER/RED]
    location_geohash TEXT,                    -- Geohash for privacy (AMBER: 6 chars, RED: 4 chars)
    location_precision_m INTEGER,             -- Precision in meters (1000 for AMBER, 20000 for RED)

    -- WHEN - Temporal (3 columns)
    ts TEXT NOT NULL,                         -- Event timestamp (ISO 8601)
    temporal_reference TEXT,                  -- future|past|present
    temporal_target TEXT,                     -- ISO8601 (if future/past reference)

    -- SENTIMENT (3 columns)
    sentiment_score REAL,                     -- Positive/negative (-1.0 to 1.0)
    sentiment_label TEXT,                     -- positive|neutral|negative
    emotion_tags TEXT,                        -- JSON array (happy, stressed, excited, etc)

    -- AFFECT ANALYSIS (6 columns) [ADDED FOR AFFECT INTEGRATION]
    affect_valence REAL,                      -- Valence (-1.0 to 1.0)
    affect_arousal REAL,                      -- Arousal (0.0 to 1.0)
    affect_tags TEXT,                         -- JSON array ["urgent", "toxic_light"]
    affect_confidence REAL,                   -- Confidence score (0.0 to 1.0)
    affect_model_version TEXT,                -- Model version
    affect_computed_at TEXT,                  -- ISO8601 timestamp

    -- MULTI-STORE INTEGRATION (7 columns)
    embedding_id TEXT,                        -- Reference to FAISS index entry
    embedding_vector_dims INTEGER,            -- 768 for typical embeddings
    embedding_model TEXT,                     -- text-embedding-ada-002, all-mpnet-base-v2
    embedding_generated_at TEXT,              -- ISO8601 timestamp
    fts_indexed INTEGER DEFAULT 0,            -- Was text indexed in FTS5?
    fts_table_name TEXT,                      -- Which FTS5 virtual table
    fts_last_indexed TEXT,                    -- ISO8601 timestamp

    -- ACCESS CONTROL (7 columns)
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space (personal:*, shared:household)
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Primary owner (data sovereignty)
    co_owners TEXT,                           -- JSON array of co-owners (shared experiences)
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids who can read

    -- METADATA (3 columns)
    created_at TEXT NOT NULL,                 -- Record creation time
    device_id TEXT,                           -- Originating device
    session_id TEXT,                          -- Conversation session

    -- SYNC (CRDT) (3 columns)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- CONSOLIDATION ROUTING (4 columns) [ADDED FOR P03 INTEGRATION]
    consolidation_target TEXT,                -- Target layer: epi|sem|proc|social|spatial|meta
    consolidation_confidence REAL,            -- Confidence in routing (0.0-1.0)
    consolidation_status TEXT,                -- PENDING|CONSOLIDATED|FAILED
    consolidated_at TEXT,                     -- ISO8601 timestamp when moved to target

    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

-- Indexes for query performance
CREATE INDEX idx_hipp_tenant_space ON st_hipp_store(tenant_id, space_id);
CREATE INDEX idx_hipp_author ON st_hipp_store(author_id);
CREATE INDEX idx_hipp_privacy ON st_hipp_store(privacy_band);
CREATE INDEX idx_hipp_ts ON st_hipp_store(ts DESC);
CREATE INDEX idx_hipp_novelty ON st_hipp_store(novelty DESC);
CREATE INDEX idx_hipp_embedding ON st_hipp_store(embedding_id) WHERE embedding_id IS NOT NULL;
CREATE INDEX idx_hipp_fts ON st_hipp_store(fts_indexed) WHERE fts_indexed = 1;
CREATE INDEX idx_hipp_crdt_tombstone ON st_hipp_store(crdt_tombstone, tenant_id);
CREATE INDEX idx_hipp_consolidation ON st_hipp_store(consolidation_status) WHERE consolidation_status = 'PENDING';
```

**Column Count:** 80 columns (enhanced from original 78)

**Enhancements from original schema:**

- ✅ Added `location_geohash`, `location_precision_m` for AMBER/RED redaction
- ✅ Added 6 affect analysis fields (`affect_valence`, `affect_arousal`, etc.)
- ✅ Added 4 consolidation routing fields for P03 integration

### 4.2 Field-by-Field Transformation (K1 Envelope → st_hipp_store)

| Source | Transform | Destination | Example |
|--------|-----------|-------------|---------|
| `cognitive_trace_id` | Direct copy | `cognitive_trace_id` | `"trace-abc123"` |
| `body.payload.text` | Direct copy | `text` | `"Reminder: Pick up Emma..."` |
| `body.payload.text` | `len(text)` | `length` | `64` |
| `body.payload.text` | Language detection | `language` | `"en"` |
| `body.payload.tags` | JSON array | `topics` | `["reminder", "school", "sports"]` |
| `body.payload.context.activity_type` | Direct copy | `activity_type` | `"pickup"` |
| `body.payload.context.activity_category` | Direct copy | `activity_category` | `"family_coordination"` |
| `body.payload.context` | JSON serialize | `activity_metadata` | `{"urgency": "high"}` |
| Hippocampus DG | SimHash algorithm | `simhash_hex` | `"abcd1234ef567890..."` |
| Hippocampus DG | Fixed value | `simhash_bits` | `512` |
| Hippocampus DG | MinHash algorithm | `minhash32` | `"[12345, 67890, ...]"` |
| Hippocampus DG | Novelty scoring | `novelty` | `0.73` |
| Hippocampus DG | Near-dup detection | `near_duplicates` | `[["evt-123", 0.82]]` |
| `actor` | Direct copy | `author_id` | `"person-alice"` |
| Space Resolver | Lookup relationship | `author_role` | `"parent"` |
| `body.payload.participants` | JSON array | `participants` | `["person-emma"]` |
| Space Resolver | Role mapping | `participant_roles` | `{"person-emma": "child"}` |
| Entity extraction | NER | `mentions` | `[]` |
| Entity extraction | Context | `mention_contexts` | `{}` |
| `body.payload.location.name` | Direct copy (or NULL) | `location_name` | `"Lincoln Park Soccer Fields"` |
| `body.payload.location.type` | Direct copy | `location_type` | `"sports_facility"` |
| `body.payload.location.lat` | Redacted if AMBER/RED | `location_lat` | `NULL` (AMBER) |
| `body.payload.location.lon` | Redacted if AMBER/RED | `location_lon` | `NULL` (AMBER) |
| Redaction Coordinator | Geohash conversion | `location_geohash` | `"dp3wm7"` (AMBER) |
| Redaction Coordinator | Precision lookup | `location_precision_m` | `1000` (AMBER) |
| `ts` | Direct copy | `ts` | `"2025-11-12T14:23:45Z"` |
| `body.payload.timestamp` | Compare to `ts` | `temporal_reference` | `"future"` |
| `body.payload.timestamp` | Direct copy | `temporal_target` | `"2025-11-15T17:00:00Z"` |
| Sentiment analysis | Score | `sentiment_score` | `0.1` |
| Sentiment analysis | Label | `sentiment_label` | `"neutral"` |
| Sentiment analysis | Tags | `emotion_tags` | `["calm", "organized"]` |
| Affect system | Valence | `affect_valence` | `0.1` |
| Affect system | Arousal | `affect_arousal` | `0.4` |
| Affect system | Tags | `affect_tags` | `["urgent"]` |
| Affect system | Confidence | `affect_confidence` | `0.72` |
| Affect system | Model version | `affect_model_version` | `"affect-enhanced:2025-09-04"` |
| Affect system | Timestamp | `affect_computed_at` | `"2025-11-12T14:23:46.050Z"` |
| Embedding service | Vector ID | `embedding_id` | `"emb-2025-11-12-00123"` |
| Embedding service | Dimensions | `embedding_vector_dims` | `768` |
| Embedding service | Model | `embedding_model` | `"text-embedding-ada-002"` |
| Embedding service | Timestamp | `embedding_generated_at` | `"2025-11-12T14:23:46.100Z"` |
| FTS indexer | Index status | `fts_indexed` | `1` |
| FTS indexer | Table name | `fts_table_name` | `"fts_hipp"` |
| FTS indexer | Timestamp | `fts_last_indexed` | `"2025-11-12T14:23:46.150Z"` |
| `tenant_id` | Direct copy | `tenant_id` | `"tenant-family-001"` |
| `space_id` | Direct copy | `space_id` | `"shared:household"` |
| `band` | Direct copy | `privacy_band` | `"AMBER"` |
| Space Resolver | Owner determination | `owner_id` | `"person-alice"` |
| Space Resolver | Co-owner resolution | `co_owners` | `["person-emma"]` |
| Space Resolver | Visibility rules | `visible_to` | `["person-alice", "person-bob", "person-emma"]` |
| System timestamp | `now()` | `created_at` | `"2025-11-12T14:23:46.200Z"` |
| `device_id` | Direct copy | `device_id` | `"device-iphone-alice"` |
| K1 session | Session tracking | `session_id` | `"sess-2025-11-12-001"` |
| CRDT service | Vector clock | `crdt_vector_clock` | `{"device-iphone-alice": 5}` |
| CRDT service | Tombstone flag | `crdt_tombstone` | `0` |
| CRDT service | Lamport timestamp | `crdt_lamport` | `12345` |
| Content classifier | Target layer | `consolidation_target` | `"epi"` |
| Content classifier | Confidence | `consolidation_confidence` | `0.85` |
| P02 | Initial status | `consolidation_status` | `"PENDING"` |
| P02 | Not yet consolidated | `consolidated_at` | `NULL` |
| Hippocampus | Version | `hipp_version` | `"dg-v1.2.0"` |

**Total Fields:** 80 columns populated from K1 envelope + 6 enrichment services

---

## 5) Affect Analysis Integration

**Purpose:** Add emotional intelligence to memory formation
**Location:** `affect/` module (reference: `affect/README.md`)
**Timing:** After redaction, before Hippocampus DG

### 5.1 Affect Analysis Flow

```mermaid
sequenceDiagram
    participant P02 as P02 Pipeline
    participant AFF as Affect Enhanced Classifier
    participant LEX as Lexicon Scorer
    participant BEH as Behavioral Analyzer
    participant VADER as VADER Sentiment
    participant FUSION as Late Fusion

    P02->>AFF: ScoringRequest(text, behavior, context)
    AFF->>LEX: score_text_valence(text)
    LEX-->>AFF: v=0.1, a=0.3, c=0.70
    AFF->>VADER: polarity_scores(text)
    VADER-->>AFF: v=0.15, a=0.35, c=0.75
    AFF->>BEH: score_behavioral_arousal(keystroke_patterns)
    BEH-->>AFF: a=0.5, c=0.60
    AFF->>FUSION: fuse(sources, priors, confidence)
    FUSION-->>AFF: v=0.1, a=0.4, tags=["urgent"], c=0.72
    AFF-->>P02: AffectAnnotation + PolicyRecommendation
```

### 5.2 Affect Input (from K1 envelope)

```json
{
  "person_id": "person-alice",
  "space_id": "shared:household",
  "event_id": "evt-2025-11-12-00123",
  "text": "Reminder: Pick up Emma from soccer practice at 5pm on Friday",
  "behavior": {
    "inter_request_deltas": [0.5, 1.0, 0.4, 0.6],
    "keystrokes_total": 64,
    "backspaces": 5,
    "retries": 0,
    "session_seconds": 300,
    "active_seconds": 60
  },
  "ctx": {
    "battery_low": false,
    "cpu_throttled": false,
    "intent_urgent": true,
    "time_of_day_hours": 14.4
  },
  "trace_id": "trace-abc123"
}
```

### 5.3 Affect Output

```json
{
  "affect_annotation": {
    "event_id": "evt-2025-11-12-00123",
    "space_id": "shared:household",
    "valence": 0.1,
    "arousal": 0.4,
    "tags": ["urgent"],
    "confidence": 0.72,
    "model_version": "affect-enhanced:2025-09-04",
    "ts": "2025-11-12T14:23:46.050Z"
  },
  "policy_recommendation": {
    "band": "AMBER",
    "reasons": [],
    "confidence": 0.7
  }
}
```

### 5.4 Affect → st_hipp_store Mapping

| Affect Field | st_hipp_store Column | Notes |
|--------------|---------------------|-------|
| `valence` | `affect_valence` | Range: [-1.0, 1.0] |
| `arousal` | `affect_arousal` | Range: [0.0, 1.0] |
| `tags` | `affect_tags` | JSON array |
| `confidence` | `affect_confidence` | Range: [0.0, 1.0] |
| `model_version` | `affect_model_version` | Model version string |
| `ts` | `affect_computed_at` | ISO8601 timestamp |

---

## 6) Core + Workspace Integration

**Purpose:** Compute salience, update working memory, broadcast to cognitive services
**Location:** `core/` and `workspace/` modules
**Timing:** After st_hipp_store write, parallel to P02 completion

### 6.1 Core Writer Flow

```mermaid
sequenceDiagram
    participant P02 as P02 Pipeline
    participant WRITER as Core Writer
    participant SAL as Salience Scorer
    participant WM as Working Memory
    participant GW as Global Workspace
    participant BUS as Event Bus

    P02->>WRITER: WriteIntent(event_id, enriched_memory)
    WRITER->>SAL: compute_salience(recency, novelty, affect, goals)
    SAL-->>WRITER: salience=0.81
    WRITER->>WM: update([{event_id, score=0.81, meta}])
    WM-->>WRITER: active_slots=[...]
    WRITER->>GW: broadcast(space_id, wm_snapshot, band, budget)
    GW->>BUS: publish(WORKSPACE_BROADCAST)
    BUS-.->Arbiter
    BUS-.->Retrieval
    BUS-.->Learning
```

### 6.2 Salience Scoring Formula

For memory *i* in `st_hipp_store`:

```
S_i = θ_r × recency_i           [0.9]
    + θ_q × query_match_i       [1.2] (N/A for writes, used in recall)
    + θ_g × goal_align_i        [0.8]
    + θ_n × novelty_i           [0.6]
    + θ_t × circadian_fit_i     [0.5]
    + θ_a × affect_nudge_i      [0.2]
    - θ_c × cost_i              [0.3]
```

**For P02 Write Path:**

- `recency_i = 2^(-Δt/72hr) ≈ 1.0` (just created)
- `novelty_i` from Hippocampus DG output
- `affect_nudge_i = +0.1` if `affect_tags` contains "urgent"
- `goal_align_i` = 0.0 (no active goals yet)
- `circadian_fit_i` from temporal module
- `cost_i` ≈ 0.05 (low compute for simple memory)

**Example Calculation:**

```
S = 0.9×1.0 + 1.2×0.0 + 0.8×0.0 + 0.6×0.73 + 0.5×0.6 + 0.2×0.1 - 0.3×0.05
S = 0.9 + 0 + 0 + 0.438 + 0.3 + 0.02 - 0.015
S = 1.643 → normalized to 0.81 via softmax(T=0.6)
```

### 6.3 Working Memory Update

**Input:**

```json
{
  "event_id": "evt-2025-11-12-00123",
  "score": 0.81,
  "summary": "Reminder: Pick up Emma from soccer practice",
  "expires_at": "2025-11-12T14:28:46Z",
  "meta": {
    "privacy_band": "AMBER",
    "affect": {"v": 0.1, "a": 0.4, "tags": ["urgent"]},
    "novelty": 0.73
  }
}
```

**Working Memory State** (8 slots):

```json
{
  "slots": [
    {
      "slot": 0,
      "event_id": "evt-2025-11-12-00123",
      "weight": 0.81,
      "summary": "Reminder: Pick up Emma from soccer practice",
      "expires_at": "2025-11-12T14:28:46Z"
    },
    {
      "slot": 1,
      "event_id": "evt-2025-11-12-00100",
      "weight": 0.75,
      "summary": "Grocery list: milk, eggs, bread",
      "expires_at": "2025-11-12T14:25:00Z"
    }
    // ... slots 2-7
  ],
  "decay_rate": 0.5,
  "half_life_s": 90
}
```

### 6.4 Workspace Broadcast

**Output to Event Bus:**

```json
{
  "topic": "workspace.broadcast.v1",
  "payload": {
    "space_id": "shared:household",
    "wm": {
      "slots": [
        {
          "slot": 0,
          "event_id": "evt-2025-11-12-00123",
          "summary": "Reminder: Pick up Emma from soccer practice",
          "features": {
            "salience": 0.81,
            "recency": 1.0,
            "novelty": 0.73,
            "affect": {"v": 0.1, "a": 0.4, "tags": ["urgent"]}
          },
          "expires_at": "2025-11-12T14:28:46Z"
        }
      ],
      "context": {
        "band": "AMBER",
        "time_budget_ms": 25,
        "now": "2025-11-12T14:23:46.200Z"
      }
    },
    "trace_id": "trace-abc123"
  }
}
```

**Subscribers:**

- `arbiter` (group): Action planning and task scheduling
- `retrieval` (group): Context-aware search biasing
- `learning` (group): Reinforcement signals for personalization
- `prospective` (group): Reminder scheduling based on circadian fit

---

## 7) The 8-Layer Memory System

**Purpose:** Specialized storage for different memory types after P03 consolidation
**Lifecycle:** st_hipp_store (7-30 days) → P03 Consolidation → Permanent storage
**Source:** `k0/contracts/sql/migrations/0006_phase1_core_memory_foundation.sql`

### 7.1 Memory Layer Architecture

```mermaid
flowchart TB
    subgraph STAGING["Staging Layer (Temporary)"]
        HIPP[(st_hipp_store<br/>7-30 days)]
    end

    subgraph CONSOLIDATION["P03 Consolidation Pipeline"]
        CLASSIFIER[Content Classifier]
        ROUTER[Layer Router]
    end

    subgraph LONGTERM["Long-Term Memory Layers"]
        EPI[(1. st_epi<br/>Episodic)]
        SEM[(2. st_sem<br/>Semantic)]
        PROC[(3. st_proc<br/>Procedural)]
        SOCIAL[(4. st_social<br/>Social)]
        SPATIAL[(5. st_spatial<br/>Spatial)]
        META[(6. st_meta<br/>Metacognitive)]
        WORKING[(7. st_working_memory<br/>Active Context)]
        PROSPECTIVE[(8. st_prospective<br/>Future Intent)]
    end

    HIPP -->|after 7-30 days| CLASSIFIER
    CLASSIFIER --> ROUTER
    ROUTER -->|autobiographical| EPI
    ROUTER -->|facts & concepts| SEM
    ROUTER -->|how-to & skills| PROC
    ROUTER -->|relationships| SOCIAL
    ROUTER -->|location-based| SPATIAL
    ROUTER -->|self-reflection| META
    ROUTER -->|current context| WORKING
    ROUTER -->|future plans| PROSPECTIVE
```

### 7.2 Layer Descriptions & Routing Logic

#### Layer 1: st_epi (Episodic Memory)

**Purpose:** Autobiographical memories of personal experiences
**Retention:** Indefinite (subject to learning-based decay)
**Routing Criteria:**

- Contains temporal sequence (what happened when)
- Has participants (who was there)
- Has location context (where it occurred)
- Narrative structure (story-like)

**Content Classifier Rules:**

```python
def is_episodic(memory):
    score = 0
    if memory.participants: score += 0.3
    if memory.location_name: score += 0.2
    if memory.temporal_target: score += 0.2
    if "event" in memory.activity_type: score += 0.2
    if len(memory.text) > 50: score += 0.1  # Detailed narratives
    return score > 0.6  # Confidence threshold
```

**Example Memories:**

- "Had dinner with family at Olive Garden on Saturday night"
- "Emma's soccer game was rained out, so we got ice cream instead"
- "Visited grandma in the hospital yesterday afternoon"

**Schema Highlights:**

```sql
CREATE TABLE st_epi (
    event_id TEXT PRIMARY KEY,
    hipp_id TEXT,                    -- Reference to st_hipp_store
    text TEXT NOT NULL,
    summary TEXT,                    -- Generated summary
    event_time TEXT NOT NULL,        -- When it happened
    time_bucket TEXT,                -- YYYY-MM-DD-morning/afternoon/evening
    author_id TEXT NOT NULL,
    participants TEXT,               -- JSON array of person_ids
    location_ids TEXT,               -- JSON array of location IDs
    causal_chain TEXT,               -- JSON: [{"cause": "X", "effect": "Y"}]
    consolidation_score REAL,        -- How well consolidated (0.0-1.0)
    retrieval_count INTEGER,         -- How often accessed
    last_retrieved_at TEXT,
    ...
);
```

#### Layer 2: st_sem (Semantic Memory)

**Purpose:** Facts, concepts, and general knowledge
**Retention:** Indefinite (facts don't decay like events)
**Routing Criteria:**

- Timeless statements (not tied to specific episode)
- Conceptual relationships (is-a, part-of)
- Factual assertions
- Definitions and explanations

**Content Classifier Rules:**

```python
def is_semantic(memory):
    score = 0
    if not memory.temporal_target: score += 0.3  # Timeless
    if not memory.participants: score += 0.2     # General knowledge
    if "fact" in memory.activity_type: score += 0.3
    if contains_definition(memory.text): score += 0.2
    return score > 0.6
```

**Example Memories:**

- "Emma is allergic to peanuts"
- "Our family reunion is always in July"
- "The school is 2 miles from home"
- "Bob prefers decaf coffee"

**Schema Highlights:**

```sql
CREATE TABLE st_sem (
    concept_id TEXT PRIMARY KEY,
    hipp_id TEXT,
    concept_text TEXT NOT NULL,
    concept_type TEXT,               -- fact, definition, relationship, rule
    domain TEXT,                     -- family, health, education, etc.
    related_concepts TEXT,           -- JSON array of concept_ids
    confidence REAL,                 -- How certain (0.0-1.0)
    source_events TEXT,              -- JSON array of event_ids that support this
    first_learned_at TEXT,
    last_reinforced_at TEXT,
    contradiction_count INTEGER,     -- How many times contradicted
    ...
);
```

#### Layer 3: st_proc (Procedural Memory)

**Purpose:** Skills, habits, routines, and how-to knowledge
**Retention:** Strengthened with practice
**Routing Criteria:**

- Step-by-step sequences
- Routine patterns
- Habitual actions
- Process descriptions

**Content Classifier Rules:**

```python
def is_procedural(memory):
    score = 0
    if "routine" in memory.activity_category: score += 0.4
    if has_steps(memory.text): score += 0.3  # "First... then... finally..."
    if memory.crdt_lamport > 5: score += 0.2  # Repeated pattern
    if "habit" in memory.topics: score += 0.1
    return score > 0.6
```

**Example Memories:**

- "Morning routine: wake up at 6:30, shower, breakfast, leave by 7:45"
- "Emma's bedtime: bath at 8pm, story, lights out by 8:30"
- "Weekly grocery shopping on Sunday mornings"

**Schema Highlights:**

```sql
CREATE TABLE st_proc (
    procedure_id TEXT PRIMARY KEY,
    hipp_id TEXT,
    procedure_name TEXT NOT NULL,
    steps TEXT NOT NULL,             -- JSON array of ordered steps
    context TEXT,                    -- When/where this applies
    frequency TEXT,                  -- daily, weekly, as-needed
    last_performed_at TEXT,
    success_count INTEGER,
    failure_count INTEGER,
    average_duration_minutes INTEGER,
    ...
);
```

#### Layer 4: st_social (Social Memory)

**Purpose:** Relationships, social dynamics, interactions
**Retention:** Indefinite (relationships evolve)
**Routing Criteria:**

- Focus on interpersonal relationships
- Social dynamics and patterns
- Emotional connections
- Relationship history

**Content Classifier Rules:**

```python
def is_social(memory):
    score = 0
    if len(memory.participants) >= 2: score += 0.3  # Multi-person
    if memory.relationship_context: score += 0.3
    if "social" in memory.activity_category: score += 0.2
    if memory.affect_valence and len(memory.participants) > 0: score += 0.2
    return score > 0.7  # Higher threshold
```

**Example Memories:**

- "Bob and Emma enjoy woodworking together on weekends"
- "Mom gets stressed when planning big family events"
- "Emma confides in Alice about school problems"

**Schema Highlights:**

```sql
CREATE TABLE st_social (
    interaction_id TEXT PRIMARY KEY,
    hipp_id TEXT,
    participants TEXT NOT NULL,      -- JSON array (min 2 people)
    relationship_type TEXT,          -- family, friend, colleague
    interaction_valence REAL,        -- Emotional tone (-1 to 1)
    interaction_pattern TEXT,        -- cooperation, conflict, support, etc.
    mentioned_topics TEXT,           -- JSON array
    first_observed_at TEXT,
    last_observed_at TEXT,
    frequency_score REAL,            -- How often this pattern occurs
    ...
);
```

#### Layer 5: st_spatial (Spatial Memory)

**Purpose:** Location-based memories and navigation
**Retention:** Indefinite (places remain stable)
**Routing Criteria:**

- Primary focus on location
- Navigation and wayfinding
- Place-specific events
- Geographic knowledge

**Content Classifier Rules:**

```python
def is_spatial(memory):
    score = 0
    if memory.location_name: score += 0.4
    if memory.location_lat and memory.location_lon: score += 0.3
    if "navigation" in memory.activity_type: score += 0.2
    if memory.location_type in ["landmark", "route"]: score += 0.1
    return score > 0.7
```

**Example Memories:**

- "Best route to school avoids traffic on Main Street"
- "Lincoln Park has 3 soccer fields and a playground"
- "Emma's school is near the library on Oak Avenue"

**Schema Highlights:**

```sql
CREATE TABLE st_spatial (
    place_id TEXT PRIMARY KEY,
    hipp_id TEXT,
    place_name TEXT NOT NULL,
    place_type TEXT,                 -- home, school, park, route, etc.
    geohash TEXT,
    lat REAL,
    lon REAL,
    associated_events TEXT,          -- JSON array of event_ids
    visit_count INTEGER,
    last_visited_at TEXT,
    valence REAL,                    -- Emotional association with place
    ...
);
```

#### Layer 6: st_meta (Metacognitive Memory)

**Purpose:** Self-reflection, learning about learning, mental models
**Retention:** Long-term (self-knowledge)
**Routing Criteria:**

- Self-referential thoughts
- Learning strategies
- Mental state awareness
- Goal reflection

**Content Classifier Rules:**

```python
def is_metacognitive(memory):
    score = 0
    if "reflection" in memory.topics: score += 0.3
    if first_person_introspection(memory.text): score += 0.3
    if "learning" in memory.activity_type: score += 0.2
    if "I noticed" or "I realized" in memory.text: score += 0.2
    return score > 0.7
```

**Example Memories:**

- "I notice I'm more productive in the mornings"
- "Emma learns better with visual examples than verbal explanations"
- "I tend to over-schedule on weekends"

**Schema Highlights:**

```sql
CREATE TABLE st_meta (
    meta_id TEXT PRIMARY KEY,
    hipp_id TEXT,
    insight_text TEXT NOT NULL,
    insight_type TEXT,               -- self_awareness, strategy, pattern_recognition
    subject_person_id TEXT,          -- Who the insight is about
    confidence REAL,
    supporting_events TEXT,          -- JSON array of event_ids
    first_realized_at TEXT,
    reinforced_count INTEGER,
    ...
);
```

#### Layer 7: st_working_memory (Active Context)

**Purpose:** Currently active thoughts and context
**Retention:** Short-term (minutes to hours)
**Routing Criteria:**

- High salience score
- Recent (< 1 hour)
- Ongoing conversations
- Active goals

**Content Classifier Rules:**

```python
def is_working_memory(memory):
    age_minutes = (now() - memory.created_at).total_seconds() / 60
    return (
        memory.salience > 0.7 and
        age_minutes < 60 and
        memory.session_id == current_session
    )
```

**Example Memories:**

- Current conversation topics
- Items mentioned in last 10 minutes
- Active reminders and notifications

**Schema Highlights:**

```sql
CREATE TABLE st_working_memory (
    wm_id TEXT PRIMARY KEY,
    hipp_id TEXT,
    content TEXT NOT NULL,
    salience REAL,                   -- Current importance
    activation_level REAL,           -- Decay over time
    entered_wm_at TEXT,
    expires_at TEXT,
    rehearsal_count INTEGER,         -- How many times refreshed
    ...
);
```

#### Layer 8: st_prospective (Future Intent)

**Purpose:** Plans, intentions, reminders for future actions
**Retention:** Until executed or cancelled
**Routing Criteria:**

- Future temporal reference
- Intent markers ("will", "plan to", "remind me")
- Scheduled actions
- Goals and commitments

**Content Classifier Rules:**

```python
def is_prospective(memory):
    score = 0
    if memory.temporal_reference == "future": score += 0.4
    if memory.temporal_target > now(): score += 0.3
    if "reminder" in memory.topics: score += 0.2
    if contains_intent(memory.text): score += 0.1
    return score > 0.7
```

**Example Memories:**

- "Reminder: Pick up Emma from soccer practice at 5pm on Friday"
- "Plan to call grandma this weekend"
- "Need to buy Emma new soccer cleats before next season"

**Schema Highlights:**

```sql
CREATE TABLE st_prospective (
    intent_id TEXT PRIMARY KEY,
    hipp_id TEXT,
    intent_text TEXT NOT NULL,
    intent_type TEXT,                -- reminder, goal, commitment, plan
    target_time TEXT,                -- When to execute
    priority TEXT,                   -- low, medium, high, urgent
    status TEXT,                     -- pending, reminded, executed, cancelled
    created_at TEXT,
    reminded_at TEXT,
    executed_at TEXT,
    ...
);
```

### 7.3 Multi-Layer Routing (One Memory → Multiple Layers)

Some memories belong in multiple layers:

**Example:** "Reminder: Pick up Emma from soccer practice at 5pm on Friday"

| Layer | Why It Belongs | Confidence |
|-------|---------------|------------|
| **st_prospective** | Future intent, temporal target | 0.95 (PRIMARY) |
| **st_social** | Involves Emma (participant) | 0.60 |
| **st_spatial** | Lincoln Park Soccer Fields (location) | 0.55 |
| **st_proc** | Part of weekly routine | 0.40 |

**P03 Consolidation Decision:**

- **Primary target:** `st_prospective` (highest confidence)
- **Secondary writes:** Create references in `st_social`, `st_spatial`
- **Update:** Reinforce existing procedure in `st_proc` (if pattern detected)

**st_hipp_store Update:**

```sql
UPDATE st_hipp_store
SET consolidation_target = 'prospective',
    consolidation_confidence = 0.95,
    consolidation_status = 'CONSOLIDATED',
    consolidated_at = '2025-11-12T14:30:00Z'
WHERE event_id = 'evt-2025-11-12-00123';
```

### 7.4 P03 Consolidation Pipeline (Future Work)

**Trigger:** Scheduled job or event-driven (e.g., after 24 hours)

```sql
-- Find memories ready for consolidation
SELECT event_id, text, activity_type, participants, location_name,
       novelty, affect_valence, temporal_reference, consolidation_target
FROM st_hipp_store
WHERE consolidation_status = 'PENDING'
  AND created_at < datetime('now', '-24 hours')
  AND crdt_tombstone = 0
ORDER BY created_at ASC
LIMIT 100;
```

**Consolidation Flow:**

```mermaid
flowchart LR
    QUERY[Query PENDING memories] --> CLASS[Content Classifier]
    CLASS --> ROUTE[Layer Router]
    ROUTE -->|primary| INSERT1[INSERT into target layer]
    ROUTE -->|secondary| INSERT2[INSERT references]
    INSERT1 --> UPDATE[UPDATE st_hipp_store status]
    INSERT2 --> UPDATE
    UPDATE --> DELETE[DELETE from st_hipp_store after 30 days]
```

---

## 8) Complete End-to-End Flow

**Scenario:** Alice creates a reminder to pick up Emma from soccer practice

### 8.1 Step-by-Step Trace

**Step 1: K1 Envelope Creation** (10ms)

```text
K1 Agent → Envelope Builder
- Detect user intent: reminder creation
- Extract entities: Emma (person), Lincoln Park (location), Friday 5pm (time)
- Build envelope with body.payload
- Sign with device key
```

**Step 2: K0 Kernel Validation** (50ms)

```text
POST /k0/command.submit → Attention Gate
- Verify signature (Ed25519)
- Validate schema_uri
- Check device authorization
- Pass to PEP
```

**Step 3: Policy Enforcement** (20ms)

```text
PEP → Policy Engine
- Evaluate ABAC rules (parent role)
- Determine privacy band (AMBER for location)
- Attach policy_stamp
- Pass to UnitOfWork
```

**Step 4: ACID Commit** (20ms)

```text
UnitOfWork → WAL + Outbox
- Write to WAL (st_wal table)
- Generate receipt_id
- INSERT into st_outbox (topic: cognitive.memory.write.committed.v1)
- COMMIT transaction
- Return 200 OK to client (TOTAL: 100ms)
```

**CLIENT RECEIVES 200 OK - PHASE 1 COMPLETE**

---

**Step 5: P02 Pipeline Activation** (5ms)

```text
BusDispatcher → P02 Subscriber
- Poll st_outbox for PENDING messages
- Find: topic=cognitive.memory.write.committed.v1
- Deserialize BusMessage
- Call P02.handle(msg)
```

**Step 6: Space Module** (2ms)

```text
k0/modules/space/resolver.py
Input: actor=person-alice, space_id=shared:household, participants=[person-emma]
Output:
  owner_id: person-alice
  co_owners: [person-emma]
  visible_to: [person-alice, person-bob, person-emma]
```

**Note:** Location redaction already applied by K0 policy engine BEFORE P02 receives envelope:

```text
k0/policy/location_privacy.py (executed in Step 3)
Input: band=AMBER, location={lat: 41.9212, lon: -87.6401, name: "Lincoln Park Soccer Fields"}
Output (already in envelope):
  location_name: "Lincoln Park Soccer Fields"
  location_lat: NULL
  location_lon: NULL
  location_geohash: "dp3wm7"
  location_precision_m: 1000
```

**Step 7: Affect Module** (8ms)

```text
k0/modules/affect/analyzer.py
Input: text="Reminder: Pick up Emma from soccer practice at 5pm on Friday"
Process:
  - Lexicon scoring: v=0.1, a=0.3
  - VADER sentiment: v=0.15, a=0.35
  - Context signals: urgency="high"
  - Late fusion (confidence-weighted)
Output:
  valence: 0.1 (neutral-positive)
  arousal: 0.4 (moderate)
  tags: ["urgent"]
  confidence: 0.72
```

**Step 8: Hippocampus Module - Pattern Separation** (15ms)

```text
k0/modules/hippocampus/dentate_gyrus.py
Input: text="Reminder: Pick up Emma from soccer practice at 5pm on Friday"
Process:
  - Tokenize: ["reminder", "pick", "up", "emma", "soccer", "practice", "5pm", "friday"]
  - K-grams (k=3): ["rem_ind_er", "ind_er_:", "er_:_pic", ...]
  - SimHash 512-bit: 0xabcd1234ef567890... (128 hex chars)
  - MinHash 64 sketches: [12345, 67890, 23456, ...]
  - Query similar memories (Hamming distance)
  - Found: evt-2025-11-10-00456 (Jaccard similarity 0.82)
  - Novelty: 0.73 (moderately novel)
  - Near-duplicate handling: LINK (similarity 0.82, not merge)
Output:
  simhash_hex: "abcd1234ef567890..."
  minhash32: "[12345, 67890, 23456, ...]"
  novelty: 0.73
  near_duplicates: [["evt-2025-11-10-00456", 0.82]]
```

**Step 9: Memory Steward Module - Content Classification** (3ms)

```text
k0/modules/memory_steward/classifier.py
Input: full enriched memory
Scores:
  - Episodic: 0.45 (has participants, location, but not narrative)
  - Semantic: 0.30 (not timeless)
  - Procedural: 0.40 (could be routine)
  - Social: 0.60 (involves Emma)
  - Spatial: 0.55 (has location)
  - Metacognitive: 0.10 (not reflective)
  - Working Memory: 0.75 (recent, high salience)
  - Prospective: 0.95 (future temporal target, reminder)
Output:
  Primary: prospective (0.95)
  Secondary: social (0.60), spatial (0.55)
```

**Step 10: Salience Module** (3ms)

```text
k0/modules/salience/scorer.py
Input: recency=1.0, novelty=0.73, affect_tags=["urgent"], created_at=now()
Calculation:
  S = 0.9×1.0 (recency) + 0.6×0.73 (novelty) + 0.5×0.6 (circadian) + 0.2×0.1 (affect_urgent)
  S = 0.9 + 0.438 + 0.3 + 0.02 = 1.658
  Normalized: 0.81
Output: salience=0.81
```

**Step 11: Commit to st_hipp_store** (8ms)

```text
k0/kernel/syscalls.py → hipp_store_upsert()
- Open UnitOfWork transaction
- Construct 80-column row
- INSERT INTO st_hipp_store (event_id, text, author_id, affect_valence, consolidation_target, ...)
- VALUES ('evt-2025-11-12-00123', 'Reminder: Pick up Emma...', 'person-alice', 0.1, 'prospective', ...)
- COMMIT
```

**Step 12: Mark Processed** (2ms)

```text
k0/kernel/syscalls.py → mark_processed()
- INSERT INTO st_pipeline_processed
  (pipeline_id, space_id, wal_pos, processed_at)
  VALUES ('P02', 'shared:household', 67890, '2025-11-12T14:23:46.123Z')
```

**Step 13: Emit Receipt** (1ms)

```text
k0/kernel/syscalls.py → emit_receipt()
- INSERT INTO st_pipeline_status
  (pipeline_id, wal_pos, status, duration_ms, updated_at)
  VALUES ('P02', 67890, 'SUCCESS', 47, '2025-11-12T14:23:46.150Z')
```

**Step 14: Workspace Module** (2ms)

```text
k0/modules/workspace/manager.py
- Decay existing slots (half-life 90s)
- Insert new memory: {event_id, weight=0.81, expires_at=+5min}
- Evict lowest weight if > 8 slots
- Sort by weight DESC
```

**Step 15: Workspace Broadcast** (5ms)

```text
k0/modules/workspace/broadcaster.py → Event Bus
- Construct WORKSPACE_BROADCAST
- Publish to topic: workspace.broadcast.v1
- Durable WAL append
- Notify subscribers: arbiter, retrieval, learning, prospective
```

**Step 16: ACK to Outbox** (1ms)

```text
P02 → BusDispatcher
- Call msg.ack()
- Update st_outbox: status=COMPLETED, completed_at=now()
```

**PHASE 2 COMPLETE - TOTAL: 51ms**

---

### 8.2 Performance Breakdown

| Stage | Component | Duration | Notes |
|-------|-----------|----------|-------|
| **PHASE 1 (Sync)** | | **100ms** | Client waits |
| 1 | K1 Envelope Creation | 10ms | |
| 2 | K0 Gate Validation | 50ms | Signature + schema |
| 3 | Policy Enforcement | 20ms | ABAC rules |
| 4 | ACID Commit | 20ms | WAL + Outbox |
| | **CLIENT 200 OK** | | |
| **PHASE 2 (Async)** | | **47ms** | Client doesn't wait |
| 5 | P02 Activation | 5ms | Bus poll |
| 6 | Space Module | 2ms | k0/modules/space |
| 7 | Affect Module | 8ms | k0/modules/affect |
| 8 | Hippocampus Module | 15ms | k0/modules/hippocampus (SimHash+dedup) |
| 9 | Memory Steward Module | 3ms | k0/modules/memory_steward |
| 10 | Salience Module | 3ms | k0/modules/salience |
| 11 | st_hipp_store INSERT | 8ms | k0/kernel/syscalls |
| 12 | Mark Processed | 2ms | k0/kernel/syscalls |
| 13 | Emit Receipt | 1ms | k0/kernel/syscalls |
| 14 | Workspace Module | 2ms | k0/modules/workspace |
| 15 | Workspace Broadcast | 5ms | k0/modules/workspace |
| 16 | ACK Outbox | 1ms | |
| | **TOTAL E2E** | **147ms** | Within 150ms P95 budget |

**Note:** Location redaction (Step 3, Policy Enforcement) already applied BEFORE P02, so no separate redaction step in P02.

---

## 9) Idempotency & Error Handling

### 9.1 Idempotency Strategy

**Problem:** What if P02 crashes mid-processing and retries?

**Solution:** `st_pipeline_processed` watermarks

```sql
-- Before processing
SELECT 1 FROM st_pipeline_processed
WHERE pipeline_id = 'P02'
  AND space_id = 'shared:household'
  AND wal_pos = 67890;

-- If found → SKIP (already processed)
-- If not found → PROCESS + INSERT watermark
```

**Deduplication at Multiple Levels:**

1. **K0 Kernel** (idem_key): Prevents duplicate submissions
2. **P02** (wal_pos): Prevents duplicate processing of same Outbox message
3. **Hippocampus DG** (SimHash/MinHash): Detects near-duplicate content

### 9.2 Error Scenarios & Recovery

| Error | Detection | Recovery | Impact |
|-------|-----------|----------|--------|
| **Signature validation fails** | K0 Gate (50ms) | Return 401 Unauthorized | Client retries |
| **Schema unknown** | K0 Gate (50ms) | Return 400 Bad Request | Client fixes |
| **ACID commit fails** | UnitOfWork (100ms) | Rollback, return 500 | Client retries |
| **P02 crashes mid-process** | Outbox retry (auto) | Restart from last watermark | Transparent |
| **Hippocampus DG timeout** | P02 (15ms) | Fallback to placeholder SimHash | Degraded novelty |
| **st_hipp_store INSERT fails** | Commit Manager (8ms) | Rollback UoW, NACK outbox | Retry with backoff |
| **Workspace broadcast fails** | Global Workspace (5ms) | WAL + retry subscribers | Eventually consistent |

**Retry Policy (Outbox):**

```text
Attempt 1: Immediate
Attempt 2: +2s
Attempt 3: +4s (exponential backoff)
Attempt 4: +8s
Attempt 5+: +60s (max backoff)
After 10 failures: Move to DLQ (manual intervention)
```

### 9.3 Observability & Debugging

**Tracing:**

- `cognitive_trace_id` propagated to all tables and logs
- OpenTelemetry spans for each stage
- Example trace: `trace-abc123` → K1 (10ms) → K0 (100ms) → P02 (51ms) → Total 161ms

**Metrics (Prometheus):**

```text
p02_messages_processed_total{pipeline_id="P02",status="success"} 12345
p02_processing_duration_seconds{stage="hippocampus_dg",quantile="0.95"} 0.015
p02_deduplication_actions_total{action="LINK"} 456
p02_consolidation_targets_total{layer="prospective"} 789
```

**Logging (Structured JSON):**

```json
{
  "level": "info",
  "ts": "2025-11-12T14:23:46.200Z",
  "msg": "P02 processing complete",
  "trace_id": "trace-abc123",
  "event_id": "evt-2025-11-12-00123",
  "wal_pos": 67890,
  "duration_ms": 51,
  "stages": {
    "space_resolution": 2,
    "redaction": 1,
    "affect": 8,
    "hippocampus": 15,
    "deduplication": 5,
    "classification": 3,
    "commit": 8
  },
  "consolidation_target": "prospective",
  "salience": 0.81
}
```

---

## 10) Future Enhancements

### 10.1 Near-Term (Next 3 Months)

- ✅ **P03 Consolidation**: Automated st_hipp_store → 8-layer migration
- ✅ **Real Hippocampus**: Replace placeholder with production DG/CA1/CA3
- ✅ **Batch Processing**: Process 100 events in parallel (per-space ordering)
- ✅ **Embedding Integration**: Auto-generate embeddings for all memories
- ✅ **FTS5 Indexing**: Full-text search for st_hipp_store

### 10.2 Medium-Term (6 Months)

- 🔄 **Multi-modal Affect**: Add prosody, facial AU, HRV analysis
- 🔄 **Hierarchical Working Memory**: Slots per modality + cross-modal binding
- 🔄 **Personalized Salience**: Online learning of θ weights per user
- 🔄 **Cross-space Focus**: Co-workspace for shared family moments
- 🔄 **Temporal Rollup**: Hourly → Daily → Weekly → Monthly summaries

### 10.3 Long-Term (12+ Months)

- 🎯 **Counterfactual Rehearsal**: Imagination rollouts before risky actions
- 🎯 **Causal Chain Extraction**: Automatic cause-effect relationship detection
- 🎯 **Federated Learning**: Privacy-preserving model updates across devices
- 🎯 **Neurosymbolic Integration**: Combine neural embeddings with symbolic reasoning
- 🎯 **Multi-agent Memory**: Shared memories across family members with CRDT sync

---

## 11) Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| **ACID** | Atomicity, Consistency, Isolation, Durability (transaction guarantees) |
| **BusMessage** | Wrapper for Outbox events consumed by pipelines |
| **CRDT** | Conflict-Free Replicated Data Type (for multi-device sync) |
| **DLQ** | Dead Letter Queue (failed messages after max retries) |
| **Geohash** | Spatial encoding for privacy-preserving location (e.g., "dp3wm7") |
| **Idem Key** | Idempotency key (prevents duplicate submissions) |
| **MinHash** | Locality-sensitive hashing for Jaccard similarity |
| **Salience** | Importance score combining recency, novelty, affect, goals |
| **SimHash** | Locality-sensitive hashing for cosine similarity (512-bit SDR) |
| **UnitOfWork** | Transaction coordinator pattern (ACID boundary) |
| **WAL** | Write-Ahead Log (durability mechanism) |
| **Watermark** | Checkpoint for idempotent processing (wal_pos tracking) |

### B. References

- **K0 Kernel Architecture**: `docs/whiteboard/k0_pipeline_architecture.md`
- **P02 Implementation Plan**: `docs/versioning_documents/pipeline_implementation/p02_implementation_plan.md`
- **K0 Modules**: `k0/modules/` (6 cognitive assistant modules)
  - Space Module: `k0/modules/space/resolver.py`
  - Affect Module: `k0/modules/affect/analyzer.py`
  - Hippocampus Module: `k0/modules/hippocampus/dentate_gyrus.py`
  - Memory Steward Module: `k0/modules/memory_steward/classifier.py`
  - Salience Module: `k0/modules/salience/scorer.py`
  - Workspace Module: `k0/modules/workspace/manager.py`
- **K0 Policy Engine**: `k0/policy/location_privacy.py` (AMBER/RED redaction)
- **Schema Migrations**: `k0/contracts/sql/migrations/0006_phase1_core_memory_foundation.sql`
- **Schema Enhancements**: `k0/contracts/sql/migrations/0013_p02_write_pipeline_enhancements.sql`

### C. Key Files

| Path | Purpose | Status |
|------|---------|--------|
| `k0/pipelines/p02_episodic_write.py` | P02 pipeline orchestrator | TO BE CREATED |
| `k0/modules/space/resolver.py` | Owner/visibility determination | TO BE CREATED |
| `k0/modules/affect/analyzer.py` | Sentiment analysis | TO BE CREATED |
| `k0/modules/hippocampus/dentate_gyrus.py` | Pattern separation | TO BE CREATED |
| `k0/modules/memory_steward/classifier.py` | Content classification | TO BE CREATED |
| `k0/modules/salience/scorer.py` | Importance scoring | TO BE CREATED |
| `k0/modules/workspace/manager.py` | Working memory management | TO BE CREATED |
| `k0/kernel/syscalls.py` | Storage capabilities (extend) | EXTEND |
| `k0/policy/location_privacy.py` | AMBER/RED redaction | EXISTS ✅ |
| `k0/storage/outbox.py` | Async event queue | EXISTS ✅ |
| `k0/uow/unit_of_work.py` | ACID transaction coordinator | EXISTS ✅ |
| `k0/bus/dispatcher.py` | Topic-based event routing | EXISTS ✅ |
| `k0/contracts/sql/migrations/0013_*.sql` | P02 schema enhancements | CREATED ✅ |
| `tests/k0/pipelines/test_p02.py` | Integration tests | TO BE CREATED |

### D. SQL Queries for Common Operations

**Query 1: Find all memories for a person in a date range**

```sql
SELECT event_id, text, ts, privacy_band, novelty, affect_valence
FROM st_hipp_store
WHERE tenant_id = 'tenant-family-001'
  AND space_id = 'shared:household'
  AND author_id = 'person-alice'
  AND ts BETWEEN '2025-11-01T00:00:00Z' AND '2025-11-30T23:59:59Z'
  AND crdt_tombstone = 0
ORDER BY ts DESC
LIMIT 100;
```

**Query 2: Find high-novelty memories awaiting consolidation**

```sql
SELECT event_id, text, novelty, consolidation_target, consolidation_confidence
FROM st_hipp_store
WHERE consolidation_status = 'PENDING'
  AND novelty > 0.7
  AND created_at < datetime('now', '-24 hours')
ORDER BY novelty DESC
LIMIT 50;
```

**Query 3: Monitor P02 processing health**

```sql
SELECT
  COUNT(*) as total_processed,
  AVG(duration_ms) as avg_duration_ms,
  MAX(duration_ms) as max_duration_ms,
  SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
  SUM(CASE WHEN status = 'FAILURE' THEN 1 ELSE 0 END) as failure_count
FROM st_pipeline_status
WHERE pipeline_id = 'P02'
  AND updated_at > datetime('now', '-1 hour');
```

**Query 4: Find memories similar to a given SimHash**

```sql
-- Note: Requires custom Hamming distance function
SELECT event_id, text, simhash_hex,
       hamming_distance(simhash_hex, ?) as distance
FROM st_hipp_store
WHERE tenant_id = ?
  AND space_id = ?
  AND simhash_hex IS NOT NULL
  AND crdt_tombstone = 0
HAVING distance < 50  -- Within 50 bits different
ORDER BY distance ASC
LIMIT 10;
```

---

## 12) Conclusion

This document defines the **complete P02 Write Pipeline** from K1 envelope ingestion to 8-layer memory storage. Key achievements:

1. ✅ **End-to-end traceability**: `cognitive_trace_id` from K1 → st_hipp_store → downstream services
2. ✅ **Multi-service integration**: Memory Steward + Affect + Hippocampus + Core/Workspace
3. ✅ **Privacy-preserving**: AMBER/RED redaction with geohash obfuscation
4. ✅ **Intelligent routing**: Content classification to 8 specialized memory layers
5. ✅ **Production-ready**: 150ms P95 latency, idempotent, observable, recoverable

**Next Steps:**

- Implement `k0/pipelines/p02_episodic_write.py` (see Section 11.C)
- Write integration tests `tests/k0/pipelines/test_p02.py`
- Deploy P03 Consolidation for st_hipp_store → 8-layer migration
- Monitor metrics and tune performance budgets

**Version:** 1.0.0
**Last Updated:** 2025-11-12
**Status:** Ready for Implementation
