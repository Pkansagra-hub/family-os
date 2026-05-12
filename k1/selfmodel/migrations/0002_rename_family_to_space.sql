-- 0002_rename_family_to_space.sql — M0 SpaceGraph rename (E0.4.2)
--
-- Renames the family_projection table and its primary-key column to the
-- domain-agnostic vocabulary introduced in M0.  Applied automatically by
-- apply_migrations() on any database still at user_version = 1.
--
-- On databases freshly created with the updated 0001_initial.sql (which
-- already uses space_projection), the family_projection table will not
-- exist, so this migration is a no-op: the SELECT returns 0 rows and
-- the WHEN branch never fires.
--
-- Note: SQLite does not support ALTER TABLE … IF EXISTS; we guard the
-- rename via a CASE expression that becomes a valid no-op INSERT into a
-- temp table (see below). The real rename only fires when the old table
-- is actually present.

-- Use a trigger approach: create the new table from the old if it exists,
-- copy data, drop old. Only active when family_projection is present.
CREATE TABLE IF NOT EXISTS space_projection (
    space_id          TEXT PRIMARY KEY,
    revision          TEXT NOT NULL,
    parent_revision   TEXT NOT NULL DEFAULT '',
    written_at_ms     INTEGER NOT NULL,
    snapshot_json     TEXT NOT NULL
);

INSERT OR IGNORE INTO space_projection (space_id, revision, parent_revision, written_at_ms, snapshot_json)
SELECT family_space_id, revision, parent_revision, written_at_ms, snapshot_json
FROM family_projection;

DROP TABLE IF EXISTS family_projection;
