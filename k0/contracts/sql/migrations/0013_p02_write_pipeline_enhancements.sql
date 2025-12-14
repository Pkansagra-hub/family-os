-- Migration: 0013_p02_write_pipeline_enhancements
-- Description: Add affect analysis and consolidation routing fields to st_hipp_store for P02 pipeline
-- Author: K0 Architecture Team
-- Date: 2025-11-13
-- Dependencies: 0012_pipeline_infrastructure
-- Related Docs: docs/versioning_documents/pipeline_implementation/p02_implementation_plan.md

BEGIN;

-- ============================================================================
-- Affect Analysis Fields (6 columns)
-- ============================================================================
-- Purpose: Emotional intelligence from sentiment analysis
-- Used by: P02 pipeline affect_analyzer.py module
-- Range: valence [-1.0, 1.0], arousal [0.0, 1.0], confidence [0.0, 1.0]

ALTER TABLE st_hipp_store ADD COLUMN affect_valence REAL;
ALTER TABLE st_hipp_store ADD COLUMN affect_arousal REAL;
ALTER TABLE st_hipp_store ADD COLUMN affect_tags TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_confidence REAL;
ALTER TABLE st_hipp_store ADD COLUMN affect_model_version TEXT;
ALTER TABLE st_hipp_store ADD COLUMN affect_computed_at TEXT;

-- Index for affect-based queries (e.g., find highly emotional memories)
CREATE INDEX idx_hipp_affect_valence ON st_hipp_store(affect_valence)
  WHERE affect_valence IS NOT NULL;

-- ============================================================================
-- Consolidation Routing Fields (4 columns)
-- ============================================================================
-- Purpose: P03 consolidation pipeline routing to 8 memory layers
-- Targets: epi (episodic), sem (semantic), proc (procedural), social, spatial,
--          meta (metacognitive), working, prospective
-- Used by: P02 pipeline content_classifier.py module, P03 consolidation pipeline

ALTER TABLE st_hipp_store ADD COLUMN consolidation_target TEXT;
ALTER TABLE st_hipp_store ADD COLUMN consolidation_confidence REAL;
ALTER TABLE st_hipp_store ADD COLUMN consolidation_status TEXT
  DEFAULT 'PENDING'
  CHECK (consolidation_status IN ('PENDING', 'CONSOLIDATED', 'FAILED'));
ALTER TABLE st_hipp_store ADD COLUMN consolidated_at TEXT;

-- Index for P03 consolidation pipeline queries (find pending memories)
CREATE INDEX idx_hipp_consolidation ON st_hipp_store(consolidation_status)
  WHERE consolidation_status = 'PENDING';

-- ============================================================================
-- Verification Queries (for testing)
-- ============================================================================
-- Uncomment to verify migration:
--
-- -- Check new columns exist
-- PRAGMA table_info(st_hipp_store);
--
-- -- Count total columns (should be 74: original 64 + 10 new)
-- SELECT COUNT(*) as column_count FROM pragma_table_info('st_hipp_store');
--
-- -- Verify indexes created
-- SELECT name, tbl_name FROM sqlite_master
-- WHERE type = 'index'
--   AND tbl_name = 'st_hipp_store'
--   AND name IN ('idx_hipp_affect_valence', 'idx_hipp_consolidation');
--
-- -- Test CHECK constraint on consolidation_status
-- -- This should fail:
-- -- INSERT INTO st_hipp_store (event_id, cognitive_trace_id, text, ts, tenant_id,
-- --   space_id, privacy_band, owner_id, visible_to, author_id, created_at,
-- --   crdt_vector_clock, crdt_lamport, consolidation_status)
-- -- VALUES ('test-001', 'trace-001', 'test', '2025-11-13T00:00:00Z', 'tenant-1',
-- --   'space-1', 'GREEN', 'person-1', '["person-1"]', 'person-1',
-- --   '2025-11-13T00:00:00Z', '{"device-1": 1}', 1, 'INVALID');

COMMIT;

-- ============================================================================
-- Migration Notes
-- ============================================================================
-- 1. All new columns are nullable (no DEFAULT except consolidation_status)
-- 2. Indexes use WHERE clauses for efficiency (partial indexes)
-- 3. consolidation_status CHECK constraint ensures only valid states
-- 4. Backward compatible: existing rows work without new columns
-- 5. location_geohash and location_precision_m already exist via k0/policy/location_privacy.py
-- 6. Total columns after migration: 74 (64 original + 10 new)
