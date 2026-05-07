-- 0001_initial.sql — k1.selfmodel SQLite schema (M3.E4.I2)
--
-- All tables for the projection store. Applied as a single migration
-- by ``k1.selfmodel.adapters.sqlite_migrations.apply_migrations`` when
-- ``PRAGMA user_version == 0``. Sets ``PRAGMA user_version = 1`` on
-- success.
--
-- Conventions:
--   * Times stored as INTEGER millisecond epochs.
--   * Booleans stored as INTEGER 0/1.
--   * Body / payload columns are JSON text (validated at the application
--     layer, not by SQLite).
--   * Every mutating row is timestamped at write time.

-- ---------------------------------------------------------------
-- Self-model projection
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS self_projection (
    actor_id          TEXT PRIMARY KEY,
    revision          TEXT NOT NULL,
    parent_revision   TEXT NOT NULL DEFAULT '',
    written_at_ms     INTEGER NOT NULL,
    snapshot_json     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_self_projection_written_at
    ON self_projection(written_at_ms);

-- ---------------------------------------------------------------
-- Family-model projection
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS family_projection (
    family_space_id   TEXT PRIMARY KEY,
    revision          TEXT NOT NULL,
    parent_revision   TEXT NOT NULL DEFAULT '',
    written_at_ms     INTEGER NOT NULL,
    snapshot_json     TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- Constitution projection (active row per constitution_id)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS constitution_projection (
    constitution_id   TEXT PRIMARY KEY,
    version           TEXT NOT NULL,
    parent_version    TEXT NOT NULL DEFAULT '',
    revision          TEXT NOT NULL,
    parent_revision   TEXT NOT NULL DEFAULT '',
    written_at_ms     INTEGER NOT NULL,
    snapshot_json     TEXT NOT NULL
);

-- Append-only history (every write produces a row here too; latest
-- per constitution_id mirrors ``constitution_projection``).
CREATE TABLE IF NOT EXISTS constitution_history (
    constitution_id   TEXT NOT NULL,
    version           TEXT NOT NULL,
    parent_version    TEXT NOT NULL DEFAULT '',
    written_at_ms     INTEGER NOT NULL,
    snapshot_json     TEXT NOT NULL,
    PRIMARY KEY (constitution_id, version)
);

-- ---------------------------------------------------------------
-- Amendment proposals + signatures
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS amendment_proposals (
    amendment_id      TEXT PRIMARY KEY,
    parent_version    TEXT NOT NULL DEFAULT '',
    proposed_by       TEXT NOT NULL,
    body_json         TEXT NOT NULL,
    status            TEXT NOT NULL,
    expires_at_ms     INTEGER NOT NULL DEFAULT 0,
    conflict_json     TEXT,
    written_at_ms     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_amendments_status
    ON amendment_proposals(status);

CREATE INDEX IF NOT EXISTS idx_amendments_parent
    ON amendment_proposals(parent_version);

CREATE TABLE IF NOT EXISTS amendment_signatures (
    amendment_id      TEXT NOT NULL,
    signer_id         TEXT NOT NULL,
    key_id            TEXT NOT NULL,
    algorithm         TEXT NOT NULL DEFAULT 'ed25519',
    signature_b64     TEXT NOT NULL,
    signed_at_ms      INTEGER NOT NULL,
    PRIMARY KEY (amendment_id, signer_id),
    FOREIGN KEY (amendment_id) REFERENCES amendment_proposals(amendment_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- Identity sessions (TTL-indexed)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS identity_sessions (
    session_token        TEXT PRIMARY KEY,
    profile_id           TEXT NOT NULL,
    tier                 INTEGER NOT NULL,
    device_id            TEXT NOT NULL,
    issued_at_ms         INTEGER NOT NULL,
    hard_expires_at_ms   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_identity_sessions_expiry
    ON identity_sessions(hard_expires_at_ms);

CREATE INDEX IF NOT EXISTS idx_identity_sessions_profile
    ON identity_sessions(profile_id);

-- ---------------------------------------------------------------
-- Projection sync state (M4 bridge sync; created here for parity)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projection_sync_state (
    projection_key       TEXT PRIMARY KEY,
    freshness            TEXT NOT NULL DEFAULT 'fresh',
    last_synced_at_ms    INTEGER NOT NULL DEFAULT 0,
    last_revision        TEXT NOT NULL DEFAULT ''
);
