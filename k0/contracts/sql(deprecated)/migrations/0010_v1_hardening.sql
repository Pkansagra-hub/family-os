-- ========================================================================================
-- K0 V1 Security Hardening: Full Envelope Signature & HMAC Idempotency
-- ========================================================================================
-- Migration: 0010
-- Created: 2025-01-22
-- Description: Add V1 security hardening for envelope signature verification and HMAC idempotency
-- ADR Reference: ADR-0001 (Envelope Signature V1), ADR-0002 (HMAC Idempotency)
-- Breaking Changes:
--   1. V0 signatures (body excluded) incompatible with V1 logic (body included)
--   2. All V1 envelopes require: sig_alg, sig_kid, envelope_sha256
--   3. Replay detection via envelope_sha256 uniqueness
--   4. HMAC-based idempotency with 60-second time buckets
-- ========================================================================================
-- Columns Added:
--   1. st_wal: envelope_sha256 (UNIQUE), ingested_at, clock_skew_ms
--   2. st_devices: hmac_secret (device provisioning)
-- ========================================================================================

BEGIN;

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=OFF;

-- ========================================================================================
-- ALTER: st_wal - Add V1 envelope hash + ingestion tracking
-- ========================================================================================
-- envelope_sha256: SHA-256 hash of entire canonical envelope (headers + body)
--   Purpose: Exact duplicate/replay detection (envelope_sha256 is UNIQUE)
--   Format: 64-character hex string
--   Used By: MinimalGate._check_envelope_replay()
-- ingested_at: RFC 3339 timestamp when envelope was ingested at gate
--   Purpose: Clock skew detection (for clock_skew_ms)
--   Format: "2025-01-22T15:30:45.123Z"
-- clock_skew_ms: Milliseconds between envelope.ts and ingested_at
--   Purpose: Detect device clock drift/attacks
--   Range: -60000 to +60000 (±60 seconds tolerance)

ALTER TABLE st_wal ADD COLUMN envelope_sha256 TEXT;
-- Index for fast replay detection lookups (UNIQUE constraint enforced by application logic due to SQLite ALTER TABLE limitations)
CREATE UNIQUE INDEX IF NOT EXISTS idx_wal_envelope_sha256 ON st_wal(envelope_sha256) WHERE envelope_sha256 IS NOT NULL;

ALTER TABLE st_wal ADD COLUMN ingested_at TEXT;
-- Index for time-based queries (clock skew analysis)
CREATE INDEX IF NOT EXISTS idx_wal_ingested_at ON st_wal(ingested_at);

ALTER TABLE st_wal ADD COLUMN clock_skew_ms INTEGER;
-- Index for skew analysis (detect drift patterns)
CREATE INDEX IF NOT EXISTS idx_wal_clock_skew ON st_wal(clock_skew_ms);

-- ========================================================================================
-- ALTER: st_devices - Add HMAC secret for idempotency keys
-- ========================================================================================
-- hmac_secret: Device-specific HMAC key for idempotency key derivation
--   Purpose: HMAC-SHA256(device_secret, envelope_sha256|device_id|time_bucket)
--   Format: 32 bytes (raw bytes, NOT hex-encoded in DB)
--   Security: Should be rotated on device re-provisioning
--   Lifetime: Per device provisioning cycle (handled by provisioning ledger)

ALTER TABLE st_devices ADD COLUMN hmac_secret BLOB;
-- Index for secret lookups (when computing HMAC idem keys)
CREATE INDEX IF NOT EXISTS idx_devices_hmac_secret ON st_devices(device_id) WHERE hmac_secret IS NOT NULL;

-- ========================================================================================
-- MIGRATION NOTES
-- ========================================================================================
-- Q: What about existing envelopes?
-- A: Existing envelopes won't have envelope_sha256/ingested_at/clock_skew_ms.
--    They'll be NULL in DB. V1 validation only applies to new (post-migration) envelopes.
--
-- Q: What about existing devices?
-- A: Existing devices won't have hmac_secret. During device provisioning upgrade,
--    hmac_secret will be generated and stored. Until then, HMAC-based idem is disabled.
--
-- Q: Can we downgrade?
-- A: This is a ONE-WAY migration. V1 envelopes cannot be validated with V0 logic.
--    Rollback requires manual schema restoration (not recommended in production).
--
-- Q: Performance impact?
-- A: Three new indexes (small). Index on envelope_sha256 will be frequently used.
--    Ingested_at and clock_skew_ms are rarely queried (audit/analysis only).
--
-- Q: What about the UNIQUE constraint on envelope_sha256?
-- A: Enforces replay protection at DB level. If MinimalGate._check_envelope_replay
--    fails to detect a replay, DB UNIQUE constraint will catch it on INSERT.
--    Error will bubble up as IntegrityError (which MinimalGate must handle).

COMMIT;
