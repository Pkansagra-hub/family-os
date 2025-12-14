# P02: Data Schema Design Specification

**Status**: ✅ Step 2.1 - Data Design Complete
**Version**: 0.1.0
**Last Updated**: 2025-11-15
**Owner**: Architecture Team

---

## Overview

This document specifies the **data schema design** for P02 (Episodic Memory Formation Pipeline). It defines three new tables:

1. **`st_hipp_events`** (NEW) — Hippocampus staging for enriched memory events
2. **`st_embedding_queue`** (NEW) — Job queue for P08 vector generation
3. **`st_relationships`** (RESTORED) — Family graph cache (undeprecate from migration 0021)

This schema enables P02 to:
- Store enriched hippocampus events with fingerprints + metadata
- Queue embedding jobs for P08 processing
- Support social graph lookups for family relationships
- Enable P03 to perform global consolidation + clustering

---

## Design Principles

### 1. **One-Way Flow (P02 → Storage)**
- P02 **inserts only** into `st_hipp_events` and `st_embedding_queue`
- P03 **mutates** dedup/cluster columns in `st_hipp_events`
- No circular dependencies or back-writes

### 2. **Denormalization for Performance**
- Store derived fields (e.g., `simhash_hex`, `minhash32`) directly in `st_hipp_events`
- Use JSON columns for flexible structures (entities, KG triples, reasons)
- Pre-compute timestamps and local time fields at write time

### 3. **Traceability & Observability**
- Every row linked to `wal_pos` for auditability
- Include `cognitive_trace_id` for end-to-end tracing
- Store policy decisions and obligations for compliance audit

### 4. **Null-Safe Dedup/Cluster Columns**
- P02 writes: `novelty_score = NULL`, `episode_cluster_id = NULL`
- P03 updates these after global analysis
- Queries can distinguish "not yet clustered" from "analyzed as singleton"

---

## Table 1: `st_hipp_events` — Hippocampus Staging

### Purpose

Primary storage for P02 enriched events. P03 reads from here for consolidation.

**Query Pattern**: Point lookups by `event_id`, range scans by `(space_id, event_time_utc)`, fingerprint queries for novelty

### Column Groups

#### Identity & Trace (9 columns)
```sql
event_id TEXT PRIMARY KEY,          -- UUID, unique event identifier
wal_pos INTEGER NOT NULL,           -- Foreign key to st_wal(wal_pos)
cognitive_trace_id TEXT NOT NULL,   -- End-to-end trace ID
tenant_id TEXT NOT NULL,            -- Tenant identifier
space_id TEXT NOT NULL,             -- Space identifier (e.g., 'personal:dad')
effective_space_id TEXT,            -- Actual space if redirected (optional)
topic TEXT NOT NULL,                -- Event topic (e.g., 'memory.episodic.formation')
uow_id TEXT,                        -- UnitOfWork ID from P02 transaction
schema_version TEXT DEFAULT '1.0.0' -- Schema version for forward compatibility
```

#### Integrity & Audit (6 columns)
```sql
envelope_sha256 TEXT NOT NULL,      -- Hash of original envelope (audit trail)
sig_alg TEXT NOT NULL,              -- Signature algorithm (e.g., 'ECDSA_P256_SHA256')
sig_kid TEXT NOT NULL,              -- Signature key ID
idem_key TEXT NOT NULL,             -- Idempotency key from hot path
ingested_at INTEGER NOT NULL,       -- Unix ts when envelope hit K0 ingress
clock_skew_ms INTEGER               -- Clock skew between device and K0
```

#### Policy & Visibility (10 columns)

**Semantics**:
- `visible_to_json` = **final explicit subject list** after PEP + SpaceResolver (actual ACL)
- `visibility_scope` = **high-level pattern** describing how list relates to space defaults

```sql
policy_decision TEXT NOT NULL,      -- 'ALLOW' | 'DENY' (only ALLOW in P02)
policy_band TEXT NOT NULL,          -- 'GREEN' | 'AMBER' | 'RED'
policy_version TEXT NOT NULL,       -- Policy version applied (e.g., '2025-11-01')
obligations_json TEXT,              -- JSON array: ["mask.location.precision", ...]
visible_to_json TEXT,               -- JSON array: effective principals after PEP + space resolution ["person_dad", "person_mom"]
visibility_scope TEXT,              -- High-level pattern: 'OWNER_ONLY' | 'SPACE_DEFAULT' | 'HOUSEHOLD_ALL' | 'CUSTOM_SUBSET' | 'EXTERNAL_SHARE'
owner_id TEXT NOT NULL,             -- Primary space owner
co_owners_json TEXT,                -- JSON array of co-owner IDs
retention_policy_id TEXT NOT NULL,  -- Foreign key to st_retention_policy
retention_bucket TEXT NOT NULL      -- 'STANDARD' | 'SENSITIVE' | 'EPHEMERAL'
```

