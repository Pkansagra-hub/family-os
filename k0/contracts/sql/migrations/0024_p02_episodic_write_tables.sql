-- ========================================================================================
-- Migration 0024: P02 Episodic Memory Formation Pipeline Tables
-- ========================================================================================
-- Created: 2025-11-15
-- Purpose: Create three new tables for P02 episodic memory enrichment pipeline
-- Architecture: P02 background processing writes enriched hippocampus events, embedding jobs,
--              and family relationship cache for downstream pipelines (P03, P04, P08)
-- Related: docs/pipelines/P02_write_dossier.md, docs/pipelines/P02_data_schema.md,
--          k0/contracts/pipelines/P02_tables_schema.yaml
-- ========================================================================================
-- Impact:
--   - 3 NEW tables created: st_hipp_events (70+ cols), st_embedding_queue (12 cols), st_relationships (9 cols)
--   - P02 inserts episodic memories with DG fingerprints, affect analysis, space resolution
--   - P03 reads st_hipp_events for novelty-based consolidation (dedup/clustering)
--   - P08 processes st_embedding_queue for vector generation
--   - st_relationships restored (undeprecated from 0021), with extended relationship types
--   - 90-day retention policy, ~2-3 KB per row, ~100-300 GB/month at stress load
-- ========================================================================================

BEGIN;

PRAGMA foreign_keys=OFF;

