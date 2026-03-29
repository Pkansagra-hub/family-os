# GAP-001: Cross-Layer Vector & Text Linking Problem

**Status**: Identified
**Severity**: Critical
**Impact**: Recall accuracy, semantic search fragmentation, memory coherence, **DATA LOSS after 20 days**
**Related Pipelines**: P01 (Recall), P02 (Write), P03 (Consolidation), P08 (Embedding)
**Schema Source**: `k0/db/alembic/versions/0022-0033`
**Decay Engine**: `k0/modules/consolidation/algorithms/decay_engine.py`
**Dossier Reference**: `docs/pipelines/P03_consolidation_dossier_v2.md` §4.4.1.1, Appendix F.2

---

## 1. Problem Statement

The current architecture has **fragmented vector storage** and **text representation gaps** across truth layers.

### CRITICAL: The Decay Time Bomb

**st_hipp_events is the ONLY table with the original `text` field, and it gets TOMBSTONED after 20 days!**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE 20-DAY TEXT LOSS PROBLEM                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Day 1:   st_hipp_events.text = "Had Thai dinner with Mom at Thai Palace"  │
│           st_epi created with source_events_json = ["event_123"]            │
│           st_sem created with pattern_name = "Had Thai dinner..."           │
│                                                                             │
│  Day 7:   st_hipp_events.decay_factor = 0.50 (half-life reached)            │
│           All truth layers still reference event_123                        │
│                                                                             │
│  Day 20:  st_hipp_events.decay_factor < 0.01 → TOMBSTONE → DELETE           │
│           st_epi still has source_events_json = ["event_123"]               │
│           BUT event_123 NO LONGER EXISTS!                                   │
│                                                                             │
│  Result:  ❌ Original text LOST forever                                     │
│           ❌ Cannot regenerate embeddings                                   │
│           ❌ Cannot audit provenance                                        │
│           ❌ Semantic search returns orphaned references                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Decay Rates by Layer (from decay_engine.py)

| Table | λ (Decay Rate) | Half-Life | Archive @ | **Tombstone @** |
|-------|----------------|-----------|-----------|-----------------|
| **st_hipp_events** | **0.100** | **7 days** | 10 days | **20 days** ⚠️ |
| st_prospective | 0.020 | 35 days | 45 days | 90 days |
| st_procedural | 0.010 | 69 days | 90 days | 180 days |
| st_kg_edges | 0.008 | 87 days | 120 days | 240 days |
| st_epi | 0.005 | 139 days | 180 days | 365 days |
| st_sem | 0.003 | 231 days | 300 days | 600 days |
| st_social | 0.002 | 347 days | 450 days | 900 days |
| st_kg_dom | 0.001 | 693 days | 900 days | 1800 days |

**The problem**: Truth layers (st_epi, st_sem, etc.) live for **1-5 years**, but their source text in st_hipp_events is **deleted after 20 days**.

### Pain Point 1: Episodic Memories Store Structured Info, Not Text

```
st_hipp_events (source) → st_epi (truth)
├── text field: "Had dinner with mom at Olive Garden"
└── After consolidation to st_epi:
    ├── source_events_json: ["evt_abc123"]  ← Reference only
    ├── NO text field                        ← Text lost!
    └── participants_json, location, etc.    ← Structured only
```

**Consequence**: Cannot perform text-based semantic search on consolidated episodic memories.

### Pain Point 2: Each Layer Has Isolated Vectors

| Layer | Current Vector Linkage | Problem |
|-------|----------------------|---------|
| `st_hipp_events` | `embedding_id` → `st_vec` (via `event_id` FK) | ✅ Works for raw events |
| `st_epi` | `embedding_id` (optional, aggregate) | ❌ No FK to st_vec, no source linkage |
| `st_sem` | `embedding_id` (optional, aggregate) | ❌ Pattern embedding not linked to sources |
| `st_procedural` | None | ❌ No vector representation |
| `st_social` | None | ❌ No vector representation |
| `st_prospective` | None | ❌ No vector representation |
| `st_kg_dom` | None (entity nodes) | ❌ Entity embeddings not stored |
| `st_kg_edges` | None | ❌ Relationship embeddings not stored |

### Pain Point 3: Vectors Not Cross-Linked

```
Current: Islands of Vectors
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   st_vec        │   │   (Implicit)    │   │   (Missing)     │
│ event_id = X    │   │   episode_vec   │   │   pattern_vec   │
│ embedding_id=A  │   │   NOT LINKED    │   │   NOT LINKED    │
└─────────────────┘   └─────────────────┘   └─────────────────┘
         │                    │                     │
         │                    │                     │
         ▼                    ▼                     ▼
   st_hipp_events        st_epi              st_sem
   (source events)    (episodes)          (patterns)

Desired: Unified Vector Graph
┌─────────────────────────────────────────────────────────────┐
│                      st_vec_unified                         │
│                                                             │
│  source_type   source_id      embedding    cross_refs       │
│  ──────────────────────────────────────────────────────     │
│  EVENT         evt_abc123     [0.1, ...]   []               │
│  EVENT         evt_def456     [0.2, ...]   []               │
│  EPISODE       epi_001        [0.15, ...]  [evt_abc, evt_d] │ ← Aggregated
│  PATTERN       sem_001        [0.3, ...]   [epi_001]        │ ← Derived from
│  ENTITY        ent_mom        [0.4, ...]   [epi_001, sem_1] │ ← Cross-linked
└─────────────────────────────────────────────────────────────┘
```

### Pain Point 4: Schema vs Reality Mismatch

**Critical Finding**: Many schema columns exist but are **NOT POPULATED** by P03 writers.

| Layer | Schema Column | Actually Populated? | Writer Issue |
| ----- | ------------- | ------------------- | ------------ |
| st_epi | `episode_summary` | ⚠️ Partial | Concatenated texts, not proper summary |
| st_epi | `embedding_id` | ❌ NULL | Writer never sets it |
| st_sem | `pattern_name` | ⚠️ Partial | Truncated event text (first 200 chars) |
| st_sem | `pattern_description` | ❌ NULL | Writer never sets it |
| st_sem | `pattern_attributes_json` | ❌ NULL | Writer never sets it |
| st_procedural | `routine_name` | ✅ Yes | Works |
| st_procedural | `embedding_id` | ❌ NO COLUMN | Schema missing |
| st_social | `embedding_id` | ❌ NO COLUMN | Schema missing |
| st_social | text column | ❌ NO COLUMN | Schema missing |
| st_prospective | `intention_description` | ⚠️ Possibly | Not verified |
| st_prospective | `embedding_id` | ❌ NO COLUMN | Schema missing |
| st_kg_dom | `canonical_name` | ✅ Yes | Just entity name |
| st_kg_dom | `embedding_id` | ❌ NULL | Writer never sets it |
| st_kg_edges | `embedding_id` | ❌ NO COLUMN | Schema missing |

---

## 1.1 The Solution: Copy Source Texts Before Decay

Since st_hipp_events decays in 20 days, we MUST copy the source text to truth layers during R7 consolidation.

**Design Decision**: Use **Option C — Copy Source Event Texts** to each truth layer.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SOLUTION: TEXT PRESERVATION DURING R7                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  During P03 R7 (Truth Write), BEFORE st_hipp_events decay:                  │
│                                                                             │
│  1. Fetch all source events: events = fetch(source_events_json)             │
│  2. Extract texts: source_texts = [e.text for e in events]                  │
│  3. Store in truth layer: source_texts_json = json.dumps(source_texts)      │
│  4. Generate embedding text: embedding_text = " | ".join(source_texts)      │
│  5. Create embedding: embedding = ultrabert.encode(embedding_text)          │
│                                                                             │
│  Result: Truth layers are SELF-CONTAINED                                    │
│  - Can search without st_hipp_events                                        │
│  - Can regenerate embeddings after model upgrade                            │
│  - Full provenance preserved                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1.2 Architecture Summary: Inline Vectors + Entity Graph

This document proposes a two-part solution:

1. **Inline Vectors**: Store `embedding_vector BYTEA` directly in each truth layer
2. **Entity Graph**: Use st_kg_dom as the universal cross-layer linking mechanism

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│              RECOMMENDED ARCHITECTURE: INLINE VECTORS + ENTITY GRAPH        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BEFORE (Current)                      AFTER (Proposed)                     │
│  ───────────────────                   ─────────────────────                │
│                                                                             │
│  ┌──────────────┐                      ┌──────────────────────────────┐     │
│  │  st_vec      │                      │  st_epi (self-contained)     │     │
│  │  event_id FK │                      │  ├── source_texts_json       │     │
│  │  (events     │                      │  ├── embedding_text          │     │
│  │   only)      │                      │  ├── embedding_vector BYTEA  │     │
│  └──────┬───────┘                      │  ├── embedding_model         │     │
│         │                              │  └── participants_json ──────┼──┐  │
│         ▼                              └──────────────────────────────┘  │  │
│  ┌──────────────┐                                                        │  │
│  │st_hipp_events│                      ┌──────────────────────────────┐  │  │
│  │  (decays in  │                      │  st_sem (self-contained)     │  │  │
│  │   20 days!)  │                      │  ├── source_texts_json       │  │  │
│  └──────────────┘                      │  ├── embedding_text          │  │  │
│                                        │  ├── embedding_vector BYTEA  │  │  │
│  ┌──────────────┐                      │  └── actor_id ───────────────┼──┤  │
│  │  st_epi      │                      └──────────────────────────────┘  │  │
│  │  (no text!)  │                                                        │  │
│  └──────────────┘                      ┌──────────────────────────────┐  │  │
│                                        │  st_social                   │  │  │
│  ┌──────────────┐                      │  ├── embedding_vector BYTEA  │  │  │
│  │  st_sem      │                      │  └── actor_a_id, actor_b_id ─┼──┤  │
│  │  (no text!)  │                      └──────────────────────────────┘  │  │
│  └──────────────┘                                                        │  │
│                                        ┌──────────────────────────────┐  │  │
│  Problem:                              │  st_kg_dom (Entity Hub)      │◀─┘  │
│  • Vectors only for events             │  ├── entity_id (universal)   │     │
│  • Truth layers orphaned               │  ├── canonical_name          │     │
│  • No cross-layer linking              │  ├── embedding_vector BYTEA  │     │
│                                        │  └── attributes_json         │     │
│                                        └────────────┬─────────────────┘     │
│                                                     │                       │
│                                        ┌────────────▼─────────────────┐     │
│                                        │  st_kg_edges                 │     │
│                                        │  source_entity ↔ target      │     │
│                                        └──────────────────────────────┘     │
│                                                                             │
│  Solution:                                                                  │
│  • Each truth layer owns its vector                                         │
│  • Entity IDs link across layers                                            │
│  • FAISS Union Index for search                                             │
│  • Entity Graph for context expansion                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Query Flow: Vector Search → Entity Expansion → LLM Context

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    P01 RECALL: QUERY FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User: "What did I discuss with Mom about her garden?"                      │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Step 1: EMBED QUERY                                                │   │
│  │  UltraBERT → query_vec [768-dim]                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Step 2: FAISS UNION INDEX SEARCH                                   │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │   │
│  │  │st_epi  │ │st_sem  │ │st_proc │ │st_soc  │ │st_pros │ │st_kg   │  │   │
│  │  │vectors │ │vectors │ │vectors │ │vectors │ │vectors │ │vectors │  │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │   │
│  │                                                                     │   │
│  │  Returns: [(st_epi, ep_123, 0.91), (st_sem, sem_456, 0.87), ...]   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Step 3: EXTRACT ENTITY IDs                                         │   │
│  │                                                                     │   │
│  │  ep_123.participants_json = ["Mom", "User"]                         │   │
│  │  sem_456.actor_id = "Mom"                                           │   │
│  │                                                                     │   │
│  │  → entities = {"Mom", "User"}                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Step 4: ENTITY GRAPH EXPANSION (1-hop)                             │   │
│  │                                                                     │   │
│  │  st_kg_dom: "Mom" → entity details                                  │   │
│  │  st_kg_edges: "Mom" -- FAMILY_OF → "User"                           │   │
│  │               "Mom" -- INTERESTED_IN → "Gardening"                   │   │
│  │                                                                     │   │
│  │  → expanded_entities = {"Mom", "User", "Gardening"}                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Step 5: FETCH RELATED TRUTH RECORDS                                │   │
│  │                                                                     │   │
│  │  episodes = SELECT * FROM st_epi                                    │   │
│  │             WHERE participants_json CONTAINS ANY(expanded_entities) │   │
│  │                                                                     │   │
│  │  patterns = SELECT * FROM st_sem                                    │   │
│  │             WHERE actor_id IN expanded_entities                     │   │
│  │                                                                     │   │
│  │  relationships = SELECT * FROM st_social                            │   │
│  │                  WHERE actor_a_id OR actor_b_id IN expanded_entities│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Step 6: RICH CONTEXT FOR LLM                                       │   │
│  │                                                                     │   │
│  │  {                                                                  │   │
│  │    "direct_matches": [                                              │   │
│  │      {"type": "episode", "text": "Discussed Mom's garden..."}       │   │
│  │    ],                                                               │   │
│  │    "related_episodes": [                                            │   │
│  │      {"text": "Mom mentioned new tomato plants..."}                 │   │
│  │    ],                                                               │   │
│  │    "patterns": [                                                    │   │
│  │      {"name": "Mom's gardening interest", "frequency": "WEEKLY"}    │   │
│  │    ],                                                               │   │
│  │    "relationships": [                                               │   │
│  │      {"type": "FAMILY", "with": "Mom", "closeness": 0.95}           │   │
│  │    ]                                                                │   │
│  │  }                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Current Schema Analysis (from Alembic Migrations)