#### Actor & Device (6 columns)
```sql
actor_id TEXT NOT NULL,             -- Actor (person) who created the event
actor_role TEXT,                    -- Semantic actor role ('SELF' | 'AGENT' | 'SYSTEM' | 'DELEGATE')
device_id TEXT NOT NULL,            -- Device that created event
device_kind TEXT NOT NULL,          -- 'phone' | 'web' | 'voice' | etc.
device_os TEXT,                     -- 'iOS' | 'Android' | 'Web' | etc.
ingress_channel TEXT                -- Coarse medium ('conversation' | 'form' | 'api' | 'sensor')
```

#### Temporal (11 columns)
```sql
event_time_utc INTEGER NOT NULL,    -- Unix ts when event occurred (from body or envelope)
write_time_utc INTEGER NOT NULL,    -- Unix ts when P02 committed to DB
write_lag_ms INTEGER,               -- Milliseconds from event_time to write_time
local_date TEXT,                    -- YYYY-MM-DD in tenant timezone
local_time TEXT,                    -- HH:MM:SS in tenant timezone
day_of_week TEXT,                   -- 'monday' | 'tuesday' | ... | 'sunday'
is_weekend BOOLEAN,                 -- True if Saturday or Sunday
time_of_day_bucket TEXT,            -- 'morning' | 'afternoon' | 'evening' | 'night'
circadian_slot TEXT,                -- 'breakfast' | 'lunch' | 'dinner' | 'sleep' | etc.
is_backdated BOOLEAN,               -- True if write_lag_ms > 24h
created_at INTEGER NOT NULL         -- Row creation timestamp (P02 UnitOfWork start)
```

#### Spatial & Place (5 columns)
```sql
location_name TEXT,                 -- Place name (e.g., 'Olive Garden, Market St')
location_type TEXT,                 -- 'restaurant' | 'home' | 'work' | 'other'
geohash_6 TEXT,                     -- Truncated geohash from WAL (typically 5-7 chars; name 'geohash_6' kept for legacy)
geo_precision_external TEXT,        -- Band-based precision (from policy obligations)
geo_masking_reason TEXT             -- Obligation name (e.g., 'mask.location.precision')
```

#### Social & Relationships (7 columns)
```sql
participants_json TEXT,             -- JSON array of participant IDs
num_participants INTEGER,           -- Count of participants
has_partner_present BOOLEAN,        -- True if spouse/partner in participants
has_parent_present BOOLEAN,         -- True if parent/elder in participants
is_solo_event BOOLEAN,              -- True if only actor present
participant_roles_json TEXT,        -- JSON: {"person_id": "ROLE", ...}
social_context TEXT,                -- 'nuclear_family' | 'extended_family' | 'friends' | 'work'
social_intimacy TEXT                -- 'LOW' | 'MED' | 'HIGH'
```

#### Semantic & Activity (9 columns)
```sql
text TEXT,                          -- Full event text
text_normalized TEXT,               -- Lowercased, whitespace normalized
char_count INTEGER,                 -- Character count of text
token_count INTEGER,                -- Approximate token count (for billing/metrics)
language TEXT,                      -- 'en' | 'es' | 'fr' | etc. (from envelope or detected)
activity_type TEXT,                 -- 'dinner' | 'meeting' | 'exercise' | etc.
activity_category TEXT,             -- 'social' | 'work' | 'health' | etc.
is_meal BOOLEAN,                    -- True if activity involves eating/dining
is_outing BOOLEAN                   -- True if outside home/workplace
ingress_source TEXT                 -- Concrete origin ('k1.conversation' | 'web.form' | 'api.direct' | 'calendar.sync')
```

#### Hippocampus: Pattern Separation & Novelty (8 columns)
```sql
simhash_hex TEXT NOT NULL,          -- 64-bit SimHash (hex format)
minhash32 TEXT NOT NULL,            -- MinHash signatures JSON (32 permutations)
novelty_score REAL,                 -- NULL in P02, populated by P03 (0-1 scale)
near_duplicates_json TEXT,          -- NULL in P02, populated by P03
is_near_duplicate BOOLEAN,          -- NULL in P02, populated by P03
episode_cluster_id TEXT,            -- NULL in P02, populated by P03
cluster_confidence REAL,            -- NULL in P02, populated by P03 (0-1 scale)
clustering_version TEXT             -- Version of clustering algorithm used (P03)
```

