-- V1 Database Schema Migration (0011_v1_privacy_and_async.sql)
--
-- This migration adds V1.3 (privacy) and V1.4 (async workers) fields:
--
-- V1.3 NEW: Policy Stamp & Location Privacy
--   - policy_stamp_json: JSON serialized policy decision (band, obligations, visible_to)
--   - location_geohash: Geohash string for privacy-masked location (AMBER: geohash-6, RED: geohash-4)
--   - location_precision_m: Precision in meters (GREEN: exact, AMBER: ~5km, RED: ~25km)
--
-- V1.4 NEW: Async Worker Status Tracking
--   - embedding_status: Track embedding worker progress (PENDING, IN_PROGRESS, COMPLETE, FAILED)
--   - embedding_id: Store embedding vector ID once computed
--   - fts_status: Track FTS indexing worker progress
--   - fts_entry_id: Store FTS index entry ID once indexed
--
-- Reduces commit latency from ~150ms to ~80-100ms by deferring heavy computation
-- to background workers.
--
-- Architecture:
--   1. Commit completes without embedding/FTS (status=PENDING)
--   2. Outbox entry created with work payload
--   3. Async worker picks up work from outbox
--   4. Computes embedding or FTS index
--   5. Updates st_wal with result IDs and marks status=COMPLETE
--   6. Marks outbox entry complete
--
-- Migration Status: SAFE (adds new columns with defaults)
-- Rollback: DELETE columns if needed (backward compatible)

BEGIN TRANSACTION;

-- ========================================================================================
-- V1.3: Policy Stamp & Location Privacy
-- ========================================================================================

-- policy_stamp_json: JSON blob containing policy evaluation result
-- Format: {"policy_version": "2025-11-01", "band": "AMBER", "obligations": ["LOG"], "visible_to": ["alice", "bob"], "decision": "PERMIT"}
-- Purpose: Audit trail for policy decisions attached to envelope
-- Used By: PolicyEvaluator, Memory Steward
ALTER TABLE st_wal ADD COLUMN policy_stamp_json TEXT DEFAULT NULL;

-- location_geohash: Privacy-masked location as geohash
-- Format: geohash-4 (RED, ~25km), geohash-6 (AMBER, ~5km), NULL (GREEN, exact lat/lon)
-- Purpose: GDPR/CCPA location privacy (coarse-grained for sensitive data)
-- Used By: LocationPrivacyHandler (after PEP decision)
ALTER TABLE st_wal ADD COLUMN location_geohash TEXT DEFAULT NULL;

-- location_precision_m: Precision of location in meters
-- Values: NULL (GREEN, exact), 5000 (AMBER, ~5km), 25000 (RED, ~25km)
-- Purpose: Document location masking granularity
ALTER TABLE st_wal ADD COLUMN location_precision_m INTEGER DEFAULT NULL;

-- Index for policy-based queries (e.g., "find all AMBER envelopes")
CREATE INDEX IF NOT EXISTS idx_st_wal_policy_stamp
  ON st_wal(tenant_id, space_id, policy_stamp_json) WHERE policy_stamp_json IS NOT NULL;

-- Index for location privacy analysis
CREATE INDEX IF NOT EXISTS idx_st_wal_location_geohash
  ON st_wal(location_geohash) WHERE location_geohash IS NOT NULL;

-- ========================================================================================
-- V1.4: Async Worker Status Tracking
-- ========================================================================================

-- embedding_status: Track embedding worker progress
-- Values: PENDING, IN_PROGRESS, COMPLETE, FAILED
-- NULL means worker not run yet (backward compat with V0/V1.1/V1.2)
ALTER TABLE st_wal ADD COLUMN embedding_status TEXT DEFAULT NULL;

-- embedding_id: Store embedding vector ID once computed
-- Format: emb-{event_id_prefix}-{hash}
-- Example: emb-evt001-abc123def456
-- NULL means embedding not computed
ALTER TABLE st_wal ADD COLUMN embedding_id TEXT DEFAULT NULL;

-- fts_status: Track FTS indexing worker progress
-- Values: PENDING, IN_PROGRESS, COMPLETE, FAILED
-- NULL means worker not run yet
ALTER TABLE st_wal ADD COLUMN fts_status TEXT DEFAULT NULL;

-- fts_entry_id: Store FTS index entry ID once indexed
-- Format: fts-{event_id_prefix}-{keyword_count:02d}
-- Example: fts-evt001-05
-- NULL means FTS index entry not created
ALTER TABLE st_wal ADD COLUMN fts_entry_id TEXT DEFAULT NULL;

-- Create indexes for worker queries
CREATE INDEX IF NOT EXISTS idx_st_wal_embedding_status
  ON st_wal(tenant_id, space_id, embedding_status) WHERE embedding_status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_st_wal_fts_status
  ON st_wal(tenant_id, space_id, fts_status) WHERE fts_status = 'PENDING';

-- Allow queries like:
--   SELECT * FROM st_wal WHERE embedding_status = 'PENDING'
--   SELECT * FROM st_wal WHERE fts_status = 'PENDING'
-- For worker discovery pattern

COMMIT;

-- ========================================================================================
-- Verification queries (run after migration):
-- ========================================================================================
-- SELECT COUNT(*) FROM st_wal WHERE policy_stamp_json IS NOT NULL;
-- SELECT COUNT(*) FROM st_wal WHERE location_geohash IS NOT NULL;
-- SELECT COUNT(*) FROM st_wal WHERE embedding_status IS NOT NULL;
-- SELECT COUNT(*) FROM st_wal WHERE fts_status IS NOT NULL;
-- SELECT DISTINCT embedding_status FROM st_wal WHERE embedding_status IS NOT NULL;
-- SELECT DISTINCT fts_status FROM st_wal WHERE fts_status IS NOT NULL;
-- ========================================================================================