### 2.1 st_hipp_events (0022) — Source Layer

The raw event store with 80+ columns. **Key embedding-related fields:**

```sql
-- Embeddings & Knowledge Graph (4 columns)
embedding_id TEXT NOT NULL UNIQUE,      -- FK target for st_vec
embedding_status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/IN_PROGRESS/READY/FAILED
entities_json TEXT,                      -- NER output
kg_triples_json TEXT,                    -- KG triples

-- Text Content
text TEXT,                               -- Original event text ✅ HAS TEXT
text_normalized TEXT,                    -- Cleaned version
```

**Embedding Status**: ✅ Has `embedding_id`, `text` for UltraBERT sentence embedding.

---

### 2.2 st_vec (0025) — Vector Storage

```sql
CREATE TABLE st_vec (
  -- Identity
  embedding_id TEXT PRIMARY KEY,

  -- Linkage (ONLY to events!)
  event_id TEXT NOT NULL,                -- FK to st_hipp_events ⚠️ SINGLE SOURCE ONLY

  -- Context
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Vector Data
  vector BLOB NOT NULL,                  -- 768-dim UltraBERT
  vector_dim INTEGER DEFAULT 768,
  model_id TEXT DEFAULT 'ultrabert_v2.1.0',

  -- Status
  status TEXT DEFAULT 'READY',           -- READY/INDEXED/FAILED

  -- FAISS
  faiss_id INTEGER,
  indexed_at BIGINT,

  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id) ON DELETE CASCADE
);
```

**Gap**: Only links to `st_hipp_events`. Cannot store embeddings for other layers.

---

### 2.3 st_epi (0027) — Episodic Memory (33 columns)

```sql
CREATE TABLE st_epi (
  -- Identity
  episode_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Versioning
  version INTEGER DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Episode Content
  episode_summary TEXT,                  -- ⚠️ Only summary, not full text
  episode_type TEXT,

  -- Temporal (7 cols)
  start_time_utc BIGINT NOT NULL,
  end_time_utc BIGINT NOT NULL,
  duration_minutes INTEGER,
  temporal_bucket TEXT,                  -- MORNING, AFTERNOON, etc.
  day_of_week TEXT,
  is_recurring BOOLEAN,
  recurrence_pattern TEXT,

  -- Source Events
  source_events_json TEXT NOT NULL,      -- JSON array of event_ids
  source_event_count INTEGER NOT NULL,

  -- Location
  primary_location TEXT,
  location_type TEXT,

  -- Participants
  participants_json TEXT,
  participant_count INTEGER,

  -- Embeddings
  embedding_id TEXT,                     -- ⚠️ EXISTS but no FK, no text source

  -- Consolidation
  cluster_id TEXT,
  cluster_confidence REAL,
  consolidation_cycle_id TEXT,

  -- Truth Tracking
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at BIGINT,
  decay_factor REAL DEFAULT 1.0,

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE'  -- ACTIVE/ARCHIVED/TOMBSTONE
);
```

**Gaps**:

- ❌ No `text` column — only `episode_summary` (brief)
- ⚠️ Has `embedding_id` but no FK to st_vec
- ❌ No `text_to_embed` field for generating embeddings

---

### 2.4 st_sem (0028) — Semantic Patterns (26 columns)

```sql
CREATE TABLE st_sem (
  -- Identity
  pattern_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT,                         -- Whose pattern (NULL = family)

  -- Versioning
  version INTEGER DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Classification
  pattern_type TEXT NOT NULL,            -- ROUTINE/PREFERENCE/THEME/RELATIONSHIP/GOAL/VALUE
  pattern_subtype TEXT,

  -- Content
  pattern_name TEXT NOT NULL,            -- ✅ Embeddable name
  pattern_description TEXT,              -- ✅ Embeddable description
  pattern_attributes_json TEXT,

  -- Temporal Pattern
  temporal_regularity REAL,
  temporal_pattern_json TEXT,

  -- Source Episodes
  source_episodes_json TEXT NOT NULL,
  source_episode_count INTEGER NOT NULL,

  -- Embeddings
  embedding_id TEXT,                     -- ⚠️ EXISTS but disconnected

  -- Truth Tracking (5 cols)
  -- Lifecycle (1 col)
  -- Timestamps (4 cols)
);
```

**Gaps**:

- ✅ Has `pattern_name` + `pattern_description` — can construct embedding text
- ⚠️ Has `embedding_id` but no FK
- ❌ No dedicated `embedding_text` column

---

### 2.5 st_procedural (0029) — Habits & Routines (27 columns)

```sql
CREATE TABLE st_procedural (
  -- Identity
  routine_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,                -- Who performs this

  -- Versioning (3 cols)

  -- Routine Definition
  routine_name TEXT NOT NULL,            -- ✅ Embeddable
  routine_category TEXT,                 -- MORNING, EXERCISE, etc.

  -- Temporal Pattern
  temporal_anchor TEXT,                  -- "07:30"
  day_pattern TEXT,                      -- WEEKDAYS, WEEKENDS, DAILY
  frequency TEXT,                        -- DAILY, WEEKLY, MONTHLY
  regularity_score REAL,

  -- Action Sequence
  action_sequence_json TEXT,             -- ⚠️ JSON, not plain text
  typical_duration_minutes INTEGER,

  -- Source Episodes
  source_episodes_json TEXT NOT NULL,
  source_episode_count INTEGER NOT NULL,

  -- Truth Tracking (6 cols including streak)
  -- Lifecycle + Timestamps
);
```

**Gaps**:

- ❌ No `embedding_id` column
- ⚠️ Has `routine_name` but `action_sequence_json` is structured, not embeddable
- ❌ No text representation for embedding

---

### 2.6 st_social (0030) — Relationships (27 columns)

```sql
CREATE TABLE st_social (
  -- Identity
  relationship_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Endpoints
  actor_a_id TEXT NOT NULL,              -- First person
  actor_b_id TEXT NOT NULL,              -- Second person

  -- Versioning (3 cols)

  -- Type
  relationship_type TEXT NOT NULL,       -- FAMILY, FRIEND, COLLEAGUE
  relationship_subtype TEXT,             -- SPOUSE, SIBLING, PARENT
  relationship_label TEXT,               -- Custom label

  -- Strength
  interaction_count INTEGER DEFAULT 0,
  avg_sentiment REAL,
  relationship_strength REAL DEFAULT 0.5,
  intimacy_level TEXT,                   -- ACQUAINTANCE → INTIMATE

  -- Temporal
  first_interaction_at BIGINT,
  last_interaction_at BIGINT,
  interaction_frequency TEXT,            -- DAILY, WEEKLY, etc.

  -- Source Episodes
  source_episodes_json TEXT,

  -- Truth Tracking (3 cols)
  -- Lifecycle + Timestamps
);
```

**Gaps**:

- ❌ No `embedding_id` column
- ❌ No text content — only IDs and labels (not sentence-like)
- ⚠️ UltraBERT NOT suitable for relationship labels

---

### 2.7 st_prospective (0031) — Intentions & Goals (23 columns)

```sql
CREATE TABLE st_prospective (
  -- Identity
  intention_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,

  -- Versioning (3 cols)

  -- Type
  intention_type TEXT NOT NULL,          -- GOAL/PLAN/REMINDER/COMMITMENT/WISH

  -- Content
  intention_description TEXT NOT NULL,   -- ✅ Embeddable!
  target_date BIGINT,
  target_context TEXT,                   -- ✅ Trigger context

  -- Status
  status TEXT DEFAULT 'ACTIVE',          -- ACTIVE/COMPLETED/ABANDONED/DEFERRED

  -- Inference Source
  inferred_from_json TEXT,
  inference_confidence REAL,

  -- Truth Tracking (3 cols)
  -- Lifecycle + Timestamps
);
```

**Gaps**:

- ❌ No `embedding_id` column
- ✅ Has `intention_description` + `target_context` — good for embedding

---

### 2.8 st_kg_dom (0032) — KG Entities (23 columns)

```sql
CREATE TABLE st_kg_dom (
  -- Identity
  entity_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Versioning (3 cols)

  -- Entity Type
  entity_type TEXT NOT NULL,             -- PERSON, PLACE, ORG, THING, EVENT
  entity_subtype TEXT,

  -- Names
  canonical_name TEXT NOT NULL,          -- ⚠️ Short label, not sentence
  aliases_json TEXT,                     -- Alternative names

  -- Attributes
  attributes_json TEXT,                  -- Structured data

  -- Embeddings
  embedding_id TEXT,                     -- ⚠️ EXISTS but disconnected

  -- Source Episodes
  source_episodes_json TEXT,
  first_mentioned_event_id TEXT,

  -- Truth Tracking (4 cols)
  -- Lifecycle + Timestamps
);
```

**Gaps**:

- ⚠️ Has `embedding_id` but no FK
- ❌ `canonical_name` is a short label (e.g., "Mom", "Olive_Garden")
- ⚠️ UltraBERT NOT suitable for single-word entity names

---

### 2.9 st_kg_edges (0033) — KG Relationships (22 columns)

```sql
CREATE TABLE st_kg_edges (
  -- Identity
  edge_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Endpoints
  source_entity_id TEXT NOT NULL,        -- FK to st_kg_dom
  target_entity_id TEXT NOT NULL,        -- FK to st_kg_dom

  -- Versioning (3 cols)

  -- Type
  relation_type TEXT NOT NULL,           -- WORKS_AT, LIVES_IN, KNOWS
  relation_subtype TEXT,

  -- Properties
  properties_json TEXT,

  -- Strength
  edge_weight REAL DEFAULT 1.0,
  confidence_score REAL DEFAULT 0.5,

  -- Source Evidence
  source_episodes_json TEXT,
  co_occurrence_count INTEGER DEFAULT 1, -- Hebbian learning

  -- Truth Tracking (3 cols)
  -- Lifecycle + Timestamps

  FOREIGN KEY (source_entity_id) REFERENCES st_kg_dom(entity_id),
  FOREIGN KEY (target_entity_id) REFERENCES st_kg_dom(entity_id)
);
```

**Gaps**:

- ❌ No `embedding_id` column
- ❌ `relation_type` is a label, not a sentence
- ⚠️ Relationship embeddings need graph-aware models (TransE, not UltraBERT)

---

## 3. Embedding Model Analysis

### 3.1 Content Type vs Model Fit

| Layer | Content Type | Example | UltraBERT Fit? | Recommended Model |
|-------|-------------|---------|----------------|-------------------|
| st_hipp_events | **Sentence** | "Had dinner with mom at Olive Garden" | ✅ Perfect | UltraBERT 768-dim |
| st_epi | **Paragraph** | Consolidated episode narrative | ✅ Good | UltraBERT 768-dim |
| st_sem | **Phrase** | "Weekly Thai dinner routine" | ⚠️ Okay | UltraBERT (with description) |
| st_procedural | **Steps/List** | "Make coffee: grind, brew, pour" | ⚠️ Okay | UltraBERT (flatten steps) |
| st_social | **Labels** | "Mom", "SPOUSE" | ❌ Poor | Word2Vec or Description |
| st_prospective | **Sentence** | "Plan to visit mom next Sunday" | ✅ Good | UltraBERT 768-dim |
| st_kg_dom | **Entity Name** | "Olive_Garden_Market_St" | ❌ Poor | Entity Embeddings |
| st_kg_edges | **Relation Type** | "WORKS_AT", "had_dinner_with" | ❌ Poor | TransE/RotatE |