-- ========================================================================================
-- Table 1: st_hipp_events (NEW) - Hippocampus Staging for P02 Enriched Events
-- ========================================================================================
-- Purpose: Primary storage for P02 enriched events with pattern separation fingerprints.
--          P03 reads from here for consolidation & clustering.
-- Columns: 70+ (Identity, Integrity, Policy, Actor, Temporal, Spatial, Social, Semantic,
--          Hippocampus, Embeddings, Affect, Metadata)
-- Indexes: 6 (time-based, fingerprints, embeddings, clusters)
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_hipp_events (
  -- Identity & Trace (9 columns)
  event_id TEXT PRIMARY KEY,
  wal_pos INTEGER NOT NULL UNIQUE,
  cognitive_trace_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  effective_space_id TEXT,
  topic TEXT NOT NULL,
  uow_id TEXT,
  schema_version TEXT NOT NULL DEFAULT '1.0.0',

  -- Integrity & Audit (6 columns)
  envelope_sha256 TEXT NOT NULL,
  sig_alg TEXT NOT NULL,
  sig_kid TEXT NOT NULL,
  idem_key TEXT NOT NULL,
  ingested_at INTEGER NOT NULL,
  clock_skew_ms INTEGER,

  -- Policy & Visibility (10 columns)
  policy_decision TEXT NOT NULL CHECK(policy_decision IN ('ALLOW', 'DENY')),
  policy_band TEXT NOT NULL CHECK(policy_band IN ('GREEN', 'AMBER', 'RED')),
  policy_version TEXT NOT NULL,
  obligations_json TEXT,
  visible_to_json TEXT,
  visibility_scope TEXT CHECK(visibility_scope IN ('OWNER_ONLY', 'SPACE_DEFAULT', 'HOUSEHOLD_ALL', 'CUSTOM_SUBSET', 'EXTERNAL_SHARE')),
  owner_id TEXT NOT NULL,
  co_owners_json TEXT,
  retention_policy_id TEXT NOT NULL,
  retention_bucket TEXT NOT NULL CHECK(retention_bucket IN ('STANDARD', 'SENSITIVE', 'EPHEMERAL')),

  -- Actor & Device (6 columns)
  actor_id TEXT NOT NULL,
  actor_role TEXT CHECK(actor_role IN ('SELF', 'AGENT', 'SYSTEM', 'DELEGATE')),
  device_id TEXT NOT NULL,
  device_kind TEXT NOT NULL,
  device_os TEXT,
  ingress_channel TEXT,

  -- Temporal (11 columns)
  event_time_utc INTEGER NOT NULL,
  write_time_utc INTEGER NOT NULL,
  write_lag_ms INTEGER,
  local_date TEXT,
  local_time TEXT,
  day_of_week TEXT,
  is_weekend BOOLEAN,
  time_of_day_bucket TEXT,
  circadian_slot TEXT,
  is_backdated BOOLEAN,
  created_at INTEGER NOT NULL,

  -- Spatial & Place (5 columns)
  location_name TEXT,
  location_type TEXT,
  geohash_6 TEXT,
  geo_precision_external TEXT,
  geo_masking_reason TEXT,

  -- Social & Relationships (8 columns)
  participants_json TEXT,
  num_participants INTEGER,
  has_partner_present BOOLEAN,
  has_parent_present BOOLEAN,
  is_solo_event BOOLEAN,
  participant_roles_json TEXT,
  social_context TEXT,
  social_intimacy TEXT,

  -- Semantic & Activity (10 columns)
  text TEXT,
  text_normalized TEXT,
  char_count INTEGER,
  token_count INTEGER,
  language TEXT,
  activity_type TEXT,
  activity_category TEXT,
  is_meal BOOLEAN,
  is_outing BOOLEAN,
  ingress_source TEXT,

  -- Hippocampus: Pattern Separation & Novelty (8 columns)
  simhash_hex TEXT NOT NULL,
  minhash32 TEXT NOT NULL,
  novelty_score REAL,
  near_duplicates_json TEXT,
  is_near_duplicate BOOLEAN,
  episode_cluster_id TEXT,
  cluster_confidence REAL,
  clustering_version TEXT,

  -- Embeddings & Knowledge Graph (4 columns)
  embedding_id TEXT NOT NULL UNIQUE,
  embedding_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(embedding_status IN ('PENDING', 'IN_PROGRESS', 'READY', 'FAILED')),
  entities_json TEXT,
  kg_triples_json TEXT,

  -- Affect & Salience (9 columns)
  sentiment_score REAL,
  sentiment_label TEXT,
  dominant_emotions_json TEXT,
  affect_valence REAL,
  affect_arousal REAL,
  affect_band TEXT CHECK(affect_band IN ('GREEN', 'AMBER', 'RED')),
  salience_score REAL NOT NULL DEFAULT 0.0,
  salience_reasons_json TEXT,
  salience_band TEXT CHECK(salience_band IN ('HIGH', 'MED', 'LOW')),

  -- Metadata & Versioning (4 columns)
  hippocampus_api_version TEXT,
  space_resolver_version TEXT,
  schema_uri TEXT,                    -- Schema contract URI (persisted for convenience; can also be retrieved from st_wal)
  updated_at INTEGER NOT NULL,

  -- Foreign Keys
  FOREIGN KEY (wal_pos) REFERENCES st_wal(wal_pos),
  FOREIGN KEY (retention_policy_id) REFERENCES st_retention_policy(policy_id)
);

-- Indexes for st_hipp_events
CREATE INDEX idx_hipp_events_tenant_time ON st_hipp_events(tenant_id, event_time_utc DESC);
CREATE INDEX idx_hipp_events_space_time ON st_hipp_events(space_id, event_time_utc DESC);
CREATE INDEX idx_hipp_events_simhash ON st_hipp_events(simhash_hex);
CREATE INDEX idx_hipp_events_embedding_id ON st_hipp_events(embedding_id);
CREATE INDEX idx_hipp_events_band_time ON st_hipp_events(policy_band, event_time_utc DESC);
CREATE INDEX idx_hipp_events_cluster_id ON st_hipp_events(episode_cluster_id) WHERE episode_cluster_id IS NOT NULL;

