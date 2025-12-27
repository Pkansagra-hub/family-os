-- ========================================================================================
-- Migration 0023: Drop Remaining Orphaned Tables from Migration 0008
-- ========================================================================================
-- Created: 2025-11-15
-- Purpose: Drop 8 remaining orphaned tables from Migration 0008 that were missed in 0021/0022
-- Architecture: Complete cleanup of unused intelligence/orchestration tables
-- Related: STORAGE_AUDIT_MIGRATION_0021.md, Migration 0021, Migration 0022
-- ========================================================================================
-- Impact:
--   - 8 tables permanently deleted (drive_state, drive_intents, metacog_reports,
--     metacog_signals, action_decisions, action_receipts, temporal_index, temporal_patterns)
--   - Zero production code breakage (verified via grep search)
--   - NO ROLLBACK (immediate permanent deletion)
-- ========================================================================================
-- Tables Dropped (All from Migration 0008):
--   - drive_state: P06 Drives & Homeostasis state tracking
--   - drive_intents: P06 Drives & Homeostasis action proposals
--   - metacog_reports: P20 Metacognition confidence reports
--   - metacog_signals: P20 Metacognition anomaly signals
--   - action_decisions: P04 Arbitration decision records
--   - action_receipts: P04 Arbitration execution receipts
--   - temporal_index: P01 Temporal multi-resolution time shards
--   - temporal_patterns: P01 Temporal circadian/weekly patterns
-- ========================================================================================
-- Evidence of Zero Usage:
--   grep -r "drive_state|drive_intents" k0/**/*.py --exclude-dir=tests → 0 matches
--   grep -r "metacog_reports|metacog_signals" k0/**/*.py --exclude-dir=tests → 0 matches
--   grep -r "action_decisions|action_receipts" k0/**/*.py --exclude-dir=tests → 0 matches
--   grep -r "temporal_index|temporal_patterns" k0/**/*.py --exclude-dir=tests → 0 matches
-- ========================================================================================

BEGIN;

PRAGMA foreign_keys=OFF;

-- ========================================================================================
-- Migration 0008: Orphaned Intelligence/Orchestration Tables (8 tables)
-- ========================================================================================

DROP TABLE IF EXISTS drive_state;
DROP TABLE IF EXISTS drive_intents;
DROP TABLE IF EXISTS metacog_reports;
DROP TABLE IF EXISTS metacog_signals;
DROP TABLE IF EXISTS action_decisions;
DROP TABLE IF EXISTS action_receipts;
DROP TABLE IF EXISTS temporal_index;
DROP TABLE IF EXISTS temporal_patterns;

-- ========================================================================================
-- Verification Queries (Uncomment to verify)
-- ========================================================================================
-- SELECT name FROM sqlite_master WHERE type='table'
--   AND name IN ('drive_state', 'drive_intents', 'metacog_reports', 'metacog_signals',
--                'action_decisions', 'action_receipts', 'temporal_index', 'temporal_patterns');
-- -- Should return 0 rows

PRAGMA foreign_keys=ON;

COMMIT;

-- ========================================================================================
-- Migration Notes
-- ========================================================================================
-- 1. All 8 tables are empty (no data loss)
-- 2. No production code references these tables (verified via grep search)
-- 3. Only test files reference retention/crdt tables (unrelated to these 8)
-- 4. This migration is IRREVERSIBLE - no rollback possible
-- 5. Migration 0008 originally created 12 tables:
--    - 4 dropped in Migration 0022 (prospective_triggers, prospective_outcomes, st_emb, st_aff)
--    - 8 dropped in this migration (drive_state, drive_intents, metacog_reports, metacog_signals,
--                                    action_decisions, action_receipts, temporal_index, temporal_patterns)
-- 6. Fresh pipeline implementations (P01, P04, P06, P20) will design minimal storage per PIPELINE_PROCESS.md
-- 7. Total cleanup: 36 tables removed (28 from Migrations 0021/0022 + 8 from this migration)

-- ========================================================================================
-- Post-Migration Verification Checklist
-- ========================================================================================
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'drive_%';
-- [ ] Verify: Result should be 0
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'metacog_%';
-- [ ] Verify: Result should be 0
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'action_%';
-- [ ] Verify: Result should be 0
-- [ ] Run: SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'temporal_%';
-- [ ] Verify: Result should be 0
-- [ ] Run: PRAGMA integrity_check;
-- [ ] Verify: Result should be "ok"
-- [ ] Restart kernel: ./k0.ps1 -Command restart
-- [ ] Verify: Kernel boots without errors
-- [ ] Run tests: pytest tests/ -v
-- [ ] Verify: All tests pass
-- [ ] Submit envelope: python k0/provision_and_submit.py
-- [ ] Verify: Envelope processed successfully