### 3.2 The Core Problem: UltraBERT is Sentence-Level

**UltraBERT** (and sentence-transformers like all-MiniLM-L6-v2) are trained on:

- "The cat sat on the mat" vs "A feline rested on the rug" → High similarity ✅

**But for entity names:**

- "Mom" vs "Mother" → May NOT be similar (short tokens, no context)
- "Olive_Garden_Market_St" vs "Olive Garden on Market Street" → Tokenization issues

### 3.3 Recommended Multi-Model Strategy

```text
┌─────────────────────────────────────────────────────────────────┐
│                    EMBEDDING MODEL STRATEGY                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SENTENCE-LEVEL (UltraBERT 768-dim)                             │
│  ├── st_hipp_events.text                                         │
│  ├── st_epi.consolidated_text (NEW)                              │
│  ├── st_sem.pattern_name + pattern_description                   │
│  ├── st_procedural.routine_name + action_summary (NEW)           │
│  └── st_prospective.intention_description + target_context       │
│                                                                  │
│  ENTITY-LEVEL (Option A: Description → UltraBERT)               │
│  ├── st_kg_dom: Generate entity_description from attributes     │
│  │   "Mom" → "My mother who lives in San Francisco"             │
│  └── st_social: Generate relationship_description                │
│       "relationship with Mom" → "Close family relationship..."   │
│                                                                  │
│  ENTITY-LEVEL (Option B: Dedicated Entity Embeddings)           │
│  ├── st_kg_dom: TransE/RotatE for entity nodes                   │
│  └── st_kg_edges: TransE for relationship triples                │
│       Trained on (subject, predicate, object) structure          │
│                                                                  │
│  GRAPH-AWARE (Future: GraphSAGE/Node2Vec)                       │
│  └── st_kg_*: Learn embeddings from graph structure              │
│       Captures neighborhood information                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 Recommendation: Description-Based Approach (Option A)

For now, use **UltraBERT for everything** by generating descriptions:

| Layer | Generate From | Embedding Text Example |
|-------|--------------|----------------------|
| st_epi | Source events + summary | "Episode: Family dinner at Olive Garden with Mom and Dad on Tuesday evening" |
| st_sem | pattern_name + description | "Routine: Weekly Thai dinner - We go to Thai Palace every Friday night" |
| st_procedural | routine_name + flatten steps | "Habit: Morning coffee - Grind beans, add water, brew for 4 minutes, pour" |
| st_social | actor names + type + context | "Relationship: Mom (FAMILY/PARENT) - Close relationship, weekly calls" |
| st_prospective | intention + context | "Goal: Visit mom next Sunday for Mother's Day" |
| st_kg_dom | name + type + attributes | "Entity: Olive Garden (PLACE/RESTAURANT) - Italian restaurant on Market St" |
| st_kg_edges | subject + relation + object | "Relationship: Mom WORKS_AT Hospital - She is a nurse there" |

**Pros:**

- Single model (UltraBERT) for all embeddings
- Consistent 768-dim vectors
- Semantic search works across all layers

**Cons:**

- Generated descriptions add storage overhead
- May lose structural information for KG
- Graph-specific queries may be less accurate

---

## 4. Non-LLM Summary Generation Strategies

Since we need to generate embeddable text for each truth layer WITHOUT using LLMs (to avoid latency and cost), we use algorithmic approaches.

### 4.1 Strategy Overview

| Strategy | Best For | Complexity | Quality |
| -------- | -------- | ---------- | ------- |
| **Template-Based** | Structured data (patterns, routines, relationships) | Low | Good |
| **Concatenation + Dedup** | Episodes with few events | Low | Moderate |
| **TextRank Extractive** | Episodes with many events | Medium | Good |
| **Keyword + Template** | Mixed content | Medium | Good |
| **Narrative Arc (First/Peak/Last)** | Long episodes | Low | Good |
| **Compression (Prefix Removal)** | Repetitive routines | Low | Moderate |

### 4.2 Template-Based Generation

Use structured templates that fill placeholders from existing columns:

```python
# k0/modules/consolidation/algorithms/summary_generator.py

class TemplateSummaryGenerator:
    """Template-based summary generation without LLM."""

    # ─────────────────────────────────────────────────────────────────────────
    # st_epi: Episode Summary
    # ─────────────────────────────────────────────────────────────────────────
    def generate_episode_summary(self, episode: dict) -> str:
        """Generate summary from structured fields."""
        parts = []

        # Time anchor
        time_str = self._format_time_bucket(
            episode.get('temporal_bucket'),
            episode.get('day_of_week')
        )
        if time_str:
            parts.append(time_str)  # "Tuesday morning"

        # Location
        if episode.get('primary_location'):
            parts.append(f"at {episode['primary_location']}")

        # Participants
        if episode.get('participants_json'):
            names = self._get_participant_names(episode['participants_json'])
            if names:
                parts.append(f"with {', '.join(names)}")

        # Episode type
        if episode.get('episode_type') == 'ROUTINE':
            parts.append("(recurring)")
        elif episode.get('episode_type') == 'MILESTONE':
            parts.append("(milestone)")

        # Duration
        duration = episode.get('duration_minutes')
        if duration and duration > 30:
            parts.append(f"lasting {duration} minutes")

        return " ".join(parts)
        # → "Tuesday morning at Thai Palace with Mom (recurring) lasting 90 minutes"

    # ─────────────────────────────────────────────────────────────────────────
    # st_sem: Pattern Description
    # ─────────────────────────────────────────────────────────────────────────
    def generate_pattern_description(self, pattern: dict) -> str:
        """Generate description from pattern structure."""
        pattern_type = pattern.get('pattern_type', 'UNKNOWN')
        pattern_name = pattern.get('pattern_name', 'Unknown pattern')
        attrs = json.loads(pattern.get('pattern_attributes_json') or '{}')

        if pattern_type == 'PREFERENCE':
            polarity = "likes" if attrs.get('polarity') == 'positive' else "dislikes"
            actor = pattern.get('actor_name', 'User')
            value = attrs.get('value', 'unknown')
            domain = attrs.get('domain', 'general')
            return f"{actor} {polarity} {value} ({domain})"
            # → "Mom likes Thai food (cuisine)"

        elif pattern_type == 'ROUTINE':
            temporal = pattern.get('temporal_pattern_json', '')
            temporal_str = self._format_temporal(temporal)
            return f"{pattern_name} happens {temporal_str}"
            # → "Thai dinner happens every Friday evening"

        elif pattern_type == 'THEME':
            count = pattern.get('observation_count', 1)
            return f"Theme: {pattern_name} (observed {count} times)"

        else:
            return f"{pattern_type}: {pattern_name}"

    # ─────────────────────────────────────────────────────────────────────────
    # st_procedural: Routine Description
    # ─────────────────────────────────────────────────────────────────────────
    def generate_routine_description(self, routine: dict) -> str:
        """Generate description from action sequence."""
        routine_name = routine.get('routine_name', 'Routine')
        steps = json.loads(routine.get('action_sequence_json') or '[]')

        if not steps:
            return routine_name

        # Extract action verbs from first 3 steps
        actions = []
        for step in steps[:3]:
            action = step.get('action') or step.get('verb') or step.get('name', '?')
            actions.append(action)

        if len(steps) > 3:
            return f"{routine_name}: {', '.join(actions)}, and {len(steps)-3} more steps"
        else:
            return f"{routine_name}: {', '.join(actions)}"
        # → "Morning coffee routine: wake up, grind beans, brew espresso"

    # ─────────────────────────────────────────────────────────────────────────
    # st_social: Relationship Description
    # ─────────────────────────────────────────────────────────────────────────
    def generate_relationship_description(self, rel: dict) -> str:
        """Generate description from relationship structure."""
        actor_a = self._get_actor_name(rel.get('actor_a_id'))
        actor_b = self._get_actor_name(rel.get('actor_b_id'))

        rel_type = (rel.get('relationship_type') or 'RELATED').lower().replace('_', ' ')

        parts = [f"{actor_a} is {rel_type} with {actor_b}"]

        if rel.get('relationship_label'):
            parts.append(f"({rel['relationship_label']})")

        strength = rel.get('strength_score', 0)
        if strength > 0.7:
            parts.append("- close relationship")
        elif strength < 0.3:
            parts.append("- distant relationship")

        return " ".join(parts)
        # → "User is family with Sarah (Mom) - close relationship"

    # ─────────────────────────────────────────────────────────────────────────
    # st_prospective: Intention Description
    # ─────────────────────────────────────────────────────────────────────────
    def generate_intention_description(self, intention: dict) -> str:
        """Generate description from intention fields."""
        intent_type = intention.get('intention_type', 'GOAL')
        description = intention.get('intention_description', '')
        target_context = intention.get('target_context', '')

        parts = [f"{intent_type}: {description}"]

        if target_context:
            parts.append(f"(triggered by: {target_context})")

        target_date = intention.get('target_date')
        if target_date:
            date_str = self._format_date(target_date)
            parts.append(f"by {date_str}")

        return " ".join(parts)
        # → "GOAL: Visit mom for Mother's Day (triggered by: calendar reminder) by 2025-05-11"

    # ─────────────────────────────────────────────────────────────────────────
    # st_kg_dom: Entity Description
    # ─────────────────────────────────────────────────────────────────────────
    def generate_entity_description(self, entity: dict) -> str:
        """Generate description from entity attributes."""
        parts = [entity.get('canonical_name', 'Unknown')]

        # Entity type
        entity_type = entity.get('entity_type')
        if entity_type:
            parts.append(f"({entity_type.lower()})")

        # Aliases
        aliases = json.loads(entity.get('aliases_json') or '[]')
        if aliases:
            parts.append(f"also known as {', '.join(aliases[:2])}")

        # Key properties
        props = json.loads(entity.get('properties_json') or '{}')
        if props:
            key_props = list(props.items())[:2]
            prop_strs = [f"{k}: {v}" for k, v in key_props]
            parts.append(f"[{', '.join(prop_strs)}]")

        return " ".join(parts)
        # → "Thai Palace (restaurant) also known as TP [cuisine: Thai, price: $$]"

    # ─────────────────────────────────────────────────────────────────────────
    # st_kg_edges: Edge Description
    # ─────────────────────────────────────────────────────────────────────────
    def generate_edge_description(self, edge: dict) -> str:
        """Generate description from edge structure."""
        subj = self._get_entity_name(edge.get('subject_id'))
        obj = self._get_entity_name(edge.get('object_id'))
        rel = (edge.get('relation_type') or 'RELATED').lower().replace('_', ' ')

        desc = f"{subj} {rel} {obj}"

        count = edge.get('observation_count', 1)
        if count > 1:
            desc += f" (observed {count} times)"

        confidence = edge.get('confidence', 1.0)
        if confidence < 0.7:
            desc += " [uncertain]"

        return desc
        # → "Mom dines at Thai Palace (observed 5 times)"
```

### 4.3 Concatenation with Smart Deduplication

For episodes with source texts, concatenate with dedup:

```python
def smart_concatenate(texts: List[str], max_length: int = 1000) -> str:
    """Concatenate texts with deduplication and length limits."""
    if not texts:
        return ""

    # 1. Deduplicate near-identical texts (using SimHash or Jaccard)
    unique_texts = deduplicate_texts(texts, similarity_threshold=0.85)

    # 2. Sort by information density (longer = more info, but diminishing)
    unique_texts.sort(key=lambda t: min(len(t), 200), reverse=True)

    # 3. Take most informative texts up to max_length
    result = []
    current_length = 0

    for text in unique_texts:
        if current_length + len(text) + 3 > max_length:
            # Truncate last text if needed
            remaining = max_length - current_length - 3
            if remaining > 50:
                result.append(text[:remaining] + "...")
            break
        result.append(text)
        current_length += len(text) + 3  # " | " separator

    return " | ".join(result)
