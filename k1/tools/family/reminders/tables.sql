-- k1/tools/family/reminders/tables.sql
-- P7: every adapter DDL must contain a <adapter_id>_schema_version table.
-- BaseEntity universal columns appear in every table; entity-specific columns follow.

CREATE TABLE IF NOT EXISTS reminders_schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS reminders (
    -- BaseEntity universal columns
    id              TEXT    NOT NULL PRIMARY KEY,
    space_id        TEXT    NOT NULL DEFAULT '',
    actor           TEXT    NOT NULL DEFAULT '',
    source          TEXT    NOT NULL DEFAULT 'native',
    source_label    TEXT,
    visibility      TEXT    NOT NULL DEFAULT 'family',
    named_visible   TEXT    NOT NULL DEFAULT '[]',
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT,
    updated_at      TEXT,
    deleted_at      TEXT,
    tags            TEXT    NOT NULL DEFAULT '[]',
    metadata        TEXT    NOT NULL DEFAULT '{}',

    -- Reminder-specific columns
    title           TEXT    NOT NULL,
    recipient       TEXT    NOT NULL,
    trigger         TEXT    NOT NULL DEFAULT '{}',   -- JSON-serialised ReminderTrigger
    message         TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'scheduled',
    snoozed_until   TEXT,
    fired_at        TEXT,
    linked_event_id TEXT
);

-- Primary isolation: every query is space-scoped
CREATE INDEX IF NOT EXISTS idx_reminders_space
    ON reminders(space_id);

-- "Show my reminders" — most common read path
CREATE INDEX IF NOT EXISTS idx_reminders_recipient
    ON reminders(recipient);

-- Lifecycle filter: pending vs fired vs dismissed
CREATE INDEX IF NOT EXISTS idx_reminders_status
    ON reminders(status);

-- Scheduler poll: SELECT WHERE status='scheduled' AND fire_at <= :now
-- fire_at is embedded inside the trigger JSON blob, but we also expose
-- the extracted value for index-friendly polling.
CREATE INDEX IF NOT EXISTS idx_reminders_space_status_fire
    ON reminders(space_id, status, snoozed_until);
