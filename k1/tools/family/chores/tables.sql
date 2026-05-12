-- k1.tools.family.chores -- projection tables (M15 §E15.4).
--
-- Three tables:
--   chore_templates    -- reusable chore definitions with recurrence schedule
--   chore_occurrences  -- individual due instances of a template
--
-- P7 invariant: every adapter MUST own a ``<adapter_id>_schema_version``
-- table so independent adapters can coordinate migrations without clashing.

CREATE TABLE IF NOT EXISTS chores_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO chores_schema_version (version) VALUES (1);

-- ── chore_templates ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chore_templates (
    -- BaseEntity universal columns
    id            TEXT PRIMARY KEY,
    space_id      TEXT NOT NULL DEFAULT '',
    actor         TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'native',
    source_label  TEXT NOT NULL DEFAULT '',
    visibility    TEXT NOT NULL DEFAULT 'family',
    named_visible TEXT NOT NULL DEFAULT '[]',   -- JSON list of member_ids
    version       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT,
    tags          TEXT NOT NULL DEFAULT '[]',   -- JSON list
    metadata      TEXT NOT NULL DEFAULT '{}',   -- JSON object
    -- entity-specific
    title         TEXT NOT NULL,
    description   TEXT,
    assigned_to   TEXT,                         -- default assignee member_id
    frequency     TEXT NOT NULL DEFAULT 'weekly',
    base_points   INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1    -- 1=active, 0=inactive
);
CREATE INDEX IF NOT EXISTS idx_chore_templates_space
    ON chore_templates(space_id);
CREATE INDEX IF NOT EXISTS idx_chore_templates_space_active
    ON chore_templates(space_id, is_active);
CREATE INDEX IF NOT EXISTS idx_chore_templates_assigned
    ON chore_templates(space_id, assigned_to);

-- ── chore_occurrences ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chore_occurrences (
    -- BaseEntity universal columns
    id            TEXT PRIMARY KEY,
    space_id      TEXT NOT NULL DEFAULT '',
    actor         TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'native',
    source_label  TEXT NOT NULL DEFAULT '',
    visibility    TEXT NOT NULL DEFAULT 'family',
    named_visible TEXT NOT NULL DEFAULT '[]',
    version       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT,
    tags          TEXT NOT NULL DEFAULT '[]',
    metadata      TEXT NOT NULL DEFAULT '{}',
    -- entity-specific
    template_id   TEXT NOT NULL,
    title         TEXT NOT NULL,                -- denormalized from template
    assigned_to   TEXT,
    due_at        TEXT,
    completed_at  TEXT,
    completed_by  TEXT,
    skipped_at    TEXT,
    skip_reason   TEXT,
    points_awarded INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (template_id) REFERENCES chore_templates(id)
);
CREATE INDEX IF NOT EXISTS idx_chore_occ_space
    ON chore_occurrences(space_id);
CREATE INDEX IF NOT EXISTS idx_chore_occ_template
    ON chore_occurrences(space_id, template_id);
CREATE INDEX IF NOT EXISTS idx_chore_occ_assigned
    ON chore_occurrences(space_id, assigned_to);
CREATE INDEX IF NOT EXISTS idx_chore_occ_status
    ON chore_occurrences(space_id, status);
CREATE INDEX IF NOT EXISTS idx_chore_occ_due
    ON chore_occurrences(space_id, status, due_at);