```

### 4.4 TextRank Extractive Summarization

For episodes with many source events, extract key sentences:

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def textrank_summarize(texts: List[str], num_sentences: int = 3) -> str:
    """
    TextRank-based extractive summarization.

    Selects most representative sentences without LLM.
    Based on: Mihalcea & Tarau (2004) - TextRank
    """
    if len(texts) <= num_sentences:
        return " ".join(texts)

    # 1. Vectorize all sentences with TF-IDF
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(texts)

    # 2. Build similarity graph
    similarity_matrix = cosine_similarity(tfidf_matrix)

    # 3. PageRank-style scoring
    scores = np.ones(len(texts)) / len(texts)
    damping = 0.85

    for _ in range(10):  # 10 iterations usually enough
        new_scores = (1 - damping) + damping * similarity_matrix.T.dot(scores)
        new_scores /= new_scores.sum()
        if np.allclose(scores, new_scores):
            break
        scores = new_scores

    # 4. Select top sentences (preserve temporal order)
    top_indices = np.argsort(scores)[-num_sentences:]
    top_indices = sorted(top_indices)  # Preserve original order

    return " ".join([texts[i] for i in top_indices])
```

### 4.5 Narrative Arc: First + Peak + Last

Based on Peak-End Rule (Kahneman) — people remember peaks and endings:

```python
def narrative_arc_summary(events: List[dict]) -> str:
    """
    Extract first, peak (most emotional), and last events.

    Based on: Peak-End Rule (Kahneman) - people remember peaks and endings.
    """
    if len(events) <= 3:
        return " | ".join([e['text'] for e in events])

    # First event (context setting)
    first = events[0]['text']

    # Last event (conclusion)
    last = events[-1]['text']

    # Peak event (highest emotional salience in middle)
    middle_events = events[1:-1]
    peak_event = max(
        middle_events,
        key=lambda e: abs(e.get('sentiment_score', 0) * e.get('salience', 1))
    )
    peak = peak_event['text']

    return f"{first} ... {peak} ... {last}"
```

### 4.6 Compression for Repetitive Routines

For habits/routines that repeat, compress redundant info:

```python
def compress_routine_texts(texts: List[str]) -> str:
    """
    Compress repetitive texts by finding common patterns.

    Example:
    ["Morning coffee at 7am", "Morning coffee at 7:15am", "Morning coffee at 6:45am"]
    → "Morning coffee (typically around 7am, 3 occurrences)"
    """
    if len(texts) <= 1:
        return texts[0] if texts else ""

    # Find longest common prefix
    import os
    prefix = os.path.commonprefix(texts)

    if len(prefix) > 10:
        # Good common prefix found
        variations = [t[len(prefix):].strip() for t in texts]
        unique_variations = list(set(variations))[:3]
        return f"{prefix.strip()} ({len(texts)} times, variations: {', '.join(unique_variations)})"

    # Fallback: first text + count
    return f"{texts[0]} (and {len(texts)-1} similar events)"
```

### 4.7 Per-Layer Strategy Recommendation

| Layer | Primary Strategy | Fallback Strategy |
| ----- | ---------------- | ----------------- |
| **st_epi** | TextRank (if >5 events) | Concatenation + Template header |
| **st_sem** | Template from pattern_type | First source text as evidence |
| **st_procedural** | Template from action_sequence | Routine name only |
| **st_social** | Template from relationship fields | Actor names + type |
| **st_prospective** | Use `intention_description` directly | Template from intent_type |
| **st_kg_dom** | Template: name + type + aliases | Canonical name only |
| **st_kg_edges** | Template: subject + relation + object | Relation type only |

### 4.8 SummaryGenerator Module Interface

```python
# k0/modules/consolidation/algorithms/summary_generator.py

class SummaryGenerator:
    """
    Non-LLM summary generation for all truth layers.

    Usage:
        generator = SummaryGenerator(entity_resolver)

        # Episode with source texts
        summary = generator.generate_episode_summary(
            source_texts=["Had dinner", "Discussed work", "Ordered Thai"],
            metadata=EpisodeMetadata(
                temporal_bucket="EVENING",
                day_of_week="FRIDAY",
                primary_location="Thai Palace",
                participants=["Mom", "Dad"],
            )
        )

        # Pattern
        desc = generator.generate_pattern_description(
            pattern_name="Weekly Thai dinner",
            pattern_type="ROUTINE",
            attributes={"frequency": "weekly", "day": "Friday"},
            source_texts=["Thai dinner with family"],
        )
    """

    def __init__(self, entity_resolver: Optional[EntityResolver] = None):
        self.entity_resolver = entity_resolver
        self.template_generator = TemplateSummaryGenerator()

    def generate_for_layer(
        self,
        layer: str,
        record: dict,
        source_texts: Optional[List[str]] = None,
    ) -> str:
        """Generate embedding text for any truth layer."""
        if layer == 'st_epi':
            return self._generate_episode(record, source_texts)
        elif layer == 'st_sem':
            return self._generate_pattern(record, source_texts)
        elif layer == 'st_procedural':
            return self._generate_routine(record, source_texts)
        elif layer == 'st_social':
            return self._generate_relationship(record)
        elif layer == 'st_prospective':
            return self._generate_intention(record)
        elif layer == 'st_kg_dom':
            return self._generate_entity(record)
        elif layer == 'st_kg_edges':
            return self._generate_edge(record)
        else:
            raise ValueError(f"Unknown layer: {layer}")

    def _generate_episode(
        self,
        record: dict,
        source_texts: Optional[List[str]],
    ) -> str:
        """Generate episode embedding text."""
        # 1. Build template header from metadata
        header = self.template_generator.generate_episode_summary(record)

        # 2. Process source texts
        if not source_texts:
            return header

        if len(source_texts) <= 3:
            body = " | ".join(source_texts)
        elif len(source_texts) <= 10:
            body = textrank_summarize(source_texts, num_sentences=3)
        else:
            body = textrank_summarize(source_texts, num_sentences=5)

        return f"{header}: {body}" if header else body
```

---

## 5. Schema Changes Required

### 5.1 Summary: Current vs Required Fields

| Layer | Has text? | Has embedding_id? | Needs Added |
| ----- | --------- | ----------------- | ----------- |
| st_hipp_events | ✅ `text` | ✅ `embedding_id` | — (complete) |
| st_vec | — | ✅ PK | `source_layer`, `source_id`, `embedding_text` |
| st_epi | ⚠️ `episode_summary` only | ✅ (no FK) | `source_texts_json`, `embedding_text` |
| st_sem | ⚠️ `pattern_description` | ✅ (no FK) | `source_texts_json`, `embedding_text` |
| st_procedural | ❌ None | ❌ None | `embedding_id`, `source_texts_json`, `embedding_text` |
| st_social | ❌ None | ❌ None | `embedding_id`, `source_texts_json`, `embedding_text` |
| st_prospective | ✅ `intention_description` | ❌ None | `embedding_id`, `source_texts_json` |
| st_kg_dom | ⚠️ `canonical_name` only | ✅ (no FK) | `entity_description`, `source_texts_json` |
| st_kg_edges | ❌ None | ❌ None | `embedding_id`, `edge_description`, `source_texts_json` |

### 5.2 New Columns Per Layer

All truth layers need these new columns to preserve source text before st_hipp_events decay:

```sql
-- ═══════════════════════════════════════════════════════════════════════════════
-- st_epi: Episodic Memory — Preserve source event texts
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE st_epi ADD COLUMN source_texts_json TEXT;       -- JSON array of original event texts
ALTER TABLE st_epi ADD COLUMN embedding_text TEXT;          -- Generated text for UltraBERT
-- source_texts_json: ["Had dinner with Mom", "Discussed her garden project", "She mentioned Dad's birthday"]
-- embedding_text: "Friday evening at Thai Palace with Mom: Had dinner with Mom | Discussed her garden project | She mentioned Dad's birthday"

-- ═══════════════════════════════════════════════════════════════════════════════
-- st_sem: Semantic Patterns — Preserve source texts + generate description
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE st_sem ADD COLUMN source_texts_json TEXT;       -- JSON array of source event texts
ALTER TABLE st_sem ADD COLUMN embedding_text TEXT;          -- Generated from template + sources
-- Ensure pattern_description is populated (currently NULL!)
-- source_texts_json: ["Thai dinner on Friday", "Going to Thai Palace again", "Love the pad thai here"]
-- embedding_text: "ROUTINE: Weekly Thai dinner - We go to Thai Palace every Friday (e.g., 'Thai dinner on Friday')"

-- ═══════════════════════════════════════════════════════════════════════════════
-- st_procedural: Habits & Routines — Add embedding support
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE st_procedural ADD COLUMN embedding_id TEXT;     -- FK to st_vec
ALTER TABLE st_procedural ADD COLUMN source_texts_json TEXT;
ALTER TABLE st_procedural ADD COLUMN embedding_text TEXT;   -- Generated from routine + steps
-- source_texts_json: ["Making morning coffee", "Grinding the beans", "Brewing espresso"]
-- embedding_text: "Morning coffee routine: grind beans, add water, brew for 4 minutes"

-- ═══════════════════════════════════════════════════════════════════════════════
-- st_social: Relationships — Add text representation
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE st_social ADD COLUMN embedding_id TEXT;
ALTER TABLE st_social ADD COLUMN source_texts_json TEXT;    -- Evidence texts
ALTER TABLE st_social ADD COLUMN embedding_text TEXT;       -- Generated relationship summary
-- source_texts_json: ["Called Mom today", "Mom visited for dinner", "Discussed finances with Mom"]
-- embedding_text: "User is family with Sarah (Mom) - close relationship, weekly interactions"

-- ═══════════════════════════════════════════════════════════════════════════════
-- st_prospective: Intentions & Goals — Add embedding support
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE st_prospective ADD COLUMN embedding_id TEXT;
ALTER TABLE st_prospective ADD COLUMN source_texts_json TEXT;
-- Already has: intention_description + target_context (use as embedding_text)
-- source_texts_json: ["Mentioned wanting to visit Mom", "Should plan Mother's Day trip"]

-- ═══════════════════════════════════════════════════════════════════════════════
-- st_kg_dom: KG Entities — Add description for embedding
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE st_kg_dom ADD COLUMN entity_description TEXT;   -- Full description for UltraBERT
ALTER TABLE st_kg_dom ADD COLUMN source_texts_json TEXT;    -- Evidence texts
-- canonical_name: "Thai Palace"
-- entity_description: "Thai Palace (restaurant) also known as TP [cuisine: Thai, location: Market St]"
-- source_texts_json: ["Dinner at Thai Palace", "Best pad thai at Thai Palace"]

-- ═══════════════════════════════════════════════════════════════════════════════
-- st_kg_edges: KG Relationships — Add embedding support
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE st_kg_edges ADD COLUMN embedding_id TEXT;
ALTER TABLE st_kg_edges ADD COLUMN edge_description TEXT;   -- "Mom dines at Thai Palace (5 times)"
ALTER TABLE st_kg_edges ADD COLUMN source_texts_json TEXT;
-- edge_description: "Mom dines at Thai Palace (observed 5 times)"
-- source_texts_json: ["Mom and I at Thai Palace", "Took Mom to her favorite restaurant"]
```

---

### 5.3 Solution A: Extend st_vec (Polymorphic Source) — ~~REJECTED~~

> **Decision**: This approach was rejected in favor of Solution C (Inline Vectors).
> Reason: Adding polymorphic references to st_vec creates tight coupling and complex
> cross-table queries. The entity graph (st_kg_dom) already provides linking.

~~Add `source_layer` and `source_id` columns to st_vec~~

**Rejected because**:

- Polymorphic references break FK integrity
- Adds complexity to already-busy st_vec table
- Cross-layer queries require expensive JOINs
- Entity graph already exists for linking

---

### 5.4 Solution B: st_vec_links Junction Table — ~~REJECTED~~

> **Decision**: Rejected. Junction tables add query complexity without providing
> the semantic linking that entity graph already offers.

**Rejected because**:

- Extra table = extra JOINs
- Links are syntactic (IDs) not semantic (entities)
- Entity graph already captures semantic relationships

---

### 5.5 Solution C: Inline Vectors in Truth Layers — ✅ ACCEPTED

Store embedding vectors **directly in each truth layer** as BYTEA columns:

```sql
-- ═══════════════════════════════════════════════════════════════════════════════
-- INLINE VECTOR COLUMNS — Add to each truth layer
-- ═══════════════════════════════════════════════════════════════════════════════

-- st_epi: Episode vectors
ALTER TABLE st_epi ADD COLUMN embedding_vector BYTEA;       -- 768-dim → 3072 bytes
ALTER TABLE st_epi ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';

-- st_sem: Pattern vectors
ALTER TABLE st_sem ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_sem ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';

-- st_procedural: Routine vectors
ALTER TABLE st_procedural ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_procedural ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';

-- st_social: Relationship vectors
ALTER TABLE st_social ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_social ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';

-- st_prospective: Intention vectors
ALTER TABLE st_prospective ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_prospective ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';

-- st_kg_dom: Entity vectors
ALTER TABLE st_kg_dom ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_kg_dom ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';
```

