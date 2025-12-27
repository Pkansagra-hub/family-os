-- ========================================================================================
-- Migration 0021: Deprecate Unused Memory, Intelligence, and Connector Tables
-- ========================================================================================
-- Created: 2025-11-15
-- Purpose: Rename 28 unused tables to _deprecated_ prefix for 1-week safety window
-- Architecture: Clean slate for fresh pipeline development per PIPELINE_PROCESS.md
-- Related: STORAGE_AUDIT_MIGRATION_0021.md (comprehensive audit findings)
-- ========================================================================================
-- Impact:
--   - 28 tables renamed (410+ columns)
--   - Zero production code breakage (all tables unused)
--   - Reversible within 1 week (ALTER TABLE rename back)
--   - Migration 0022 will DROP tables after safety window
-- ========================================================================================
-- Tables Deprecated:
--   Migration 0006: 10 memory staging tables (st_hipp_store, st_epi, st_sem, st_ws, st_proc, st_social, self_*)
--   Migration 0008: 4 intelligence tables (prospective_triggers, prospective_outcomes, st_emb, st_aff)
--   Migration 0009: 7 connector domain tables (st_health, st_financial, st_calendar, st_shopping, st_envelope_metadata, st_unprocessed_bag, st_connector_registry)
--   Migration 0014: 4 affect tables (st_household_affect_state, st_affect_ema_state, st_affect_counterfactual_input, st_affect_counterfactual_result)
--   Migration 0016: 2 space authority tables (st_spaces, st_space_members)
--   Migration 0017: 1 relationships cache table (st_relationships)
-- ========================================================================================

BEGIN;

PRAGMA foreign_keys=OFF;

-- ========================================================================================
-- Migration 0006: Memory Staging Tables (10 tables)
-- ========================================================================================

ALTER TABLE st_hipp_store RENAME TO _deprecated_st_hipp_store;
ALTER TABLE st_epi RENAME TO _deprecated_st_epi;
ALTER TABLE st_sem RENAME TO _deprecated_st_sem;
ALTER TABLE st_ws RENAME TO _deprecated_st_ws;
ALTER TABLE st_proc RENAME TO _deprecated_st_proc;
ALTER TABLE st_social RENAME TO _deprecated_st_social;
ALTER TABLE self_traits RENAME TO _deprecated_self_traits;
ALTER TABLE self_preferences RENAME TO _deprecated_self_preferences;
ALTER TABLE self_health RENAME TO _deprecated_self_health;
ALTER TABLE self_roles RENAME TO _deprecated_self_roles;

-- ========================================================================================
-- Migration 0008: Intelligence Tables (4 tables)
-- ========================================================================================

ALTER TABLE prospective_triggers RENAME TO _deprecated_prospective_triggers;
ALTER TABLE prospective_outcomes RENAME TO _deprecated_prospective_outcomes;
ALTER TABLE st_emb RENAME TO _deprecated_st_emb;
ALTER TABLE st_aff RENAME TO _deprecated_st_aff;

-- ========================================================================================
-- Migration 0009: Connector Domain Tables (7 tables)
-- ========================================================================================

ALTER TABLE st_health RENAME TO _deprecated_st_health;
ALTER TABLE st_financial RENAME TO _deprecated_st_financial;
ALTER TABLE st_calendar RENAME TO _deprecated_st_calendar;
ALTER TABLE st_shopping RENAME TO _deprecated_st_shopping;
ALTER TABLE st_envelope_metadata RENAME TO _deprecated_st_envelope_metadata;
ALTER TABLE st_unprocessed_bag RENAME TO _deprecated_st_unprocessed_bag;
ALTER TABLE st_connector_registry RENAME TO _deprecated_st_connector_registry;

-- ========================================================================================
-- Migration 0014: Affect Storage Tables (4 tables)
-- ========================================================================================

ALTER TABLE st_household_affect_state RENAME TO _deprecated_st_household_affect_state;
ALTER TABLE st_affect_ema_state RENAME TO _deprecated_st_affect_ema_state;
ALTER TABLE st_affect_counterfactual_input RENAME TO _deprecated_st_affect_counterfactual_input;
ALTER TABLE st_affect_counterfactual_result RENAME TO _deprecated_st_affect_counterfactual_result;