#### Embeddings & Knowledge Graph (4 columns)
```sql
embedding_id TEXT NOT NULL,         -- UUID; 1:1 join key with st_embedding_queue.embedding_id
                                    -- FK ENFORCED: P02 must insert st_hipp_events before st_embedding_queue in same transaction
embedding_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(embedding_status IN ('PENDING','IN_PROGRESS','READY','FAILED')),
entities_json TEXT,                 -- JSON: extracted named entities (people, places, orgs)
kg_triples_json TEXT                -- JSON: knowledge graph triples [(subject, predicate, object), ...]
```

#### Affect & Salience (9 columns)
```sql
sentiment_score REAL,               -- 0-1 scale, negative to positive
sentiment_label TEXT,               -- 'negative' | 'neutral' | 'positive'
dominant_emotions_json TEXT,        -- JSON: ["joy", "contentment", ...]
affect_valence REAL,                -- 0-1, negative to positive (from AffectService)
affect_arousal REAL,                -- 0-1, calm to excited (from AffectService)
affect_band TEXT CHECK(affect_band IN ('GREEN','AMBER','RED')), -- Risk level
salience_score REAL NOT NULL,       -- 0-1, importance to actor (default 0.0 if AffectService fails)
salience_reasons_json TEXT,         -- JSON: ["social_family", "positive_affect", ...]
salience_band TEXT CHECK(salience_band IN ('HIGH','MED','LOW'))  -- Importance tier
```

#### Metadata & Versioning (4 columns)
```sql
hippocampus_api_version TEXT,       -- Version of hippocampus module used
space_resolver_version TEXT,        -- Version of space resolver used
schema_uri TEXT,                    -- Schema contract URI (persisted for convenience; can also be retrieved from st_wal)
updated_at INTEGER NOT NULL         -- Row last update timestamp
```

### Indexes

```sql
PRIMARY KEY (event_id)
FOREIGN KEY (wal_pos) REFERENCES st_wal(wal_pos)

-- Query by tenant + time (common range scan for retention/analytics)
CREATE INDEX idx_hipp_events_tenant_time
  ON st_hipp_events(tenant_id, event_time_utc DESC);

-- Query by space + time (P03 consolidation per-space)
CREATE INDEX idx_hipp_events_space_time
  ON st_hipp_events(space_id, event_time_utc DESC);

-- Fingerprint queries for P03 novelty detection
CREATE INDEX idx_hipp_events_simhash
  ON st_hipp_events(simhash_hex);

-- Embedding job tracking
CREATE INDEX idx_hipp_events_embedding_id
  ON st_hipp_events(embedding_id);

-- Policy band filtering (for retention workers)
CREATE INDEX idx_hipp_events_band_time
  ON st_hipp_events(policy_band, event_time_utc DESC);

-- Cluster lookups (P03 may query by cluster_id)
CREATE INDEX idx_hipp_events_cluster_id
  ON st_hipp_events(episode_cluster_id) WHERE episode_cluster_id IS NOT NULL;
```

### Insert Rate & Capacity

**Realistic Load** (human-scale per household):

- **Average**: 50–150 hippo events/day per active adult user
- **Household** (3–4 people): 150–500 events/day
- **Sustained rate**: ~0.002–0.006 inserts/sec per household
- **Burst**: up to 1–5 inserts/sec during heavy conversations or automation bursts

**Capacity Target** (for stress tests / safety margin):

- Design K0/P02 to **handle 100–1000 events/sec** as an upper bound, but this represents *headroom*, not expected normal load.

**Estimated Size**:

- **Per-row size**: ~2-3 KB (with JSON payloads)
- **Retention**: 90 days (configurable per policy)
- **Lifetime per person**: ~3.6M memories over 50 years (at 200/day) ⇒ ~7–10 GB per user of hippo events, pre-retention

---

## Table 2: `st_embedding_queue` — P08 Vector Generation Job Queue

### Purpose
Queue for P08 vector generation. P02 enqueues, P08 processes with retry logic.

**Insert Rate**: Same as P02 (~100-1000 jobs/sec)
**Query Pattern**: Poll by `(status, next_attempt_ts)`, lookup by `job_id` or `event_id`

### Schema

