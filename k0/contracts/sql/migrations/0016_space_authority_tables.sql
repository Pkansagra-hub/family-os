-- Migration: 0016_space_authority_tables
-- Description: Create st_spaces and st_space_members tables for Space Authority Cache
-- Author: K0 Architecture Team
-- Date: 2025-11-13
-- Dependencies: 0015_space_resolver_visibility_columns
-- Related ADRs: ADR-K004b (cache authority), ADR-K004c (ownership rules), ADR-K004d (visibility)

BEGIN;

-- ============================================================================
-- Authoritative space metadata (ADR-K004b)
-- ============================================================================
CREATE TABLE IF NOT EXISTS st_spaces (
  space_id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  consent_policy TEXT,
  coownership_policy TEXT,
  steward_ids TEXT NOT NULL DEFAULT '[]',
  metadata_json TEXT,
  state TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK(state IN ('ACTIVE','FROZEN','DECOMMISSIONED')),
  source_version TEXT NOT NULL,
  hydrated_at TEXT NOT NULL,
  ttl_seconds INTEGER NOT NULL DEFAULT 600,
  checksum TEXT
);

CREATE INDEX IF NOT EXISTS idx_spaces_household ON st_spaces(household_id);
CREATE INDEX IF NOT EXISTS idx_spaces_kind ON st_spaces(kind);

-- ============================================================================
-- Per-space membership roster with capabilities (ADR-K004b/K004c)
-- ============================================================================
CREATE TABLE IF NOT EXISTS st_space_members (
  space_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  household_id TEXT NOT NULL,
  role TEXT NOT NULL,
  capabilities TEXT NOT NULL DEFAULT '[]',
  delegated_from TEXT,
  membership_state TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK(membership_state IN ('ACTIVE','SUSPENDED','REMOVED')),
  opt_out_flags TEXT NOT NULL DEFAULT '[]',
  source_version TEXT NOT NULL,
  hydrated_at TEXT NOT NULL,
  ttl_seconds INTEGER NOT NULL DEFAULT 600,
  PRIMARY KEY(space_id, person_id),
  FOREIGN KEY(space_id) REFERENCES st_spaces(space_id)
);

CREATE INDEX IF NOT EXISTS idx_space_members_household ON st_space_members(household_id);
CREATE INDEX IF NOT EXISTS idx_space_members_role ON st_space_members(role);
CREATE INDEX IF NOT EXISTS idx_space_members_space_state ON st_space_members(space_id, membership_state);

COMMIT;

-- ============================================================================
-- Verification snippets (manual)
-- ============================================================================
-- .read k0/contracts/sql/migrations/0016_space_authority_tables.sql
-- PRAGMA table_info('st_spaces');
-- PRAGMA table_info('st_space_members');
-- SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_space%';
