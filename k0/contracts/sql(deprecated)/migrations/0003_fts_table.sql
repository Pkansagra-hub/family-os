-- Add FTS (Full Text Search) table for semantic search capabilities.
-- Uses SQLite FTS5 virtual table for efficient text search.

BEGIN;

-- FTS virtual table for full-text search over WAL content
CREATE VIRTUAL TABLE IF NOT EXISTS st_fts USING fts5(
  wal_pos UNINDEXED,           -- Reference to st_wal.pos
  tenant_id UNINDEXED,         -- Tenant scope
  space_id UNINDEXED,          -- Space scope
  topic UNINDEXED,             -- Topic filter
  content,                     -- Full text content to search
  envelope_json UNINDEXED,     -- Original envelope for reconstruction
  body UNINDEXED,              -- Original body for reconstruction
  payload_sha256 UNINDEXED,    -- SHA256 of payload
  schema_uri UNINDEXED,        -- Schema URI
  schema_version UNINDEXED,    -- Schema version
  device_id UNINDEXED,         -- Device that wrote
  commit_ts UNINDEXED          -- Commit timestamp
);

-- Note: FTS5 virtual tables are self-indexing and do not support additional CREATE INDEX statements

COMMIT;