-- ========================================================================================
-- Migration 0016: Space Authority Tables (2 tables)
-- ========================================================================================

ALTER TABLE st_spaces RENAME TO _deprecated_st_spaces;
ALTER TABLE st_space_members RENAME TO _deprecated_st_space_members;

-- ========================================================================================
-- Migration 0017: Relationships Cache (1 table)
-- ========================================================================================

ALTER TABLE st_relationships RENAME TO _deprecated_st_relationships;

-- ========================================================================================
-- Verification Queries (Uncomment to verify)
-- ========================================================================================
-- SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_deprecated_%';
-- SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE '_deprecated_%';  -- Should return 28

PRAGMA foreign_keys=ON;

COMMIT;

-- ========================================================================================
-- Rollback Instructions (if needed within 1 week)
-- ========================================================================================
-- BEGIN;
-- PRAGMA foreign_keys=OFF;
--
-- -- Migration 0006
-- ALTER TABLE _deprecated_st_hipp_store RENAME TO st_hipp_store;
-- ALTER TABLE _deprecated_st_epi RENAME TO st_epi;
-- ALTER TABLE _deprecated_st_sem RENAME TO st_sem;
-- ALTER TABLE _deprecated_st_ws RENAME TO st_ws;
-- ALTER TABLE _deprecated_st_proc RENAME TO st_proc;
-- ALTER TABLE _deprecated_st_social RENAME TO st_social;
-- ALTER TABLE _deprecated_self_traits RENAME TO self_traits;
-- ALTER TABLE _deprecated_self_preferences RENAME TO self_preferences;
-- ALTER TABLE _deprecated_self_health RENAME TO self_health;
-- ALTER TABLE _deprecated_self_roles RENAME TO self_roles;
--
-- -- Migration 0008
-- ALTER TABLE _deprecated_prospective_triggers RENAME TO prospective_triggers;
-- ALTER TABLE _deprecated_prospective_outcomes RENAME TO prospective_outcomes;
-- ALTER TABLE _deprecated_st_emb RENAME TO st_emb;
-- ALTER TABLE _deprecated_st_aff RENAME TO st_aff;
--
-- -- Migration 0009
-- ALTER TABLE _deprecated_st_health RENAME TO st_health;
-- ALTER TABLE _deprecated_st_financial RENAME TO st_financial;
-- ALTER TABLE _deprecated_st_calendar RENAME TO st_calendar;
-- ALTER TABLE _deprecated_st_shopping RENAME TO st_shopping;
-- ALTER TABLE _deprecated_st_envelope_metadata RENAME TO st_envelope_metadata;
-- ALTER TABLE _deprecated_st_unprocessed_bag RENAME TO st_unprocessed_bag;
-- ALTER TABLE _deprecated_st_connector_registry RENAME TO st_connector_registry;
--
-- -- Migration 0014
-- ALTER TABLE _deprecated_st_household_affect_state RENAME TO st_household_affect_state;
-- ALTER TABLE _deprecated_st_affect_ema_state RENAME TO st_affect_ema_state;
-- ALTER TABLE _deprecated_st_affect_counterfactual_input RENAME TO st_affect_counterfactual_input;
-- ALTER TABLE _deprecated_st_affect_counterfactual_result RENAME TO st_affect_counterfactual_result;
--
-- -- Migration 0016
-- ALTER TABLE _deprecated_st_spaces RENAME TO st_spaces;
-- ALTER TABLE _deprecated_st_space_members RENAME TO st_space_members;
--
-- -- Migration 0017
-- ALTER TABLE _deprecated_st_relationships RENAME TO st_relationships;
--
-- PRAGMA foreign_keys=ON;
-- COMMIT;

-- ========================================================================================
-- Migration Notes
-- ========================================================================================
-- 1. All 28 tables are empty (no data loss)
-- 2. No production code references these tables (verified via grep search)
-- 3. Only test files reference some tables (tests will be updated separately)
-- 4. Reversible within 1-week safety window via rollback script above
-- 5. Migration 0022 will permanently DROP these tables after Nov 22, 2025
-- 6. Fresh pipeline implementations (P02-P20) will design minimal storage per PIPELINE_PROCESS.md
-- 7. Estimated storage savings: 410+ unused columns eliminated
