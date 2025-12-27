-- Migration 0020: Remove async worker infrastructure (V1.4 deprecation)
--
-- Removes V1.4 async worker columns from st_wal table.
-- These columns were added in 0011_v1_async_workers.sql but are no longer needed
-- as embedding/FTS processing is now synchronous.
--
-- Migration Status: SAFE (drops columns, no data dependencies)
-- Rollback: Re-run 0011_v1_async_workers.sql to restore columns
--
-- Context: Workers deprecated due to premature optimization and excessive complexity.
-- Performance impact: Commit latency increases from ~80-100ms to ~100-150ms P95.
-- Trade-off accepted for architectural simplicity until scale demands async processing.

BEGIN TRANSACTION;

-- Drop worker status indexes (IF EXISTS supported in all SQLite versions)
DROP INDEX IF EXISTS idx_st_wal_embedding_status;
DROP INDEX IF EXISTS idx_st_wal_fts_status;

-- Drop worker columns (requires SQLite 3.35.0+, Python 3.11 ships with 3.41+)
-- Note: IF EXISTS not supported in ALTER TABLE DROP COLUMN
ALTER TABLE st_wal DROP COLUMN embedding_status;
ALTER TABLE st_wal DROP COLUMN embedding_id;
ALTER TABLE st_wal DROP COLUMN fts_status;
ALTER TABLE st_wal DROP COLUMN fts_entry_id;

COMMIT;

-- Migration complete: st_wal table no longer tracks async worker status
-- All embedding/FTS processing now happens synchronously in commit path