-- ========================================================================================
-- Table 2: st_embedding_queue (NEW) - P08 Vector Generation Job Queue
-- ========================================================================================
-- Purpose: Queue for P08 vector generation with exponential backoff retry logic.
--          P02 enqueues, P08 processes with configurable attempt limits.
-- Columns: 16 (Linkage, Context, Job Config, Execution State, Retry Tracking, Timestamps)
-- Indexes: 4 (Status polling, Event lookup, Cleanup)
-- Retry:   Exponential backoff: attempt_count=0,1,2,3,4 → 0s, +60s, +120s, +240s, +480s
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_embedding_queue (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Linkage to event and WAL
  wal_pos INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  embedding_id TEXT NOT NULL UNIQUE,

  -- Tenant/space context
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Job configuration
  vector_kind TEXT NOT NULL,
  model_id TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ('HIGH', 'NORMAL', 'LOW')),

  -- Execution state
  status TEXT NOT NULL CHECK(status IN ('PENDING', 'IN_PROGRESS', 'READY', 'FAILED_RETRYABLE', 'FAILED_PERMANENT')),

  -- Retry tracking
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_ts INTEGER,
  last_error TEXT,

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  -- Foreign keys
  FOREIGN KEY (wal_pos) REFERENCES st_wal(wal_pos),
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id),
  FOREIGN KEY (embedding_id) REFERENCES st_hipp_events(embedding_id)
);

-- Indexes for st_embedding_queue
CREATE INDEX idx_embedding_queue_status_time ON st_embedding_queue(status, next_attempt_ts);
CREATE INDEX idx_embedding_queue_event_id ON st_embedding_queue(event_id);
CREATE INDEX idx_embedding_queue_embedding_id ON st_embedding_queue(embedding_id);
CREATE INDEX idx_embedding_queue_status_created ON st_embedding_queue(status, created_at) WHERE status = 'READY';

-- ========================================================================================
-- Table 3: st_relationships (RESTORED) - Family Graph Cache
-- ========================================================================================
-- Purpose: Cache of family relationships from Neo4j. Enables P02 to resolve family roles
--          without graph traversal. Originally created in 0017, seeded in 0018, deprecated
--          in 0021, now restored in 0024 with extended relationship types (5 types).
-- Columns: 9 (Identity, Type, Metadata)
-- Indexes: 4 (Household, Person, Type, Compound lookups)
-- Seed:    From migration 0018 (Prince↔Jeel, Prince→Sharvi, Jeel→Sharvi, Grandparents→Sharvi)
-- Types:   SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF (extended in 0024)
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Relationship identity
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  related_person_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL CHECK(relationship_type IN ('SPOUSE_OF', 'PARENT_OF', 'CHILD_OF', 'CARETAKER_OF', 'SIBLING_OF')),

  -- Metadata
  properties_json TEXT,
  source_version TEXT NOT NULL,
  hydrated_at TEXT NOT NULL,
  ttl_seconds INTEGER NOT NULL,

  -- Foreign keys
  FOREIGN KEY (household_id) REFERENCES households(household_id),
  FOREIGN KEY (person_id) REFERENCES people(person_id),
  FOREIGN KEY (related_person_id) REFERENCES people(person_id)
);

-- Indexes for st_relationships
CREATE INDEX idx_relationships_household ON st_relationships(household_id);
CREATE INDEX idx_relationships_person ON st_relationships(person_id);
CREATE INDEX idx_relationships_type ON st_relationships(relationship_type);
CREATE INDEX idx_relationships_person_type ON st_relationships(person_id, relationship_type);

-- ========================================================================================
-- Seed st_relationships with baseline data from migration 0018
-- ========================================================================================
-- Family: Prince (person_prince_001), Jeel (person_jeel_001), Sharvi (person_sharvi_001)
-- Relationships:
--   - Prince ↔ Jeel (SPOUSE_OF)
--   - Prince → Sharvi (PARENT_OF)
--   - Jeel → Sharvi (PARENT_OF)
--   - Grandparents → Sharvi (CARETAKER_OF, optional)
-- ========================================================================================