**Pros**:

- ✅ **No st_vec dependency** — Each layer owns its vectors
- ✅ **Single INSERT** — R7 writes vector + text + metadata atomically
- ✅ **No JOINs** — Vector lives with the data it represents
- ✅ **Simple backfill** — UPDATE each layer directly
- ✅ **Model versioning** — `embedding_model` column tracks version per-row

**Cons**:

- ⚠️ Storage duplication if same text appears in multiple layers (rare)
- ⚠️ FAISS index must UNION across 7 tables (one-time build)

---

### 5.6 Cross-Layer Linking: Entity Graph (st_kg_dom)

**Key Insight**: We don't need vector-to-vector links. The **Entity Graph** already
provides semantic cross-layer linking through entity IDs.

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    ENTITY GRAPH AS UNIVERSAL LINKER                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│                              ┌──────────────┐                                    │
│                              │  st_kg_dom   │                                    │
│                              │  (Entities)  │                                    │
│                              │              │                                    │
│                              │  entity_id ──┼───────────────────────────────┐    │
│                              │  "Mom"       │                               │    │
│                              └──────┬───────┘                               │    │
│                                     │                                       │    │
│        ┌────────────────────────────┼────────────────────────────┐          │    │
│        │                            │                            │          │    │
│        ▼                            ▼                            ▼          ▼    │
│  ┌──────────┐                ┌──────────┐                ┌──────────┐  ┌────────┐│
│  │  st_epi  │                │ st_sem   │                │st_social │  │st_prosp││
│  ├──────────┤                ├──────────┤                ├──────────┤  ├────────┤│
│  │particip- │                │actor_id  │                │actor_a_id│  │actor_id││
│  │ants_json │                │          │                │actor_b_id│  │        ││
│  │ ["Mom",  │                │ "Mom"    │                │ "Mom"    │  │ "Mom"  ││
│  │  "Dad"]  │                │          │                │ "User"   │  │        ││
│  └──────────┘                └──────────┘                └──────────┘  └────────┘│
│                                                                                  │
│  Linking Columns Already Exist:                                                  │
│  • st_epi.participants_json → entity IDs                                         │
│  • st_sem.actor_id → entity ID                                                   │
│  • st_social.actor_a_id, actor_b_id → entity IDs                                │
│  • st_prospective.actor_id → entity ID                                           │
│  • st_procedural.actor_id → entity ID                                            │
│  • st_kg_edges.source_entity_id, target_entity_id → entity IDs                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Query Pattern for Rich LLM Context**:

```python
def expand_context_via_entity_graph(vector_match_ids: List[str]) -> dict:
    """
    Given vector search results, expand to full context using entity graph.

    1. Vector search returns: [episode_123, pattern_456]
    2. Extract entity IDs from participants_json, actor_id
    3. Traverse entity graph for related entities
    4. Fetch all truth records linked to those entities
    5. Return rich context for LLM
    """
    # Step 1: Get entity IDs from matched records
    entities = set()
    for record in fetch_records(vector_match_ids):
        if record.layer == 'st_epi':
            entities.update(json.loads(record.participants_json))
        elif record.layer == 'st_sem':
            entities.add(record.actor_id)
        # ... etc for each layer

    # Step 2: Expand via entity graph (1-hop neighbors)
    expanded_entities = expand_entity_graph(
        entity_ids=list(entities),
        max_hops=1,
        min_edge_weight=0.5
    )

    # Step 3: Fetch all truth records for expanded entities
    context = {
        'episodes': fetch_episodes_for_entities(expanded_entities),
        'patterns': fetch_patterns_for_entities(expanded_entities),
        'relationships': fetch_relationships_for_entities(expanded_entities),
        'intentions': fetch_intentions_for_entities(expanded_entities),
    }

    return context
```

---

## 6. Recommended Architecture: Inline Vectors + Entity Graph

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         RECOMMENDED ARCHITECTURE                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                        QUERY FLOW (P01 Recall)                           │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│       User Query                                                                 │
│           │                                                                      │
│           ▼                                                                      │
│   ┌───────────────┐                                                              │
│   │   UltraBERT   │  Embed query                                                │
│   │   768-dim     │                                                              │
│   └───────┬───────┘                                                              │
│           │                                                                      │
│           ▼                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                      FAISS Union Index                                 │     │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │     │
│   │  │ st_epi  │ │ st_sem  │ │st_proced│ │st_social│ │st_prosp │          │     │
│   │  │ vectors │ │ vectors │ │ vectors │ │ vectors │ │ vectors │          │     │
│   │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘          │     │
│   │                                                                        │     │
│   │  Returns: [(layer, id, score), ...]                                    │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│           │                                                                      │
│           ▼                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                    Entity Graph Expansion                              │     │
│   │                                                                        │     │
│   │   1. Extract entity IDs from matched records                           │     │
│   │   2. Traverse st_kg_dom → st_kg_edges for neighbors                   │     │
│   │   3. Fetch related truth records                                       │     │
│   │                                                                        │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│           │                                                                      │
│           ▼                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                       Rich LLM Context                                 │     │
│   │                                                                        │     │
│   │   {                                                                    │     │
│   │     "direct_matches": [...],      // Vector search results             │     │
│   │     "related_episodes": [...],    // From entity expansion            │     │
│   │     "actor_patterns": [...],      // Patterns for same actors         │     │
│   │     "relationships": [...],       // Social graph context             │     │
│   │     "active_intentions": [...]    // Goals involving same entities    │     │
│   │   }                                                                    │     │
│   │                                                                        │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Schema Migration (1 day)

1. Add `embedding_vector BYTEA` + `embedding_model TEXT` to 6 truth layers
2. Add `source_texts_json TEXT` + `embedding_text TEXT` to all layers
3. No st_vec modifications needed

### Phase 2: SummaryGenerator Module (2 days)

1. Template-based text generation for each layer
2. TextRank extractive summarization for episodes
3. Integrate with R7 writers

### Phase 3: R7 Writer Updates (3 days)

1. Fetch source event texts BEFORE st_hipp_events decay
2. Generate `embedding_text` via SummaryGenerator
3. Create embedding via UltraBERT
4. Single INSERT with: data + source_texts_json + embedding_text + embedding_vector

### Phase 4: P08 FAISS Union Index (1 day)

1. Build composite index from 6 truth layers
2. Metadata tracks (layer, record_id) for each vector
3. Batch rebuild every 6 hours (or on-demand)

### Phase 5: P01 Context Expander (2 days)

1. Vector search returns [(layer, id, score)]
2. Extract entity IDs from matched records
3. Traverse entity graph for related context
4. Return structured context for LLM

### Phase 6: Backfill Existing Records (2 days)

1. Scan truth layers for NULL embedding_vector
2. Generate embedding_text from existing columns
3. Create embeddings via UltraBERT batch API
4. UPDATE in batches of 1000

---

## 7. Impact on Pipelines

### P01 (Recall) — **Major Update**

- Vector search uses FAISS Union Index (built from 6 truth layers)
- **NEW**: Entity Graph Expansion after vector matches
- Returns rich context including:
  - Direct vector matches
  - Related episodes (via entity graph)
  - Actor patterns and relationships
  - Active intentions

```python
# P01 Recall Flow (Updated)
def recall(query: str, tenant_id: str) -> RecallContext:
    # 1. Embed query
    query_vec = ultrabert.embed(query)

    # 2. Vector search across all truth layers
    matches = faiss_union.search(query_vec, k=20)
    # Returns: [(layer='st_epi', id='ep_123', score=0.92), ...]

    # 3. Entity expansion (NEW)
    entity_ids = extract_entities_from_matches(matches)
    expanded = entity_graph.expand(entity_ids, max_hops=1)

    # 4. Fetch related context
    context = build_rich_context(matches, expanded)

    return context
```

### P02 (Write) — **No Change**

- Continues writing to st_hipp_events + st_vec
- st_vec for events only (short-lived, pre-consolidation)

### P03 (Consolidation) — **Critical Changes**

- **R7 writers**: MUST fetch source event texts BEFORE decay
- **R7 writers**: Generate embedding_text via SummaryGenerator
- **R7 writers**: Create embedding via UltraBERT
- **R7 writers**: Single INSERT with all fields (atomic)

```python
# R7 Writer (Updated)
def write_episode(episode: ConsolidatedEpisode):
    # 1. Fetch source texts (BEFORE they decay!)
    source_texts = fetch_source_event_texts(episode.source_event_ids)

    # 2. Generate embedding text
    embedding_text = summary_generator.generate_episode_summary(
        source_texts=source_texts,
        metadata=episode.metadata
    )

    # 3. Create embedding
    embedding_vector = ultrabert.embed(embedding_text)

    # 4. Single atomic INSERT
    db.execute("""
        INSERT INTO st_epi (
            episode_id, ...,
            source_texts_json,
            embedding_text,
            embedding_vector,
            embedding_model
        ) VALUES (?, ..., ?, ?, ?, ?)
    """, [
        episode.id, ...,
        json.dumps(source_texts),
        embedding_text,
        embedding_vector.tobytes(),  # BYTEA
        'ultrabert-v2.1.0'
    ])
```

### P08 (Embedding/Indexing) — **Major Update**

- **NEW**: Build FAISS Union Index from 6 truth layers
- Metadata tracks (layer, record_id) for each vector
- Batch rebuild every 6 hours (configurable)
- Backfill job for existing records with NULL embedding_vector

```python
# P08 FAISS Union Build
def build_union_index():
    vectors = []
    metadata = []

    for layer in ['st_epi', 'st_sem', 'st_procedural',
                  'st_social', 'st_prospective', 'st_kg_dom']:
        rows = db.query(f"""
            SELECT {pk_column(layer)}, embedding_vector
            FROM {layer}
            WHERE embedding_vector IS NOT NULL
              AND lifecycle_status = 'ACTIVE'
        """)
        for row in rows:
            vectors.append(np.frombuffer(row.embedding_vector, dtype=np.float32))
            metadata.append({'layer': layer, 'id': row[0]})

    index = faiss.IndexFlatIP(768)  # Inner product for normalized vectors
    index.add(np.array(vectors))

    return index, metadata
```

---

## 8. Effort Estimate (Revised)

| Phase | Effort | Priority | Dependencies |
| ----- | ------ | -------- | ------------ |
| Phase 1: Schema Migration | 1 day | P0 (Critical) | None |
| Phase 2: SummaryGenerator Module | 2 days | P0 (Critical) | None |
| Phase 3: R7 Writer Updates | 3 days | P0 (Critical) | Phase 1, 2 |
| Phase 4: P08 FAISS Union Index | 1 day | P0 (Critical) | Phase 3 |
| Phase 5: P01 Context Expander | 2 days | P1 (Important) | Phase 4 |
| Phase 6: Backfill Existing Records | 2 days | P1 (Important) | Phase 3 |
| Phase 7: Intent-Aware Prospective Writer | 1 day | P1 (Important) | Phase 3 |
| Phase 8: Intent-Aware Memory Formation | 4 days | P1 (Important) | Phase 7, R5 |
| **Total** | **16 days** | | |

### Phase Details

#### Phase 1: Schema Migration (1 day)

- Add `embedding_vector BYTEA`, `embedding_model TEXT` to 6 layers
- Add `source_texts_json TEXT`, `embedding_text TEXT` to all layers
- No st_vec changes needed

#### Phase 2: SummaryGenerator Module (2 days)

- Implement `k0/modules/consolidation/algorithms/summary_generator.py`
- Template-based generation for each layer type
- TextRank extractive summarization for episodes with many events
- Unit tests for all layer types

#### Phase 3: R7 Writer Updates (3 days)

- Update `truth_write_assembler.py` to fetch source texts
- Update each layer writer to include embedding fields
- Single atomic INSERT per layer
- Integration tests for write path

#### Phase 4: P08 FAISS Union Index (1 day)

- Build composite index from 6 truth layers
- Metadata tracks (layer, record_id) per vector
- Scheduled rebuild job

#### Phase 5: P01 Context Expander (2 days)

- Entity extraction from vector matches
- Entity graph traversal (1-hop)
- Rich context assembly for LLM

