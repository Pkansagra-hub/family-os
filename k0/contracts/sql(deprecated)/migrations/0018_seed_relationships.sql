-- Migration 0018: Seed st_relationships for joint household
-- ADR-K004b: Replicate Neo4j family graph into SQLite cache
BEGIN;

-- Joint household with Prince, Jeel, Sharvi, and extended family
-- All grandparents/parents designated as CARETAKER_OF Sharvi (minor)

-- Prince's grandparents (Vitthalbhai & Bhanuben)
INSERT INTO st_relationships (household_id, person_id, related_person_id, relationship_type, properties_json, source_version, hydrated_at, ttl_seconds)
VALUES
  ('household_001', 'person_vitthalbhai_001', 'person_bhanuben_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_bhanuben_001', 'person_vitthalbhai_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_vitthalbhai_001', 'person_lalit_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_bhanuben_001', 'person_lalit_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600);

-- Prince's parents (Lalit & Kanchan)
INSERT INTO st_relationships (household_id, person_id, related_person_id, relationship_type, properties_json, source_version, hydrated_at, ttl_seconds)
VALUES
  ('household_001', 'person_lalit_001', 'person_kanchan_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_kanchan_001', 'person_lalit_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_lalit_001', 'person_prince_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_kanchan_001', 'person_prince_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600);

-- Jeel's parents (Girishbhai & Geetaben)
INSERT INTO st_relationships (household_id, person_id, related_person_id, relationship_type, properties_json, source_version, hydrated_at, ttl_seconds)
VALUES
  ('household_001', 'person_girishbhai_001', 'person_geetaben_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_geetaben_001', 'person_girishbhai_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_girishbhai_001', 'person_jeel_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_geetaben_001', 'person_jeel_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600);

-- Nuclear family (Prince & Jeel are spouses, parents of Sharvi)
INSERT INTO st_relationships (household_id, person_id, related_person_id, relationship_type, properties_json, source_version, hydrated_at, ttl_seconds)
VALUES
  ('household_001', 'person_prince_001', 'person_jeel_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_jeel_001', 'person_prince_001', 'SPOUSE_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_prince_001', 'person_sharvi_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_jeel_001', 'person_sharvi_001', 'PARENT_OF', '{}', 'migration_0018', datetime('now'), 3600);

-- Caretaker delegations: Grandparents can act on behalf of Sharvi (minor)
-- ADR-K004c: Caretaker authority for guardianship scenarios
INSERT INTO st_relationships (household_id, person_id, related_person_id, relationship_type, properties_json, source_version, hydrated_at, ttl_seconds)
VALUES
  ('household_001', 'person_lalit_001', 'person_sharvi_001', 'CARETAKER_OF', '{"delegated_by": "person_prince_001"}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_kanchan_001', 'person_sharvi_001', 'CARETAKER_OF', '{"delegated_by": "person_prince_001"}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_girishbhai_001', 'person_sharvi_001', 'CARETAKER_OF', '{"delegated_by": "person_jeel_001"}', 'migration_0018', datetime('now'), 3600),
  ('household_001', 'person_geetaben_001', 'person_sharvi_001', 'CARETAKER_OF', '{"delegated_by": "person_jeel_001"}', 'migration_0018', datetime('now'), 3600);

COMMIT;
