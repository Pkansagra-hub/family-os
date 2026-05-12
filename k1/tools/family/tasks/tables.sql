-- k1.tools.family.tasks -- projection tables (M15 §E15.2).
--
-- Three tables:
--   task_lists   -- named task buckets (optional grouping)
--   task_items   -- one-shot to-do items
--
-- P7 invariant: every adapter MUST own a ``<adapter_id>_schema_version``
-- table so independent adapters can coordinate migrations without clashing.

CREATE TABLE IF NOT EXISTS tasks_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO tasks_schema_version (version) VALUES (1);

-- ── task_lists ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_lists (
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
    name          TEXT NOT NULL,
    color         TEXT                          -- optional hex string
);
CREATE INDEX IF NOT EXISTS idx_task_lists_space  ON task_lists(space_id);

-- ── task_items ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_items (
    -- BaseEntity universal columns
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
    -- entity-specific
    title           TEXT NOT NULL,
    list_id         TEXT,                        -- FK → task_lists.id (soft ref)
    assigned_to     TEXT,                        -- member_id; NULL = unassigned
    due_at          TEXT,                        -- ISO 8601 deadline
    priority        TEXT NOT NULL DEFAULT 'medium',
    status          TEXT NOT NULL DEFAULT 'open',
    completed_at    TEXT,                        -- set by complete_task
    linked_event_id TEXT                         -- soft FK → calendar_events.id
);
CREATE INDEX IF NOT EXISTS idx_task_items_space       ON task_items(space_id);
CREATE INDEX IF NOT EXISTS idx_task_items_assigned_to ON task_items(assigned_to);
CREATE INDEX IF NOT EXISTS idx_task_items_status      ON task_items(status);
CREATE INDEX IF NOT EXISTS idx_task_items_due_at      ON task_items(due_at);
CREATE INDEX IF NOT EXISTS idx_task_items_list_id     ON task_items(list_id);