#### Phase 6: Backfill Existing Records (2 days)

- Scan for NULL embedding_vector
- Generate embedding_text from existing columns
- Batch UltraBERT calls
- UPDATE in batches of 1000

#### Phase 7: Intent-Aware Prospective Writer (1 day)

- R5 ForwardSimulator: Detect `intent_category = "set_reminder"` in event batch
- Parse `temporal_json` for target_date extraction
- R7 ProspectiveLayerWriter: Create st_prospective record with `intention_type = "REMINDER"`
- Integration tests for reminder flow

#### Phase 8: Intent-Aware Memory Formation (4 days)

Extends Phase 7 to cover ALL intent types for secondary memory formation (dreaming):

**8.1 Schema Migration** (0.5 day):

- st_prospective: Add `decision_domain`, `outcome`, `resolved_at` columns
- st_prospective: Extend intention_type CHECK to include `DECISION`, `CONCERN`, `TASK`
- st_sem: Add `pattern_domain` column
- st_kg_dom: Add `query_count`, `last_queried_at`, `milestones_json` columns
- st_kg_edges: Add `query_count`, `last_queried_at`, `sentiment_avg` columns

**8.2 R1 Importance Scorer — Query Entity Boost** (0.5 day):

- Boost salience for entities with high query_count
- Formula: `salience *= (1 + log(query_count + 1) * 0.1)`
- Integration point: `k0/modules/consolidation/algorithms/importance_scorer.py`

**8.3 R4 KG Consolidator — Query Tracking** (0.5 day):

- When `intent_label == "query_memory"`: increment entity query_count
- Stage KG_QUERY_INCREMENT writes to st_kg_dom, st_kg_edges
- Integration point: `k0/pipelines/p03/phases/r4_kg_consolidator.py`

**8.4 R5 Forward Simulator — Intent Signal Detection** (1 day):

- Detect memory formation signals from all intent types
- ReminderSignal (set_reminder) → st_prospective REMINDER
- DecisionSignal (seek_advice) → st_prospective DECISION
- LessonSignal (reflect) → st_sem LESSON pattern
- EmotionalSignal (express_feeling) → st_sem EMOTIONAL_TREND pattern
- QuerySignal (query_memory) → st_kg_dom/edges query_count
- MilestoneSignal (share_news) → st_kg_dom milestones_json
- Integration point: `k0/modules/consolidation/algorithms/forward_simulator.py`

**8.5 R6 Staging — Intent Router** (0.5 day):

- Route R5 IntentSignals to appropriate layer writers
- TruthWriteAssembler.assemble_intent_signal_writes()
- Integration point: `k0/modules/consolidation/staging/truth_write_assembler.py`

**8.6 R7 Layer Writer Updates** (0.5 day):

- SemanticLayerWriter: Add pattern_type `LESSON`, `EMOTIONAL_TREND`
- ProspectiveLayerWriter: Add intention_type `DECISION`, `CONCERN`
- KGLayerWriter: Handle query_count increment, milestones_json

**8.7 Integration Tests** (0.5 day):

- Test each intent → layer flow
- Test query_count accumulation over multiple events
- Test decision lifecycle (PENDING → RESOLVED)

**Intent → Memory Layer Matrix**:

| Intent | st_epi | st_sem | st_prospective | st_kg_dom | st_kg_edges |
|--------|--------|--------|----------------|-----------|-------------|
| log_memory | ✅ Primary | Pattern detection | — | Entity extraction | Edge strengthening |
| query_memory | — | — | — | **Query count++** | **Query count++** |
| set_reminder | ✅ Context | — | ✅ **REMINDER** | Entity extraction | — |
| express_feeling | ✅ Emotional | **EMOTIONAL_TREND** | — | Entity extraction | Sentiment on edge |
| seek_advice | ✅ Context | — | ✅ **DECISION** | Entity extraction | — |
| share_news | ✅ Milestone | — | — | **Milestone tracking** | — |
| reflect | ✅ Introspection | ✅ **LESSON** | — | Entity extraction | Insight edges |
| other | ✅ Default | — | — | Entity extraction | — |

---

## 9. UltraBERT Capability Utilization Analysis

### 9.1 Current UltraBERT Outputs vs Storage/Usage

UltraBERT provides **12 capabilities** in a single forward pass. Analysis of what is stored and used:

| UltraBERT Capability | Labels | Stored in st_hipp_events? | Actually Used? |
|---------------------|--------|--------------------------|----------------|
| **Sentiment** (5) | very_negative → very_positive | `sentiment_label`, `sentiment_score` | ✅ M04 affect.analyze |
| **Emotions** (44) | joy, sadness, nostalgia, etc. | `dominant_emotions_json` | ✅ M04 affect.analyze |
| **Safety FamilyOS** (4) | GREEN/AMBER/RED/CRISIS | `safety_familyos_band` (0053) | ✅ Safety arbitration |
| **Safety Generic** (8) | toxic, threat, self_harm, etc. | ❌ NOT STORED | ❌ Not used |
| **NER Family** (21) | KINSHIP, PET, FAMILY_EVENT | `ner_entities_json` (0046) | ✅ P03 R4 |
| **NER General** (17) | PER, ORG, LOC, DATE | `ner_entities_json` (0046) | ✅ P03 R4 |
| **Temporal** (13) | DATE_ABS, DURATION, etc. | `temporal_json` (0046) | ✅ P03 R4 |
| **Intent** (8) | log_memory, set_reminder, etc. | `intent_category` (0046) | ⚠️ **STORED, NOT ROUTED** |
| **Ingress** (12) | DIARY, TASK, HEALTH, etc. | `ingress_category` (0046) | ⚠️ Underutilized |
| **Relation** (15) | parent_of, spouse_of, etc. | `extracted_relations_json` (0053) | ✅ st_social population |
| **NLI** (3) | entailment, neutral, contradiction | `nli_label` (0053) | ❌ Column exists, not used |
| **Embedding** | 768-dim | `st_vec.embedding` | ✅ Semantic search |

### 8.2 CQRS Architecture Alignment

FamilyOS uses CQRS (Command Query Responsibility Segregation):

- **Command Port** (P02): Writes → st_hipp_events
- **Query Port** (P01): Reads → Truth layers

**Key Insight**: K1 Intent Router handles query vs command routing at API level. The `intent_category` stored in st_hipp_events is for **provenance/analytics**, not K0 internal routing.

| Intent | Type | K1 Routing | K0 Responsibility |
|--------|------|------------|-------------------|
| `log_memory` | Command | K1 → P02 | Store in st_hipp_events ✅ |
| `query_memory` | Query | K1 → P01 | N/A (CQRS - K1 handles) |
| **`set_reminder`** | **Command** | K1 → P02 | **Create st_prospective record** ❌ |
| `express_feeling` | Command | K1 → P02 | Store with affect boost ✅ |
| `seek_advice` | Query | K1 → P01 | N/A (CQRS - K1 handles) |
| `share_news` | Command | K1 → P02 | Store in st_hipp_events ✅ |
| `reflect` | Query | K1 → P01 | N/A (CQRS - K1 handles) |
| `other` | Command | K1 → P02 | Default storage ✅ |

### 8.3 GAP: set_reminder Intent Not Creating st_prospective Records

**Problem**: When UltraBERT classifies intent as `set_reminder`, the system stores it in st_hipp_events but does NOT create a corresponding st_prospective record.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SET_REMINDER → ST_PROSPECTIVE GAP                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Current Flow (BROKEN):                                                      │
│                                                                              │
│  User: "Remind me to call Mom tomorrow at 3pm"                              │
│           │                                                                  │
│           ▼                                                                  │
│  UltraBERT: intent_category = "set_reminder"                                │
│             temporal_json = [{"text": "tomorrow at 3pm", "label": "TIME"}]  │
│           │                                                                  │
│           ▼                                                                  │
│  P02: Writes to st_hipp_events with intent_category = "set_reminder"        │
│           │                                                                  │
│           ▼                                                                  │
│  P03: R7 consolidates to st_epi (episodic) ← WRONG!                         │
│        Should create st_prospective (intention)                              │
│                                                                              │
│  Result: ❌ No reminder created                                              │
│          ❌ P05 (Prospective Triggers) has nothing to fire                   │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Required Flow (SOLUTION):                                                   │
│                                                                              │
│  User: "Remind me to call Mom tomorrow at 3pm"                              │
│           │                                                                  │
│           ▼                                                                  │
│  UltraBERT: intent_category = "set_reminder"                                │
│             temporal_json = [{"text": "tomorrow at 3pm", "label": "TIME"}]  │
│           │                                                                  │
│           ▼                                                                  │
│  P02: Writes to st_hipp_events with intent_category = "set_reminder"        │
│           │                                                                  │
│           ▼                                                                  │
│  P03 R5 (Forward Simulation): Detects intent_category = "set_reminder"      │
│           │                                                                  │
│           ▼                                                                  │
│  P03 R7 ProspectiveLayerWriter:                                             │
│    • intention_type = "REMINDER"                                             │
│    • intention_description = "Call Mom"                                      │
│    • target_date = parse(temporal_json) → tomorrow 3pm                       │
│    • target_context = original text                                          │
│           │                                                                  │
│           ▼                                                                  │
│  P05: Prospective trigger fires at target_date                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.4 Solution: Intent-Aware R5/R7 Processing

**Phase 7** (added to implementation plan): Update P03 to route `set_reminder` intent to st_prospective.

**Implementation Points**:

1. **R5 ForwardSimulator**: Check `intent_category` in event batch
   - If `set_reminder` detected → flag for prospective extraction
   - Parse `temporal_json` for target_date

2. **R7 ProspectiveLayerWriter**: Create st_prospective record
   - `intention_type = "REMINDER"`
   - `intention_description` = extracted action (e.g., "Call Mom")
   - `target_date` = parsed from temporal_json
   - `source_event_ids` = original event(s)

3. **st_prospective schema**: Already supports this (migration 0031)
   - `intention_type CHECK("GOAL", "PLAN", "REMINDER", "COMMITMENT", "WISH")`
   - `intention_description TEXT NOT NULL`
   - `target_date INTEGER` (Unix timestamp)

### 9.5 Underutilized Capabilities Summary

| Capability | Current State | Recommendation |
|-----------|---------------|----------------|
| **safety_generic** | Not stored | Store for audit logging in high-risk scenarios |
| **intent_category** | Stored, not routed | Route all intents → appropriate layers (Phase 7+8) |
| **ingress_category** | Stored, minimal use | Use for activity_type enrichment, analytics |
| **nli_label** | Column exists, not used | Future: fact-checking, contradiction detection |

---

## 10. ADR Requirements

Before implementation, the following ADRs are needed:

1. **ADR-KXXX: Inline Vector Storage in Truth Layers**
   - Rationale: Avoid st_vec dependency, enable atomic writes
   - Decision: Store embedding_vector BYTEA + embedding_model TEXT in each truth layer
   - Consequences: Storage per truth record +3KB, simpler write path, no JOINs
   - Alternatives Rejected: st_vec polymorphic extension (complex), junction table (extra JOINs)

2. **ADR-KXXX: Entity Graph as Cross-Layer Linking Mechanism**
   - Rationale: Entity IDs already exist in all truth layers (participants_json, actor_id)
   - Decision: Use st_kg_dom/st_kg_edges for context expansion, not vector-to-vector links
   - Consequences: P01 uses entity graph for "related memories", not similarity search
   - Alternatives Rejected: cross_refs_json in st_vec (redundant with entity graph)

3. **ADR-KXXX: Text Preservation Before Decay**
   - Rationale: st_hipp_events decays in 20 days, truth layers live 1-5 years
   - Decision: Copy source_texts_json to all truth layers during R7
   - Consequences: Storage increase ~2x per truth record

4. **ADR-KXXX: Non-LLM Summary Generation**
   - Rationale: LLM calls add latency and cost during consolidation
   - Decision: Template-based + TextRank extractive summarization
   - Alternatives Rejected: LLM (performance), raw concatenation (quality)

5. **ADR-KXXX: FAISS Union Index Architecture**
   - Rationale: Need single vector search across 6 truth layers
   - Decision: Build composite FAISS index with metadata (layer, id) per vector
   - Consequences: Index rebuild required when schema changes

---

## 11. Open Questions

### Answered Questions

1. **✅ Store consolidated text**: Yes, must store `source_texts_json` because st_hipp_events decays in 20 days. Regeneration on demand is not possible after events are tombstoned.

