-- Migration: 0017_relationships_cache_table
-- Description: Create st_relationships table for cached Neo4j family graph
-- Author: K0 Architecture Team
-- Date: 2025-11-13
-- Dependencies: 0016_space_authority_tables
-- Related ADRs: ADR-K004b (cache authority), ADR-K004c (ownership rules)

BEGIN;

-- ============================================================================
-- Relationships cache replicated from Neo4j person graph (ADR-K004b)
-- ============================================================================
CREATE TABLE IF NOT EXISTS st_relationships (
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  related_person_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  properties_json TEXT,
  source_version TEXT NOT NULL,
  hydrated_at TEXT NOT NULL,
  ttl_seconds INTEGER NOT NULL DEFAULT 3600,
  PRIMARY KEY(household_id, person_id, related_person_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_relationships_household ON st_relationships(household_id);
CREATE INDEX IF NOT EXISTS idx_relationships_person ON st_relationships(person_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON st_relationships(relationship_type);

COMMIT;

-- ============================================================================
-- Verification snippets (manual)
-- ============================================================================
-- .read k0/contracts/sql/migrations/0017_relationships_cache_table.sql
-- PRAGMA table_info('st_relationships');
-- SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_relationships%';
