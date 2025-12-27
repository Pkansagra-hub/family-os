-- ========================================================================================
-- Migration 0022: Drop Deprecated Tables (After 1-Week Safety Window)
-- ========================================================================================
-- Created: 2025-11-15
-- Scheduled: Week of Nov 22, 2025 (7 days after Migration 0021)
-- Purpose: Permanently drop 28 deprecated tables after safety window
-- Architecture: Final cleanup after verifying no production issues
-- Related: STORAGE_AUDIT_MIGRATION_0021.md, Migration 0021
-- ========================================================================================
-- Prerequisites:
--   1. Migration 0021 applied successfully
--   2. Kernel booted and running for 7 days without errors
--   3. No references to deprecated tables in logs
--   4. All tests passing (deprecated table references removed)
-- ========================================================================================
-- Impact:
--   - 28 tables permanently deleted
--   - 410+ columns removed
--   - Indexes and FTS tables automatically dropped
--   - NO ROLLBACK after this migration (irreversible)
-- ========================================================================================
-- Tables Dropped:
--   Migration 0006: 10 memory staging tables
--   Migration 0008: 4 intelligence tables
--   Migration 0009: 7 connector domain tables
--   Migration 0014: 4 affect tables
--   Migration 0016: 2 space authority tables
--   Migration 0017: 1 relationships cache table
-- ========================================================================================

BEGIN;

PRAGMA foreign_keys=OFF;

-- ========================================================================================
-- Migration 0006: Memory Staging Tables (10 tables)
-- ========================================================================================

DROP TABLE IF EXISTS _deprecated_st_hipp_store;
DROP TABLE IF EXISTS _deprecated_st_epi;
DROP TABLE IF EXISTS _deprecated_st_sem;
DROP TABLE IF EXISTS _deprecated_st_ws;
DROP TABLE IF EXISTS _deprecated_st_proc;
DROP TABLE IF EXISTS _deprecated_st_social;
DROP TABLE IF EXISTS _deprecated_self_traits;
DROP TABLE IF EXISTS _deprecated_self_preferences;
DROP TABLE IF EXISTS _deprecated_self_health;
DROP TABLE IF EXISTS _deprecated_self_roles;

-- ========================================================================================
-- Migration 0008: Intelligence Tables (4 tables)
-- ========================================================================================

DROP TABLE IF EXISTS _deprecated_prospective_triggers;
DROP TABLE IF EXISTS _deprecated_prospective_outcomes;
DROP TABLE IF EXISTS _deprecated_st_emb;
DROP TABLE IF EXISTS _deprecated_st_aff;

-- ========================================================================================
-- Migration 0009: Connector Domain Tables (7 tables)
-- ========================================================================================

DROP TABLE IF EXISTS _deprecated_st_health;
DROP TABLE IF EXISTS _deprecated_st_financial;
DROP TABLE IF EXISTS _deprecated_st_calendar;
DROP TABLE IF EXISTS _deprecated_st_shopping;
DROP TABLE IF EXISTS _deprecated_st_envelope_metadata;
DROP TABLE IF EXISTS _deprecated_st_unprocessed_bag;
DROP TABLE IF EXISTS _deprecated_st_connector_registry;

-- ========================================================================================
-- Migration 0014: Affect Storage Tables (4 tables)
-- ========================================================================================

DROP TABLE IF EXISTS _deprecated_st_household_affect_state;
DROP TABLE IF EXISTS _deprecated_st_affect_ema_state;
DROP TABLE IF EXISTS _deprecated_st_affect_counterfactual_input;
DROP TABLE IF EXISTS _deprecated_st_affect_counterfactual_result;

-- ========================================================================================
-- Migration 0016: Space Authority Tables (2 tables)
-- ========================================================================================

DROP TABLE IF EXISTS _deprecated_st_spaces;
DROP TABLE IF EXISTS _deprecated_st_space_members;

-- ========================================================================================
-- Migration 0017: Relationships Cache (1 table)
-- ========================================================================================

DROP TABLE IF EXISTS _deprecated_st_relationships;

-- ========================================================================================
-- Drop Related FTS Tables (if any exist)
-- ========================================================================================

DROP TABLE IF EXISTS st_epi_fts;  -- From Migration 0004, tied to st_epi
DROP TABLE IF EXISTS st_hipp_fts;  -- From Migration 0004, tied to st_hipp_store

-- ========================================================================================
-- Verification Queries (Uncomment to verify)
-- ========================================================================================
-- SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_deprecated_%';  -- Should return 0 rows
-- SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE '_deprecated_%';  -- Should return 0

PRAGMA foreign_keys=ON;

COMMIT;

-- ========================================================================================
-- Migration Notes
-- ========================================================================================
-- 1. This migration is IRREVERSIBLE - no rollback possible
-- 2. Apply only after 1-week safety window (Migration 0021 applied on Nov 15, 2025)
-- 3. Verify kernel stability and no errors referencing deprecated tables
-- 4. All indexes associated with dropped tables are automatically removed by SQLite
-- 5. Total storage reclaimed: ~410 columns across 28 tables
-- 6. Fresh pipeline storage will be designed per PIPELINE_PROCESS.md Step 2
-- 7. Schedule: Apply this migration on or after Nov 22, 2025

-- ========================================================================================
-- Post-Migration Verification Checklist
-- ========================================================================================
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE '_deprecated_%';
-- [ ] Verify: Result should be 0
-- [ ] Run: PRAGMA integrity_check;
-- [ ] Verify: Result should be "ok"
-- [ ] Restart kernel: ./k0.ps1 -Command restart
-- [ ] Verify: Kernel boots without errors
-- [ ] Run tests: pytest tests/ -v
-- [ ] Verify: All tests pass
-- [ ] Submit envelope: python k0/provision_and_submit.py
-- [ ] Verify: Envelope processed successfully
