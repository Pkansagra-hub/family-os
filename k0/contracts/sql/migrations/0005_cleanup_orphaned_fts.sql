-- Cleanup orphaned st_fts table from migration 0003.
-- Migration 0003 created a generic st_fts table that was never used.
-- Migration 0004 created the actual FTS tables: st_epi_fts and st_hipp_fts.
-- This migration removes the unused st_fts table to avoid confusion.

BEGIN;

-- Drop the orphaned FTS table from migration 0003
-- This table was never populated or used by any code
DROP TABLE IF EXISTS st_fts;

-- Note: st_epi_fts and st_hipp_fts from migration 0004 remain unchanged
-- and are the correct FTS tables for episodic and semantic memory search

COMMIT;