```sql
CREATE TABLE st_embedding_queue (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Linkage to event and WAL
  wal_pos INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  embedding_id TEXT NOT NULL UNIQUE,

  -- Tenant/space context
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Job configuration
  vector_kind TEXT NOT NULL,        -- 'memory.body.text' | 'memory.entities' | etc.
  model_id TEXT NOT NULL,           -- 'embed-mini-001' | 'embed-large-001' | etc.
  priority TEXT NOT NULL DEFAULT 'NORMAL',  -- 'HIGH' | 'NORMAL' | 'LOW'

  -- Execution state
  status TEXT NOT NULL CHECK(status IN (
    'PENDING',
    'IN_PROGRESS',
    'READY',
    'FAILED_RETRYABLE',
    'FAILED_PERMANENT'
  )),

  -- Retry tracking
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_ts INTEGER,         -- Unix ts when next attempt should occur
  last_error TEXT,                 -- Error message from last failed attempt

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  -- Foreign keys
  FOREIGN KEY (wal_pos) REFERENCES st_wal(wal_pos),
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);
```

### Indexes

```sql
-- P08 polls this index to find retryable jobs
CREATE INDEX idx_embedding_queue_status_time
  ON st_embedding_queue(status, next_attempt_ts);

-- Lookup by event (P03 may query for embedding status)
CREATE INDEX idx_embedding_queue_event_id
  ON st_embedding_queue(event_id);

-- Lookup by embedding (vector store may query)
CREATE INDEX idx_embedding_queue_embedding_id
  ON st_embedding_queue(embedding_id);

-- Cleanup: find old READY jobs (after vector stored, mark for archival)
CREATE INDEX idx_embedding_queue_status_created
  ON st_embedding_queue(status, created_at)
  WHERE status = 'READY';
```

### Retry Logic

**Exponential Backoff Algorithm**:

`attempt_count` starts at **0** on insert. After each failure, increment `attempt_count`:

```
attempt_count=0 (initial): next_attempt_ts = now (immediate insert)
attempt_count=1 (after 1st retry): next_attempt_ts = now + 60s
attempt_count=2 (after 2nd retry): next_attempt_ts = now + 120s (2^1 × 60)
attempt_count=3 (after 3rd retry): next_attempt_ts = now + 240s (2^2 × 60)
attempt_count=4 (after 4th retry): next_attempt_ts = now + 480s (2^3 × 60)
attempt_count >= max_attempts (5): status = 'FAILED_PERMANENT' (move to DLQ, stop scheduling)
```

**Formula**: `next_attempt_ts = now + (2^(attempt_count - 1) × 60 seconds)`

**P08 Polling Logic**:
```sql
SELECT * FROM st_embedding_queue
WHERE status IN ('PENDING', 'FAILED_RETRYABLE')
  AND next_attempt_ts <= strftime('%s','now')
ORDER BY priority DESC, next_attempt_ts ASC
LIMIT 100;  -- Process in batches
```

---

## Table 3: `st_relationships` — Family Graph Cache (RESTORED)

### Purpose
Cache of family relationships replicated from Neo4j. Enables P02 to resolve family roles without graph traversal.

**Lifecycle**:
- Created in migration 0017
- Seeded in migration 0018
- Deprecated in migration 0021 (dropped)
- **Restored in migration 0024** (recreated with fresh seed, relationship types expanded)

### Schema

```sql
CREATE TABLE st_relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Relationship identity
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  related_person_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL CHECK(relationship_type IN (
    'SPOUSE_OF',
    'PARENT_OF',
    'CHILD_OF',       -- Added in 0024 extension
    'CARETAKER_OF',
    'SIBLING_OF'      -- Added in 0024 extension
  )),

  -- Metadata
  properties_json TEXT,             -- e.g., '{"delegated_by": "person_prince_001"}'
  source_version TEXT NOT NULL,     -- 'migration_0018' | 'neo4j_sync_v1.2' | etc.
  hydrated_at TEXT NOT NULL,        -- ISO timestamp when cached
  ttl_seconds INTEGER NOT NULL,     -- Cache TTL (3600 = 1 hour typical)

  -- Foreign keys
  FOREIGN KEY (household_id) REFERENCES households(household_id),
  FOREIGN KEY (person_id) REFERENCES people(person_id),
  FOREIGN KEY (related_person_id) REFERENCES people(person_id)
);
```

### Indexes

```sql
-- Lookup by household (seed data load, cache refresh)
CREATE INDEX idx_relationships_household
  ON st_relationships(household_id);

-- Lookup by person (P02 resolves "is person_mom my partner?")
CREATE INDEX idx_relationships_person
  ON st_relationships(person_id);

-- Lookup by relationship type (analytics, reports)
CREATE INDEX idx_relationships_type
  ON st_relationships(relationship_type);

-- Compound: (person_id, relationship_type) for role resolution
CREATE INDEX idx_relationships_person_type
  ON st_relationships(person_id, relationship_type);
```

