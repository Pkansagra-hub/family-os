-- k1.tools.family.shopping -- projection tables.
--
-- P7 invariant: every adapter MUST own a ``<adapter_id>_schema_version``
-- table so independent adapters can coordinate migrations without clashing.

CREATE TABLE IF NOT EXISTS shopping_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO shopping_schema_version (version) VALUES (1);

CREATE TABLE IF NOT EXISTS shopping_lists (
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
    name          TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT 'groceries'
);
CREATE INDEX IF NOT EXISTS idx_shopping_lists_space ON shopping_lists(space_id);
CREATE INDEX IF NOT EXISTS idx_shopping_lists_category ON shopping_lists(category);

CREATE TABLE IF NOT EXISTS shopping_items (
    id              TEXT PRIMARY KEY,
    space_id        TEXT NOT NULL DEFAULT '',
    actor           TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT 'native',
    source_label    TEXT NOT NULL DEFAULT '',
    visibility      TEXT NOT NULL DEFAULT 'family',
    named_visible   TEXT NOT NULL DEFAULT '[]',
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT,
    tags            TEXT NOT NULL DEFAULT '[]',
    metadata        TEXT NOT NULL DEFAULT '{}',
    list_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    quantity        TEXT,
    unit            TEXT,
    category        TEXT NOT NULL DEFAULT 'groceries',
    requested_by    TEXT NOT NULL,
    notes           TEXT,
    priority        TEXT NOT NULL DEFAULT 'medium',
    status          TEXT NOT NULL DEFAULT 'needed',
    approval_status TEXT NOT NULL DEFAULT 'approved',
    approved_by     TEXT,
    approved_at     TEXT,
    rejected_by     TEXT,
    rejected_at     TEXT,
    rejection_reason TEXT,
    checked_by      TEXT,
    checked_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_shopping_items_space ON shopping_items(space_id);
CREATE INDEX IF NOT EXISTS idx_shopping_items_list ON shopping_items(list_id);
CREATE INDEX IF NOT EXISTS idx_shopping_items_category ON shopping_items(category);
CREATE INDEX IF NOT EXISTS idx_shopping_items_requested_by ON shopping_items(requested_by);
CREATE INDEX IF NOT EXISTS idx_shopping_items_status ON shopping_items(status);
CREATE INDEX IF NOT EXISTS idx_shopping_items_approval ON shopping_items(approval_status);
