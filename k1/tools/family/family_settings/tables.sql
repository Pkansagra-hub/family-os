-- k1.tools.family.family_settings tables
-- P7 invariant: every adapter SQL block must include a <adapter_id>_schema_version table.

CREATE TABLE IF NOT EXISTS family_settings_schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO family_settings_schema_version (version)
SELECT 1
WHERE NOT EXISTS (SELECT 1 FROM family_settings_schema_version);

-- ---------------------------------------------------------------------------
-- visibility_policy_docs
-- One row per space_id (soft-delete aware; service enforces 1-active invariant).
-- Inherits the full BaseEntity projection columns.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS visibility_policy_docs (
    id                  TEXT    NOT NULL PRIMARY KEY,
    space_id            TEXT    NOT NULL DEFAULT '',
    actor               TEXT    NOT NULL DEFAULT '',
    source              TEXT    NOT NULL DEFAULT 'native',
    source_label        TEXT    NOT NULL DEFAULT '',
    visibility          TEXT    NOT NULL DEFAULT 'private',
    named_visible       TEXT    NOT NULL DEFAULT '[]',    -- JSON array
    version             INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    deleted_at          TEXT,
    tags                TEXT    NOT NULL DEFAULT '[]',    -- JSON array
    metadata            TEXT    NOT NULL DEFAULT '{}',   -- JSON object
    -- domain columns
    rules               TEXT    NOT NULL DEFAULT '{}',   -- JSON object
    sensitive_keywords  TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    kid_capabilities    TEXT    NOT NULL DEFAULT '{}'    -- JSON object
);

CREATE INDEX IF NOT EXISTS idx_vpd_space_active
    ON visibility_policy_docs (space_id)
    WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- feature_flags
-- Named boolean flags; unique on (space_id, flag_name) among live rows.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS feature_flags (
    id                  TEXT    NOT NULL PRIMARY KEY,
    space_id            TEXT    NOT NULL DEFAULT '',
    actor               TEXT    NOT NULL DEFAULT '',
    source              TEXT    NOT NULL DEFAULT 'native',
    source_label        TEXT    NOT NULL DEFAULT '',
    visibility          TEXT    NOT NULL DEFAULT 'private',
    named_visible       TEXT    NOT NULL DEFAULT '[]',
    version             INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    deleted_at          TEXT,
    tags                TEXT    NOT NULL DEFAULT '[]',
    metadata            TEXT    NOT NULL DEFAULT '{}',
    -- domain columns
    flag_name           TEXT    NOT NULL,
    enabled             INTEGER NOT NULL DEFAULT 0,      -- SQLite bool
    description         TEXT    NOT NULL DEFAULT '',
    scope               TEXT    NOT NULL DEFAULT 'space',
    target_member_id    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ff_space_flag_active
    ON feature_flags (space_id, flag_name)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ff_space
    ON feature_flags (space_id);
