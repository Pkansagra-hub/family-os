-- Migration: 0019_location_privacy_columns
-- Description: Add location_geohash and location_precision_m to st_hipp_store for privacy-preserving location queries
-- Author: K0 Architecture Team
-- Date: 2025-11-13
-- Dependencies: 0018_seed_relationships
-- Related: ADR-K0 (location privacy), k0/policy/location_privacy.py

BEGIN;

-- ============================================================================
-- Location Privacy Fields (2 columns)
-- ============================================================================
-- Purpose: Privacy-preserving location storage with geohash masking
-- Source: Applied at K0 gate via apply_location_privacy() in k0/policy/location_privacy.py
-- Precision levels:
--   - GREEN band: 12-char geohash (~0.6m precision) = 1m
--   - AMBER band: 6-char geohash (~2.4km precision) = 5000m
--   - RED band: 4-char geohash (~39km precision) = 25000m
--
-- These fields flow from st_wal → st_hipp_store → st_epi for consistent privacy tracking
-- Note: Exact location_lat/location_lon are cleared for AMBER/RED bands in body payload

ALTER TABLE st_hipp_store ADD COLUMN location_geohash TEXT;
ALTER TABLE st_hipp_store ADD COLUMN location_precision_m INTEGER;

-- Index for geohash-based spatial queries (e.g., find memories near geohash prefix)
CREATE INDEX idx_hipp_location_geohash ON st_hipp_store(location_geohash)
  WHERE location_geohash IS NOT NULL;

-- Index for privacy audit queries (find all memories at specific precision levels)
CREATE INDEX idx_hipp_location_precision ON st_hipp_store(location_precision_m)
  WHERE location_precision_m IS NOT NULL;

COMMIT;

-- ============================================================================
-- Verification Queries (for testing)
-- ============================================================================
-- Uncomment to verify migration:
--
-- -- Check new columns exist
-- PRAGMA table_info(st_hipp_store);
--
-- -- Count total columns (should be 78: original 47 + 29 from 0013/0014/0015 + 2 new)
-- SELECT COUNT(*) as column_count FROM pragma_table_info('st_hipp_store');
--
-- -- Verify indexes created
-- SELECT name, tbl_name FROM sqlite_master
-- WHERE type = 'index'
--   AND tbl_name = 'st_hipp_store'
--   AND name IN ('idx_hipp_location_geohash', 'idx_hipp_location_precision');
--
-- -- Test NULL handling (columns should be nullable)
-- SELECT location_geohash, location_precision_m FROM st_hipp_store LIMIT 1;

-- ============================================================================
-- Migration Notes
-- ============================================================================
-- 1. Both columns are nullable (backward compatible with existing rows)
-- 2. Indexes use WHERE clauses for efficiency (partial indexes)
-- 3. These fields are populated from st_wal during P02 pipeline memory write
-- 4. Enables spatial queries without exposing exact coordinates for AMBER/RED bands
-- 5. Total st_hipp_store columns after migration: 78