2. **✅ Summary Strategy**: Use non-LLM approaches (template-based + TextRank) for performance. LLM can be optional enhancement later.

3. **✅ st_vec Extension vs Inline**: Use inline vectors (embedding_vector BYTEA) in each truth layer. No st_vec modifications needed.

4. **✅ Cross-Layer Linking**: Use entity graph (st_kg_dom + st_kg_edges) for context expansion. Entity IDs are universal foreign keys via participants_json, actor_id columns.

### Open Questions

1. **Model Versioning**: How to handle embedding model upgrades across inline vectors?
   - Current approach: `embedding_model` column tracks version per-row
   - Need re-embedding strategy when UltraBERT updates

2. **Performance SLO**: What's the acceptable query latency for cross-layer vector search + entity expansion?
   - Current P01 SLO is <200ms
   - Entity graph expansion adds ~20-50ms per query

3. **Storage Growth**: Estimated storage growth with inline vectors:
   - ~3KB per 768-dim float32 vector (stored as BYTEA)
   - ~1.5KB per source_texts_json average
   - Total: ~5KB per truth record (new overhead)
   - For 100K episodes: ~500MB additional

4. **Backfill Strategy**: How to handle existing truth layer records without source texts?
   - Events may already be tombstoned (no source_texts_json possible)
   - Options: (a) leave embedding NULL, (b) generate from existing columns only

5. **FAISS Index Size**: Union index across 6 layers may grow large
   - 100K vectors × 768 dims × 4 bytes = ~300MB in memory
   - Need sharding strategy if >1M vectors

---

## 12. Related Milestone Plans

Detailed implementation issues are tracked in separate milestone documents:

| Milestone | Title | Effort | Location |
|-----------|-------|--------|----------|
| M1 | Schema Migration | 1 day | [GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_1_SCHEMA_MIGRATION.md) |
| M2 | Summary Generator | 2 days | [GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md) |
| M3 | R7 Writer Updates | 3 days | [GAP_001_MILESTONE_3_R7_WRITER_UPDATES.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_3_R7_WRITER_UPDATES.md) |
| M4 | FAISS Union Index | 1 day | [GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md) |
| M5 | Context Expander | 2 days | [GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md) |
| M7 | Intent-Aware Prospective Writer | 1 day | [GAP_001_MILESTONE_7_INTENT_PROSPECTIVE_WRITER.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_7_INTENT_PROSPECTIVE_WRITER.md) |
| M8 | Intent-Aware Memory Formation | 4 days | [GAP_001_MILESTONE_8_INTENT_MEMORY_FORMATION.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_8_INTENT_MEMORY_FORMATION.md) |
| M9 | R5 Dream Stage Cold Start Fix | 3 days | See §12.1 below |

> **Note**: Milestone 6 (Backfill) does not have a separate plan document; see Phase 6 details above.

---

### 12.1 Milestone 9: R5 Dream Stage Cold Start Fix (3 days)

**Status**: Identified (Jan 2026)
**Observed During**: 2000-event consolidation test

#### Problem Statement

R5 Dream Stage algorithms run successfully but produce **zero high-level outputs** despite processing 2000 events:

| Algorithm | Expected Output | Actual Output | Root Cause |
|-----------|----------------|---------------|------------|
| **BGT-SM** | Insights | 0 | Cold start threshold (10K) not met |
| **CPN** | Counterfactuals | 0 | No high-sentiment episodes (|score| ≥ 0.6) |
| **SPC-UQ** | Prospective Memories | 0 | No incomplete/fragmented episodes |
| **TDL-HCO** | Routine Optimizations | 0 | Insufficient temporal patterns |
| **IntentSignalDetector** | Intent Signals | ✅ 1,580 | Working correctly |
| **MCTS** | Forward Scenarios | ✅ 1 per batch | Working correctly |

**Logs from 2000-event test (20 batches × 100 events)**:

```
DreamExplorer completed exploration:
  insights_count: 0
  counterfactuals_count: 0
  prospective_count: 0
  routines_count: 0
  intent_signals_count: 72-88 per batch
  mcts_rollouts_used: 20
  all_succeeded: true
  failures: []
```

#### Root Cause Analysis

**1. BGT-SM Cold Start Check (bgt_sm.py:860-920)**:

```python
P03_BGT_COLD_START_THRESHOLD = 10_000  # Requires 10K observations

if self.config.corpus_size_n < self.config.cold_start_threshold:
    self._logger.info("BGT-SM cold start: corpus_size=%d < threshold=%d, skipping")
    return []  # No insights generated
```

**Problem**: 10,000 events is an unrealistic requirement for personal memory systems:

- Typical user generates 5-20 events/day
- 10K events = **500-2000 days** of usage (1.5-5.5 years)
- Early users get zero dream-stage benefits

**2. R5 Input Data Limited to Batch (r5_dream_explorer.py:374-380)**:

```python
input_data = DreamExplorerInput(
    recent_episodes=list(envelope.phases.r2_clusters),      # Episodes from THIS batch
    kg_entities=list(envelope.phases.r4_new_entities),      # NEW entities only
    kg_edges=list(envelope.phases.r4_new_edges),            # NEW edges only
)
```

**Problem**: R5 only sees newly created entities/edges per batch (2-10 entities, 0-2 edges), not the accumulated KG.

**3. CPN Emotional Threshold (cpn.py:65)**:

```python
emotional_threshold: float = 0.6  # Min |sentiment| for regret events
```

**Problem**: From 2000 events, sentiment distribution shows most events are neutral:

- Neutral: 51.8% (1,035 events)
- Positive: 29.0% (580 events)
- Negative: 19.2% (385 events)

Few events have |sentiment_score| ≥ 0.6 for counterfactual analysis.

#### Recommended Fixes

**Fix 1: Lower Cold Start Threshold for Personal Systems**

| Current | Proposed | Rationale |
|---------|----------|-----------|
| 10,000 | **1,000** | ~2-3 months of typical usage |

**Implementation**:

```python
# k0/modules/consolidation/algorithms/bgt_sm.py
P03_BGT_COLD_START_THRESHOLD = 1_000  # Lowered for personal memory systems
```

**ADR Required**: ADR-KXXX: R5 Cold Start Thresholds for Personal Memory Systems

**Fix 2: Pass Full Accumulated KG to R5**

Update R5 to receive accumulated KG instead of just new entities/edges:

```python
# k0/pipelines/p03/phases/r5_dream_explorer.py
# BEFORE:
kg_entities=list(envelope.phases.r4_new_entities)  # Only new

# AFTER:
kg_entities = await self._fetch_accumulated_kg_entities(
    tenant_id=envelope.context.tenant_id,
    space_id=envelope.context.space_id,
    limit=1000,  # Top 1000 by observation_count
)
```

**Trade-off**: Increases R5 input size but enables meaningful graph traversal.

**Fix 3: Lower CPN Emotional Threshold**

| Current | Proposed | Rationale |
|---------|----------|-----------|
| 0.6 | **0.4** | Captures more emotionally significant events |

**Implementation**:

```python
# k0/modules/consolidation/algorithms/cpn.py
emotional_threshold: float = 0.4  # Lowered from 0.6
```

**Fix 4: Add Entity Embeddings to st_kg_dom**

BGT-SM requires embeddings for semantic distance calculation:

```python
# Currently: embeddings dict is empty because st_kg_dom has no embeddings
embeddings = self._extract_embeddings(input_data)  # Returns {}
```

**Solution**: Populate `embedding_id` in st_kg_dom during R4 (already planned in Phase 1 schema migration).

#### Feasibility Analysis: Running R5 on 1,000 Events

| Algorithm | Current Min | Proposed Min | Feasibility |
|-----------|-------------|--------------|-------------|
| **BGT-SM** | 10K corpus | 1K corpus | ✅ PMI less reliable but still useful |
| **CPN** | High-emotion episodes | Moderate-emotion | ✅ May produce more noise |
| **SPC-UQ** | Fragmented episodes | Same | ⚠️ Needs episode fragmentation logic |
| **TDL-HCO** | Temporal patterns | Same | ⚠️ Needs ~30 days of habit data |
| **MCTS** | N/A | N/A | ✅ Already works |

**Verdict**: Running R5 on 1,000 events is **feasible** with adjusted thresholds:

- BGT-SM: PMI calculations less statistically robust but still surface useful connections
- CPN: Lower emotional threshold may produce more speculative counterfactuals
- SPC-UQ/TDL-HCO: Still require temporal accumulation, may remain inactive until ~30 days of data

#### Effort Estimate

| Task | Effort | Priority |
|------|--------|----------|
| 9.1 Lower BGT-SM cold start threshold | 0.5 day | P1 |
| 9.2 Pass accumulated KG to R5 | 1 day | P1 |
| 9.3 Lower CPN emotional threshold | 0.5 day | P2 |
| 9.4 Add entity embeddings to R4 | 1 day | P1 (Phase 1 dependency) |
| **Total** | **3 days** | |

#### Observations from 2000-Event Test

**What Worked Well**:

| Layer | Records | Quality |
|-------|---------|---------|
| st_hipp_events | 2,000 | ✅ All consolidated with embeddings |
| st_epi (Episodes) | 435 | ✅ Good clustering (~4.6 events/episode) |
| st_sem (Patterns) | 848 | ✅ 490 emotional trends, 258 lessons, 100 themes |
| st_prospective | 364 | ✅ 272 reminders, 92 decisions captured |
| st_vec | 2,000 | ✅ 100% embedding coverage |

**Semantic Layer Breakdown**:

- Emotional trends detected: annoyance (139), relief (89), joy (68), sadness (40), 18+ others
- Lessons learned: 258 patterns (e.g., "When I sleep 7+ hours, everything feels better")
- Themes: 100 patterns

**Prospective Memory Detection**:

- Reminders: 272 (e.g., "remind me to call Medical Center about GERD")
- Decisions: 92 (e.g., "Should I buy new monitor or fix current?")

**Issues Needing Improvement**:

| Issue | Severity | Root Cause |
|-------|----------|------------|
| Entity Type Misclassification | High | NER classifying "SSD", "GERD" as PERSON |
| Generic Edge Types | Medium | All edges use RELATED_TO |
| Duplicate Entities | Medium | "panda" vs "Panda" vs "cluster_PERSON_panda" |
| R5 Zero High-Level Outputs | Medium | Cold start thresholds too high |
| Theme Naming | Low | Generic "Pattern from [uuid]" names |

**Knowledge Graph Quality**:

- 188 entities extracted (43 UNKNOWN, 38 PERSON, 32 FAMILY_MEMBER, 25 ORGANIZATION)
- 38 edges (all RELATED_TO type)
- Entity misclassification examples: "SSD" → PERSON, "schema" → FAMILY_MEMBER
- Edge sparsity: 0.2 edges per entity (needs improvement)

#### Testing Checklist

After implementing M9 fixes, re-run 2000-event test and verify:

- [ ] BGT-SM generates insights (expect 5-20 per consolidation run)
- [ ] CPN generates counterfactuals (expect 3-10 per run)
- [ ] Entity embeddings populated in st_kg_dom
- [ ] R5 receives full accumulated KG (verify via logs)
- [ ] No performance regression (R5 duration <500ms target)

---

## 13. References

- [P03_consolidation_dossier_v2.md](../../pipelines/P03_consolidation_dossier_v2.md) - §4.4.1.1 Decay Thresholds, §6.3-6.10 Schema Design
- [decay_engine.py](../../../k0/modules/consolidation/algorithms/decay_engine.py) - UnifiedDecayEngine with per-layer λ values
- [k003-inline-embedding-ultrabert.md](../decisions-K0/pipelines/k003-inline-embedding-ultrabert.md) - Current embedding architecture
- [vector.py](../../../k0/modules/consolidation/truth_writer/layers/vector.py) - VectorLayerWriter implementation
- [truth_write_assembler.py](../../../k0/modules/consolidation/staging/truth_write_assembler.py) - R7 write assembly

---

## 14. st_vec Migration Inventory (Future Work)

This section catalogs all code locations that currently use `st_vec` for vector storage and retrieval.
After GAP-001 Phase 1 (M1) schema migration adds inline `embedding_vector` columns to truth layers,
these locations will need updating in subsequent phases to read from native columns instead of JOINing to st_vec.

### 14.1 Current st_vec Usage Pattern

