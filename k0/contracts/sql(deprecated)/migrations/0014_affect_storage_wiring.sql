-- Migration: 0014_affect_storage_wiring
-- Description: Add affect household/EMA storage, counterfactual caches, and additional affect metadata columns
-- Author: K0 Architecture Team
-- Date: 2025-11-13
-- Dependencies: 0013_p02_write_pipeline_enhancements
-- Related ADRs: ADR-0012d, ADR-0012g, ADR-0012h, ADR-0012i

BEGIN;

-- ============================================================================
-- 1) Additional Affect Columns on st_hipp_store (Gate 2 wiring)
-- ============================================================================
-- Purpose: Persist social/lifecycle modifiers, policy details, calibration metadata,
--          and link records to household/counterfactual context without later migrations.
-- Notes: Nullable columns to keep backward compatibility with existing writes.

ALTER TABLE st_hipp_store ADD COLUMN affect_band TEXT
  CHECK (affect_band IN ('GREEN', 'AMBER', 'RED', 'BLACK'));
ALTER TABLE st_hipp_store ADD COLUMN affect_band_reasons TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_rule_ids TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_action_type TEXT
  CHECK (affect_action_type IN ('share', 'notify', 'recall', 'suggest'));
ALTER TABLE st_hipp_store ADD COLUMN affect_policy_action TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_social_tags TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_lifecycle_tags TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_calibration_id TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_calibration_version TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_household_state_id TEXT;
ALTER TABLE st_hipp_store ADD COLUMN relationship_context_id TEXT;
ALTER TABLE st_hipp_store ADD COLUMN household_calendar_event_id TEXT;
ALTER TABLE st_hipp_store ADD COLUMN person_metadata_version TEXT;

-- Indexes for new columns
CREATE INDEX idx_hipp_affect_band_ts ON st_hipp_store(affect_band, affect_computed_at)
  WHERE affect_band IS NOT NULL;
CREATE INDEX idx_hipp_household_state ON st_hipp_store(affect_household_state_id)
  WHERE affect_household_state_id IS NOT NULL;
CREATE INDEX idx_hipp_relationship_ctx ON st_hipp_store(relationship_context_id)
  WHERE relationship_context_id IS NOT NULL;

-- ============================================================================
-- 2) Household Affect State Table (ADR-0012g)
-- ============================================================================
-- Purpose: Persist aggregated household affect metrics and pattern detection outputs.
-- Supports both historical queries and joins from st_hipp_store.

CREATE TABLE IF NOT EXISTS st_household_affect_state (
    state_id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    n_active_members INTEGER DEFAULT 0,
    active_members TEXT,
    valence_avg REAL,
    valence_min REAL,
    valence_max REAL,
    valence_std REAL,
    arousal_avg REAL,
    arousal_min REAL,
    arousal_max REAL,
    arousal_std REAL,
    conflict_active INTEGER DEFAULT 0,
    conflict_severity REAL,
    conflict_participants INTEGER,
    conflict_duration_seconds INTEGER,
    family_moment_active INTEGER DEFAULT 0,
    family_moment_participants INTEGER,
    celebration_active INTEGER DEFAULT 0,
    contagion_active INTEGER DEFAULT 0,
    contagion_source TEXT,
    contagion_magnitude REAL,
    valence_trend TEXT,
    arousal_trend TEXT,
    metadata TEXT
);

CREATE INDEX idx_household_affect_space_ts ON st_household_affect_state(space_id, computed_at DESC);
CREATE INDEX idx_household_affect_conflict ON st_household_affect_state(household_id, conflict_active);

-- ============================================================================
-- 3) EMA State Persistence (ADR-0012d)
-- ============================================================================
-- Purpose: Provide durable snapshot + TTL metadata for dual-EMA smoothing/cache warmup.

CREATE TABLE IF NOT EXISTS st_affect_ema_state (
    person_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    valence_fast REAL,
    valence_slow REAL,
    arousal_fast REAL,
    arousal_slow REAL,
    n_observations INTEGER DEFAULT 0,
    calibration_id TEXT,
    calibration_version TEXT,
    last_updated TEXT NOT NULL,
    ttl_expires_at TEXT,
    PRIMARY KEY (person_id, space_id)
);

CREATE INDEX idx_affect_ema_space_last_updated ON st_affect_ema_state(space_id, last_updated DESC);
CREATE INDEX idx_affect_ema_ttl ON st_affect_ema_state(ttl_expires_at)
  WHERE ttl_expires_at IS NOT NULL;

-- ============================================================================
-- 4) Counterfactual Cache Tables (ADR-0012i)
-- ============================================================================
-- Purpose: Enable <10ms counterfactual lookup by caching inputs/results by hash.

CREATE TABLE IF NOT EXISTS st_affect_counterfactual_input (
    request_hash TEXT PRIMARY KEY,
    action_type TEXT NOT NULL CHECK (action_type IN ('share', 'notify', 'recall', 'suggest')),
    content_sha256 TEXT NOT NULL,
    recipient_ids TEXT NOT NULL,
    household_state_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS st_affect_counterfactual_result (
    request_hash TEXT PRIMARY KEY REFERENCES st_affect_counterfactual_input(request_hash) ON DELETE CASCADE,
    is_safe INTEGER NOT NULL,
    blocked_recipients TEXT,
    predicted_bands TEXT,
    valence_delta_json TEXT,
    arousal_delta_json TEXT,
    reasons TEXT,
    confidence REAL,
    expires_at TEXT
);

CREATE INDEX idx_counterfactual_input_action ON st_affect_counterfactual_input(action_type);
CREATE INDEX idx_counterfactual_result_expiry ON st_affect_counterfactual_result(expires_at)
  WHERE expires_at IS NOT NULL;

COMMIT;
