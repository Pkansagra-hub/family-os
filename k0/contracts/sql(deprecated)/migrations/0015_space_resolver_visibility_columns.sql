-- Migration: 0015_space_resolver_visibility_columns
-- Description: Add Space Resolver lineage + visibility metadata columns to st_hipp_store
-- Author: K0 Architecture Team
-- Date: 2025-11-13
-- Dependencies: 0014_affect_storage_wiring
-- Related ADRs: ADR-K004a (contracts), ADR-K004d (visibility matrix), ADR-K004e (observability)

BEGIN;

-- ============================================================================
-- Visibility + Policy Provenance (ADR-K004d)
-- ============================================================================
ALTER TABLE st_hipp_store ADD COLUMN visibility_policy_version TEXT NOT NULL
  DEFAULT 'legacy:v0';
ALTER TABLE st_hipp_store ADD COLUMN policy_overrides TEXT NOT NULL
  DEFAULT '[]';
ALTER TABLE st_hipp_store ADD COLUMN visibility_adjustments TEXT NOT NULL
  DEFAULT '[]';

-- ============================================================================
-- Resolver Observability + Cache Lineage (ADR-K004e)
-- ============================================================================
ALTER TABLE st_hipp_store ADD COLUMN resolver_state TEXT NOT NULL
  DEFAULT 'BYPASS_LEGACY'
  CHECK (resolver_state IN (
    'NORMAL',
    'CACHE_WARN',
    'SAFE_MODE',
    'STRICT_GUARDIAN',
    'BYPASS_LEGACY'
  ));
ALTER TABLE st_hipp_store ADD COLUMN cache_snapshot_version TEXT NOT NULL
  DEFAULT 'legacy-cache:v0';
ALTER TABLE st_hipp_store ADD COLUMN resolution_latency_ms REAL NOT NULL
  DEFAULT 0;

COMMIT;

-- ============================================================================
-- Verification Snippets (manual)
-- ============================================================================
-- PRAGMA table_info('st_hipp_store');
-- SELECT COUNT(*) AS column_count FROM pragma_table_info('st_hipp_store');
-- SELECT name, sql FROM sqlite_master WHERE type='table' AND name='st_hipp_store';
-- UPDATE st_hipp_store SET resolver_state = 'SAFE_MODE' WHERE 1=0; -- constraint test