INSERT INTO st_relationships (household_id, person_id, related_person_id, relationship_type, source_version, hydrated_at, ttl_seconds)
VALUES
  ('household-prince-jeel', 'person_prince_001', 'person_jeel_001', 'SPOUSE_OF', 'migration_0018', datetime('now'), 3600),
  ('household-prince-jeel', 'person_jeel_001', 'person_prince_001', 'SPOUSE_OF', 'migration_0018', datetime('now'), 3600),
  ('household-prince-jeel', 'person_prince_001', 'person_sharvi_001', 'PARENT_OF', 'migration_0018', datetime('now'), 3600),
  ('household-prince-jeel', 'person_jeel_001', 'person_sharvi_001', 'PARENT_OF', 'migration_0018', datetime('now'), 3600);

PRAGMA foreign_keys=ON;

COMMIT;

-- ========================================================================================
-- Migration Notes
-- ========================================================================================
-- 1. st_hipp_events: 70+ columns designed for comprehensive episodic memory enrichment
--    - P02 inserts with all identity, policy, temporal, spatial, social, semantic data
--    - P03 updates novelty_score, cluster columns after global analysis
--    - 6 indexes cover tenant/space/time queries, fingerprints, embeddings, clusters
-- 2. st_embedding_queue: 12 columns for P08 vector job queue with exponential backoff
--    - Attempt count: 0-4 (max 5), backoff: 0s, +60s, +120s, +240s, +480s
--    - P08 polls WHERE status IN ('PENDING','FAILED_RETRYABLE') AND next_attempt_ts <= now()
--    - FAILED_PERMANENT jobs moved to DLQ (dead letter queue)
-- 3. st_relationships: Restored with 5 relationship types (SPOUSE_OF, PARENT_OF, CHILD_OF,
--    CARETAKER_OF, SIBLING_OF) - extended from original 3 in migration 0017
--    - Initial seed from 0018 (4 relationships for test family)
--    - TTL-based cache with Neo4j sync capability (future work)
-- 4. All nullable columns support NULL semantics per architecture decisions
-- 5. CHECK constraints enforce valid enum values at database level
-- 6. FOREIGN KEY references: wal_pos→st_wal, retention_policy_id→st_retention_policy,
--    household/person relationships to existing tables
-- 7. P02 atomic writes ensure all 3 inserts (st_hipp_events, st_embedding_queue, st_pipeline_processed) succeed or all fail

-- ========================================================================================
-- Post-Migration Verification Checklist
-- ========================================================================================
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='st_hipp_events';
-- [ ] Verify: Result should be 1
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='st_embedding_queue';
-- [ ] Verify: Result should be 1
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='st_relationships';
-- [ ] Verify: Result should be 1
-- [ ] Run: SELECT COUNT(*) FROM st_relationships;
-- [ ] Verify: Result should be 4 (baseline seed data)
-- [ ] Run: PRAGMA integrity_check;
-- [ ] Verify: Result should be "ok"
-- [ ] Run: SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='st_hipp_events';
-- [ ] Verify: 6 indexes returned (tenant_time, space_time, simhash, embedding_id, band_time, cluster_id)
-- [ ] Run: SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='st_embedding_queue';
-- [ ] Verify: 4 indexes returned (status_time, event_id, embedding_id, status_created)
-- [ ] Run: SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='st_relationships';
-- [ ] Verify: 4 indexes returned (household, person, type, person_type)
-- [ ] Restart kernel: ./k0.ps1 -Command restart
-- [ ] Verify: Kernel boots without errors
-- [ ] Run tests: pytest tests/ -v
-- [ ] Verify: All tests pass
-- [ ] Submit envelope: python k0/provision_and_submit.py
-- [ ] Verify: Envelope processed successfully and P02 pipeline operational

-- ========================================================================================
-- Rollback Strategy (if needed)
-- ========================================================================================
-- NOTE: This migration creates production tables. Rollback should be manual:
--   DROP TABLE IF EXISTS st_embedding_queue;
--   DROP TABLE IF EXISTS st_hipp_events;
--   DROP TABLE IF EXISTS st_relationships;
-- Ensure P02 pipeline is not running before rollback.
-- Data loss is permanent - no automatic recovery.