```
CURRENT (st_vec JOIN pattern):
┌──────────────────┐      JOIN       ┌──────────────────┐
│   Truth Layer    │ ──────────────► │     st_vec       │
│   (st_epi, etc.) │  embedding_id   │  (vector BYTEA)  │
└──────────────────┘                 └──────────────────┘

FUTURE (inline vector pattern):
┌─────────────────────────────────────────────────────────┐
│   Truth Layer (st_epi, st_sem, etc.)                    │
│   embedding_vector BYTEA  ← Direct column, no JOIN      │
└─────────────────────────────────────────────────────────┘
```

### 14.2 Code Locations Requiring Migration

#### 14.2.1 TruthQueryService (P03 Reconciliation)

| File | Function | Current Behavior | Future Change |
|------|----------|------------------|---------------|
| [truth_query_service.py](../../../k0/modules/consolidation/staging/truth_query_service.py) | `_query_layer()` | JOINs `st_vec` on `embedding_id` | Read `embedding_vector` directly from truth layer |
| [truth_query_service.py](../../../k0/modules/consolidation/staging/truth_query_service.py) | `find_candidates()` | Queries 5 layers via st_vec JOIN | Query each layer's native `embedding_vector` column |
| [truth_query_service.py](../../../k0/modules/consolidation/staging/truth_query_service.py) | `_decode_bytea_vector()` | Decodes `v.vector` from st_vec | Decode `t.embedding_vector` from truth layer |

**Current Query Pattern** (lines 287-311):

```sql
SELECT t.{pk}, v.vector, v.vector_dim, t.{confidence}
FROM {layer} t
JOIN st_vec v ON t.embedding_id = v.embedding_id
WHERE t.tenant_id = $1 AND t.space_id = $2
```

**Future Query Pattern**:

```sql
SELECT {pk}, embedding_vector, confidence_score
FROM {layer}
WHERE tenant_id = $1 AND space_id = $2
  AND embedding_vector IS NOT NULL
```

#### 14.2.2 R0 Batch Selector (P03 Embedding Load)

| File | Function | Current Behavior | Future Change |
|------|----------|------------------|---------------|
| [r0_batch_selector.py](../../../k0/pipelines/p03/phases/r0_batch_selector.py) | `_load_embeddings_for_events()` | Queries `st_vec` by `event_id` | N/A for st_hipp_events (source layer keeps st_vec) |

**Note**: st_hipp_events is a source layer that will continue using st_vec. Only truth layers (st_epi, st_sem, etc.) get inline vectors.

**Current Query** (lines 700-705):

```sql
SELECT event_id, vector, vector_dim
FROM st_vec
WHERE event_id IN (...)
  AND status IN ('READY', 'INDEXED')
```

**Future**: No change needed for R0 — st_hipp_events is pre-consolidation.

#### 14.2.3 P08 Circuit Breaker (Embedding Fallback)

| File | Function | Current Behavior | Future Change |
|------|----------|------------------|---------------|
| [p08_circuit.py](../../../k0/pipelines/p03/ops/p08_circuit.py) | `_fallback_to_cached()` | Reads embedding from st_vec | Read from truth layer's `embedding_vector` if available |

**Current Query** (lines 130-140):

```sql
SELECT embedding
FROM st_vec
WHERE entity_id = $1 AND status = 'ACTIVE'
ORDER BY created_at DESC
LIMIT 1
```

**Future**: Fallback to truth layer embedding_vector column when st_vec unavailable.

#### 14.2.4 FAISS Circuit Breaker (Brute Force Fallback)

| File | Function | Current Behavior | Future Change |
|------|----------|------------------|---------------|
| [faiss_circuit.py](../../../k0/pipelines/p03/ops/faiss_circuit.py) | `_brute_force_search()` | Scans st_vec for vectors | Scan truth layers with `embedding_vector IS NOT NULL` |

**Current Query** (lines 176-185):

```sql
SELECT entity_id, embedding
FROM st_vec
WHERE space_id = $1 AND status = 'ACTIVE'
LIMIT 2000
```

**Future**: Query UNION across truth layers:

```sql
SELECT episode_id as entity_id, embedding_vector
FROM st_epi WHERE space_id = $1 AND embedding_vector IS NOT NULL
UNION ALL
SELECT semantic_id, embedding_vector
FROM st_sem WHERE space_id = $1 AND embedding_vector IS NOT NULL
-- ... etc for other layers
```

#### 14.2.5 FAISS Rebuild Script

| File | Function | Current Behavior | Future Change |
|------|----------|------------------|---------------|
| [rebuild_faiss_index.py](../../../k0/scripts/rebuild_faiss_index.py) | `_fetch_vectors()` | Bulk SELECT from st_vec | Build union index from all truth layer embeddings |

**Current Query** (lines 130-140):

```sql
SELECT embedding_id, vector, vector_dim
FROM st_vec
WHERE status = 'READY'
ORDER BY embedding_id
LIMIT $1 OFFSET $2
```

**Future** (M4 FAISS Union Index):

- Query each truth layer's `embedding_vector` column
- Build composite index with layer+id metadata
- See [GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md](../../plans_completed_donotrefer/GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md)

#### 14.2.6 Syscalls (st_vec Operations)

All st_vec syscalls in [syscalls.py](../../../k0/kernel/syscalls.py):

| Syscall | Lines | Purpose | Capability | Future Migration |
|---------|-------|---------|------------|------------------|
| `vec_write()` | 1296-1478 | INSERT into st_vec | st_vec.write | **Keep** — st_hipp_events stays on st_vec |
| `vec_query()` | 1479-1642 | SELECT from st_vec by status | st_vec.read | **Keep** — P08 FAISS indexer for pre-consolidation events |
| `vec_update_status()` | 1643-1760 | UPDATE st_vec status | st_vec.write | **Keep** — Status tracking for FAISS indexing |
| `embedding_vectors_batch_query()` | 3321-3435 | Batch SELECT from st_vec by embedding_ids | st_vec.read | **Extend** — Add layer parameter for truth layer vectors |

##### 14.2.6.1 `vec_write()` — No Migration Needed

**Purpose**: Writes 768-dim UltraBERT embeddings for st_hipp_events during P02.

**Current Query** (lines 1422-1437):

```sql
INSERT INTO st_vec (
    embedding_id, event_id, tenant_id, space_id,
    vector, vector_dim, model_id, status,
    created_at, updated_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, ...)
ON CONFLICT (embedding_id) DO NOTHING
```

**Migration**: None needed. st_hipp_events is a source layer that continues using st_vec for pre-consolidation embeddings.

##### 14.2.6.2 `vec_query()` — No Migration Needed

**Purpose**: Queries st_vec by status for P08 FAISS indexer to find READY embeddings.

**Current Query** (lines 1580-1595):

```sql
SELECT embedding_id, event_id, tenant_id, space_id,
       vector, vector_dim, model_id, status, created_at
FROM st_vec
WHERE status = $1 AND tenant_id = $2
ORDER BY created_at ASC
LIMIT $3 OFFSET $4
```

**Migration**: None needed. This serves P08 FAISS indexer for st_hipp_events embeddings.

##### 14.2.6.3 `vec_update_status()` — No Migration Needed

**Purpose**: Updates st_vec status after FAISS indexing (READY → INDEXED).

**Current Query** (lines 1720-1730):

```sql
UPDATE st_vec SET status = $1, indexed_at = $2, updated_at = ...
WHERE embedding_id = $3
```

**Migration**: None needed. Tracks FAISS indexing status for pre-consolidation vectors.

##### 14.2.6.4 `embedding_vectors_batch_query()` — Extend for Truth Layers

**Purpose**: Batch queries st_vec for embedding vectors (used by R5 BGT-SM for semantic distance).

**Current Query** (lines 3383-3390):

```sql
SELECT embedding_id, vector, vector_dim
FROM st_vec
WHERE embedding_id IN (...)
  AND status = 'INDEXED'
```

**Future Enhancement**: Add optional `layer` parameter to query truth layer inline vectors:

```python
# Future signature
async def embedding_vectors_batch_query(
    self,
    embedding_ids: list[str],
    layer: str | None = None,  # NEW: "st_epi", "st_sem", etc.
) -> dict[str, Any]:
    if layer and layer in TRUTH_LAYERS:
        # Query truth layer's embedding_vector column
        query = f"""
            SELECT {PK_COLUMNS[layer]} as id, embedding_vector as vector
            FROM {layer}
            WHERE {PK_COLUMNS[layer]} IN (...)
              AND embedding_vector IS NOT NULL
        """
    else:
        # Fall back to st_vec (default, pre-consolidation)
        query = "SELECT embedding_id, vector FROM st_vec WHERE ..."
```

**New Capability**: Consider adding `{layer}.vector.read` capability for each truth layer.

**Note**: `st_vec.write` and `st_vec.read` capabilities remain for st_hipp_events.
New capabilities may be needed for truth layer vector operations.

#### 14.2.7 Embedding Cleanup Module

| File | Function | Current Behavior | Future Change |
|------|----------|------------------|---------------|
| [cleanup.py](../../../k0/modules/embedding/cleanup.py) | `_delete_orphan_embeddings()` | Deletes from st_vec | Also clear truth layer embedding_vector columns on tombstone |

**Current** (lines 136-150):

- Identifies orphaned embeddings in st_vec
- Deletes via `vec_delete` syscall

**Future**: When truth layer records are tombstoned, set `embedding_vector = NULL` to reclaim storage.

#### 14.2.8 FAISS Indexer Module

| File | Function | Current Behavior | Future Change |
|------|----------|------------------|---------------|
| [faiss_indexer.py](../../../k0/modules/embedding/faiss_indexer.py) | `_index_embedding()` | Reads from st_vec, adds to FAISS | Read from truth layer inline vectors |

**Requires**: `st_vec.read` capability (currently)
**Future**: Query truth layers directly, build union index per M4 plan.

### 14.3 Truth Layer Vector Columns (Post-M1)

After M1 schema migration, each truth layer will have:

| Layer | PK Column | Vector Column | Model Column | Status |
|-------|-----------|---------------|--------------|--------|
| st_epi | episode_id | embedding_vector | embedding_model | M1 adds columns |
| st_sem | semantic_id | embedding_vector | embedding_model | M1 adds columns |
| st_procedural | routine_id | embedding_vector | embedding_model | M1 adds columns |
| st_social | relationship_id | embedding_vector | embedding_model | M1 adds columns |
| st_prospective | intention_id | embedding_vector | embedding_model | M1 adds columns |
| st_kg_dom | entity_id | embedding_vector | embedding_model | M1 adds columns |

**Note**: st_hipp_events and st_vec remain unchanged — they handle pre-consolidation vectors.

### 14.4 Migration Priority

| Priority | Component | Effort | Phase |
|----------|-----------|--------|-------|
| P1 | TruthQueryService | 2 days | Phase 2 (M3) |
| P1 | FAISS Rebuild Script | 1 day | Phase 4 (M4) |
| P2 | FAISS Circuit Brute Force | 0.5 day | Phase 4 (M4) |
| P2 | P08 Circuit Fallback | 0.5 day | Phase 4 (M4) |
| P3 | Embedding Cleanup | 0.5 day | Phase 6 |
| P3 | FAISS Indexer | 1 day | Phase 4 (M4) |

**Total Effort**: ~5.5 days across Phases 2-6

### 14.5 Backward Compatibility

During transition:

1. **Dual-Path Queries**: TruthQueryService can query both:
   - `embedding_vector` (inline, preferred)
   - st_vec JOIN (fallback for records without inline vectors)

2. **Gradual Rollout**: New truth records get inline vectors; existing records query via st_vec until backfilled.

3. **Feature Flag**: `ENABLE_INLINE_TRUTH_VECTORS` controls query path:

   ```python
   if settings.ENABLE_INLINE_TRUTH_VECTORS and record.embedding_vector:
       return decode_vector(record.embedding_vector)
   else:
       return await self._query_st_vec(record.embedding_id)
   ```

### 14.6 Test Updates Required

| Test File | Current Mock | Future Mock |
|-----------|--------------|-------------|
| test_r3_integration.py | MockConnection.st_vec_rows | Add inline embedding_vector support |
| test_p03_r0_batch_selector.py | st_vec_rows fixture | N/A (R0 keeps st_vec) |
| test_p03_faiss_circuit.py | st_vec query mocks | Add truth layer query mocks |
| test_r7_truth_writer.py | LAYER_ST_VEC writes | Add embedding_vector column writes |

**Note**: Current tests pass with st_vec pattern; migration tests should verify inline vector path.