### Seed Data (from migration 0018)

**Family Structure**:
- Prince (person_prince_001)
- Jeel (person_jeel_001)
- Sharvi (person_sharvi_001)
- Grandparents (implied ancestors)

**Relationships**:
```
SPOUSE_OF: Prince ↔ Jeel
PARENT_OF: Prince → Sharvi
PARENT_OF: Jeel → Sharvi
CARETAKER_OF: Grandparents → Sharvi (optional)
```

### Cache Refresh Strategy

**Manual Refresh** (for migration 0024):
- Drop and recreate table
- Re-seed from migration 0018 data
- Verify row count matches expectations

**Ongoing Refresh** (future work, not in P02 scope):
- External sync worker periodically updates from Neo4j
- Stale cache entries expire after `ttl_seconds`
- On TTL expiry, queries fall back to Neo4j

---

## Data Consistency & Transactions

### P02 UnitOfWork Atomicity

P02 must ensure all three writes succeed together or all fail:

```python
# Pseudocode
async def commit_p02_write(self, hippocampus_event, embedding_job):
    """Atomic write of hippo event + embedding job + offset tracking"""
    # Note: policy_decision, policy_band, policy_version, owner_id, retention_policy_id,
    #       embedding_id, embedding_status are all NOT NULL (resolved before insert)
    async with self.db.transaction() as tx:
        # Insert to st_hipp_events
        await tx.execute(
            INSERT INTO st_hipp_events (...) VALUES (...),
            hippocampus_event
        )

        # Insert to st_embedding_queue
        await tx.execute(
            INSERT INTO st_embedding_queue (...) VALUES (...),
            embedding_job
        )

        # Record offset for P02 idempotency
        await tx.execute(
            INSERT OR REPLACE INTO st_pipeline_processed (pipeline_id, space_id, wal_pos, offset_ts)
            VALUES ('P02_EPISODIC_WRITE', space_id, wal_pos, strftime('%s','now')),
            (pipeline_id, space_id, wal_pos)
        )

        # All or nothing
        await tx.commit()
```

### P03 Update Strategy

P03 reads `st_hipp_events` and updates in-place:

```python
# P03 pseudocode
async def update_dedup_columns(self, event_id, novelty_score, cluster_id):
    """P03 updates dedup/cluster columns in st_hipp_events"""
    async with self.db.transaction() as tx:
        await tx.execute(
            UPDATE st_hipp_events
            SET novelty_score = ?,
                is_near_duplicate = ?,
                episode_cluster_id = ?,
                cluster_confidence = ?,
                clustering_version = ?
            WHERE event_id = ?  -- event_id is PK; LIMIT 1 unnecessary
        )
        await tx.commit()
```

---

## Performance Considerations

### Write Optimization
- Use batch inserts (128 events at a time from P02)
- Insert JSON columns as TEXT (no parsing/validation at DB layer)
- Rely on application-level validation

### Query Optimization
- Index on `(space_id, event_time_utc DESC)` for retention queries
- Index on `simhash_hex` for P03 novelty lookups (pre-computed, no hashing at query time)
- Index on `(policy_band, event_time_utc DESC)` for band-based policies

### Partitioning (Future)
- Partition `st_hipp_events` by `(tenant_id, event_time_utc)` for large scale
- Partition `st_embedding_queue` by `(status, created_at)` for old job cleanup

---

## Backward Compatibility & Evolution

### Schema Versioning
- Add `schema_version` column to `st_hipp_events` for future changes
- P02 writes current version; P03 reads and handles upgrades

### JSON Column Stability
- JSON payloads use consistent key names (no aliasing)
- New fields added as optional (backward-compatible)
- Old fields never removed (only marked deprecated)

### Migration Path
- Always create new tables alongside old ones during transition
- Use triggers or dual-write if overlapping period required
- Archive old tables after verification

---

## Related Documents

- **P02 Write Dossier**: `docs/pipelines/P02_write_dossier.md` (architecture + responsibilities)
- **Contract Spec**: `k0/contracts/pipelines/P02_tables_schema.yaml` (formal schema contract)
- **Migrations**: `k0/contracts/sql/migrations/0024_p02_episodic_write_tables.sql`
- **Master Architecture**: `k0/pipelines/k0_architecture_master.md` (Part 5.3)

---

**End of Data Schema Design Specification**
