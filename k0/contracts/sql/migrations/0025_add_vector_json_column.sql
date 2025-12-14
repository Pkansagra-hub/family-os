-- ========================================================================================
-- Migration 0025: Add vector_json column to st_embedding_queue
-- ========================================================================================
-- Created: 2025-11-20
-- Purpose: Add vector_json column to store computed embeddings before FAISS indexing
-- Related: k0/drivers/embedding_queue.py, k0/drivers/faiss.py
-- ========================================================================================
-- Impact:
--   - st_embedding_queue gains vector_json TEXT column (nullable)
--   - Allows embedding worker to store results before FAISS indexing
--   - status='READY' indicates vector_json is populated
--   - status='INDEXED' added (set by FAISS driver after indexing)
-- ========================================================================================

BEGIN;

-- Add vector_json column to st_embedding_queue
ALTER TABLE st_embedding_queue ADD COLUMN vector_json TEXT;

-- Update CHECK constraint for status to include 'INDEXED'
-- Note: SQLite doesn't support modifying CHECK constraints directly
-- We need to recreate the table (standard SQLite pattern)

-- Create backup table
CREATE TABLE st_embedding_queue_backup AS SELECT * FROM st_embedding_queue;

-- Drop original table
DROP TABLE st_embedding_queue;

-- Recreate table with updated status CHECK constraint
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
  vector_kind TEXT NOT NULL,
  model_id TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ('HIGH', 'NORMAL', 'LOW')),

  -- Execution state
  status TEXT NOT NULL CHECK(status IN ('PENDING', 'IN_PROGRESS', 'READY', 'INDEXED', 'FAILED_RETRYABLE', 'FAILED_PERMANENT')),

  -- Retry tracking
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_ts INTEGER,
  last_error TEXT,

  -- Vector storage (populated when status='READY')
  vector_json TEXT,

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  -- Foreign keys
  FOREIGN KEY (wal_pos) REFERENCES st_wal(pos),
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id),
  FOREIGN KEY (embedding_id) REFERENCES st_hipp_events(embedding_id)
);

-- Restore data from backup
INSERT INTO st_embedding_queue (
  job_id, wal_pos, event_id, embedding_id, tenant_id, space_id,
  vector_kind, model_id, priority, status, attempt_count, max_attempts,
  next_attempt_ts, last_error, vector_json, created_at, updated_at
)
SELECT
  job_id, wal_pos, event_id, embedding_id, tenant_id, space_id,
  vector_kind, model_id, priority, status, attempt_count, max_attempts,
  next_attempt_ts, last_error, NULL as vector_json, created_at, updated_at
FROM st_embedding_queue_backup;

-- Drop backup table
DROP TABLE st_embedding_queue_backup;

-- Recreate indexes
CREATE INDEX idx_embedding_queue_status_time ON st_embedding_queue(status, next_attempt_ts);
CREATE INDEX idx_embedding_queue_event_id ON st_embedding_queue(event_id);
CREATE INDEX idx_embedding_queue_embedding_id ON st_embedding_queue(embedding_id);
CREATE INDEX idx_embedding_queue_status_created ON st_embedding_queue(status, created_at) WHERE status IN ('READY', 'INDEXED');

COMMIT;

-- ========================================================================================
-- Migration Notes
-- ========================================================================================
-- 1. vector_json column stores serialized embedding vector (JSON array of floats)
-- 2. Status flow: PENDING → IN_PROGRESS → READY → INDEXED
--    - READY: vector_json populated, ready for FAISS indexing
--    - INDEXED: FAISS indexing complete, can be archived/deleted
-- 3. Updated status CHECK constraint to include 'INDEXED' state
-- 4. Updated conditional index to include both 'READY' and 'INDEXED' statuses

-- ========================================================================================
-- Post-Migration Verification Checklist
-- ========================================================================================
-- [ ] Run: PRAGMA table_info(st_embedding_queue);
-- [ ] Verify: vector_json column exists (type TEXT, nullable)
-- [ ] Run: SELECT sql FROM sqlite_master WHERE type='table' AND name='st_embedding_queue';
-- [ ] Verify: status CHECK constraint includes 'INDEXED'
-- [ ] Run: SELECT COUNT(*) FROM st_embedding_queue;
-- [ ] Verify: All existing rows preserved (vector_json will be NULL)
-- [ ] Run: PRAGMA integrity_check;
-- [ ] Verify: Result should be "ok"

-- ========================================================================================
-- Rollback Strategy (if needed)
-- ========================================================================================
-- Manual rollback (recreate table without vector_json column):
--   DROP TABLE st_embedding_queue;
--   -- Re-run migration 0024 to restore original schema
