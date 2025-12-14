-- Migration 0012: Pipeline Infrastructure Tables
-- Purpose: Add tables for pipeline idempotency, status tracking, and watermarks
-- Date: November 12, 2025
-- Related: M1 R1.2 - DDL Migrations for K0 Pipeline Architecture v1.3

BEGIN;

-- Note: st_wal.pos already exists as INTEGER PRIMARY KEY AUTOINCREMENT (monotonic)
-- Note: st_outbox.wal_pos already exists and references st_wal.pos
-- No ALTER TABLE needed for existing WAL/Outbox tables

-- ============================================================================
-- Table 1: Per-Space Pipeline Processing Ledger
-- ============================================================================
-- Purpose: Idempotency + per-space ordering enforcement
-- Usage: Before processing message, check if (pipeline_id, space_id, wal_pos) exists
-- Performance: O(1) lookup via composite PRIMARY KEY

CREATE TABLE IF NOT EXISTS st_pipeline_processed (
  pipeline_id  TEXT NOT NULL,     -- Pipeline identifier (e.g., "P02", "P03")
  space_id     TEXT NOT NULL,     -- Space ID (per-space ordering boundary)
  wal_pos      INTEGER NOT NULL,  -- References st_wal.pos (monotonic offset)
  processed_at INTEGER NOT NULL,  -- Unix timestamp (milliseconds since epoch)
  PRIMARY KEY (pipeline_id, space_id, wal_pos)
);

-- Index for efficient watermark queries (compaction support)
CREATE INDEX IF NOT EXISTS idx_pipeline_processed_space_wal
  ON st_pipeline_processed(space_id, wal_pos);

-- ============================================================================
-- Table 2: Queryable Pipeline Status (Receipts)
-- ============================================================================
-- Purpose: Per-message processing receipts for /status API queries
-- Usage: After processing, insert OK/ERROR/DEFERRED status with metrics
-- Performance: O(1) lookup via (pipeline_id, wal_pos) composite key

CREATE TABLE IF NOT EXISTS st_pipeline_status (
  pipeline_id  TEXT NOT NULL,     -- Pipeline identifier
  wal_pos      INTEGER NOT NULL,  -- References st_wal.pos
  status       TEXT NOT NULL      -- OK, ERROR, DEFERRED
    CHECK(status IN ('OK', 'ERROR', 'DEFERRED')),
  duration_ms  INTEGER,            -- Processing duration (milliseconds)
  error_kind   TEXT,               -- Error category (e.g., "SCHEMA_MISMATCH", "PERMISSION_DENIED")
  error_msg    TEXT,               -- Human-readable error message
  updated_at   INTEGER NOT NULL,  -- Unix timestamp (milliseconds)
  PRIMARY KEY (pipeline_id, wal_pos)
);

-- Index for efficient status queries (e.g., "get all errors for P02")
CREATE INDEX IF NOT EXISTS idx_pipeline_status_status
  ON st_pipeline_status(status);

-- Index for timestamp-based queries (recent status updates)
CREATE INDEX IF NOT EXISTS idx_pipeline_status_updated
  ON st_pipeline_status(updated_at);

-- ============================================================================
-- Table 3: Pipeline Watermark Ledger (Compaction Support)
-- ============================================================================
-- Purpose: Track max processed wal_pos per (pipeline, space) for compaction
-- Usage: Periodically compact st_pipeline_processed WHERE wal_pos < watermark
-- Performance: O(1) update via (pipeline_id, space_id) composite key

CREATE TABLE IF NOT EXISTS st_pipeline_watermarks (
  pipeline_id  TEXT NOT NULL,     -- Pipeline identifier
  space_id     TEXT NOT NULL,     -- Space ID
  watermark    INTEGER NOT NULL,  -- Max processed wal_pos before compaction
  updated_at   INTEGER NOT NULL,  -- Unix timestamp (milliseconds)
  PRIMARY KEY (pipeline_id, space_id)
);

-- Index for efficient compaction queries
CREATE INDEX IF NOT EXISTS idx_pipeline_watermarks_pipeline
  ON st_pipeline_watermarks(pipeline_id, watermark);

-- ============================================================================
-- Optional: Enhance st_dlq with Error Categorization
-- ============================================================================
-- Purpose: Add error_kind and error_fingerprint for better DLQ analysis
-- Note: st_dlq already has 'reason' field; error_kind provides categorization
-- Usage: error_fingerprint = SHA256(error_kind + payload_hash) for deduplication

-- Note: SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN
-- These statements will error on second run (expected behavior)
-- Idempotency handled by migration framework catching sqlite3.OperationalError

-- Add error_kind column (e.g., "SCHEMA_MISMATCH", "TIMEOUT", "PERMISSION_DENIED")
ALTER TABLE st_dlq ADD COLUMN error_kind TEXT;

-- Add error_fingerprint column (SHA256 hash for deduplication)
ALTER TABLE st_dlq ADD COLUMN error_fingerprint TEXT;

-- Index for deduplication queries (find similar errors)
CREATE INDEX IF NOT EXISTS idx_dlq_error_fingerprint
  ON st_dlq(error_fingerprint) WHERE error_fingerprint IS NOT NULL;

-- Index for error kind filtering (analytics/monitoring)
CREATE INDEX IF NOT EXISTS idx_dlq_error_kind
  ON st_dlq(error_kind) WHERE error_kind IS NOT NULL;

COMMIT;

-- ============================================================================
-- Migration Verification Queries (Run After Migration)
-- ============================================================================
-- 1. Verify tables created:
--    SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'st_pipeline%';
--    Expected: st_pipeline_processed, st_pipeline_status, st_pipeline_watermarks
--
-- 2. Verify indexes created:
--    SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_pipeline%';
--    Expected: 6 indexes (2 per table + 2 for DLQ enhancements)
--
-- 3. Verify st_dlq enhancements:
--    PRAGMA table_info(st_dlq);
--    Expected: error_kind and error_fingerprint columns
--
-- 4. Test idempotency:
--    Run migration again, verify no errors
-- ============================================================================
