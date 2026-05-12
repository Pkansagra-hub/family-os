-- k1.tools.family.calendar -- projection tables (M15 §E15.1).
--
-- Two tables:
--   calendar_events  -- persisted CalendarEvent rows
--   calendar_feeds   -- persisted ExternalFeed bindings (M15: enabled=0)
--
-- P7 invariant: every adapter MUST own a ``<adapter_id>_schema_version``
-- table so independent adapters can coordinate migrations without
-- clashing.  Version 1 is the M15-shipped shape below.

CREATE TABLE IF NOT EXISTS calendar_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO calendar_schema_version (version) VALUES (1);

CREATE TABLE IF NOT EXISTS calendar_events (
    id              TEXT PRIMARY KEY,
    space_id        TEXT NOT NULL DEFAULT '',
    actor           TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT 'native',
    source_label    TEXT NOT NULL DEFAULT '',
    visibility      TEXT NOT NULL DEFAULT 'family',
    named_visible   TEXT NOT NULL DEFAULT '[]',   -- JSON list of member_ids
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT,
    tags            TEXT NOT NULL DEFAULT '[]',   -- JSON list
    metadata        TEXT NOT NULL DEFAULT '{}',   -- JSON object
    -- entity-specific
    title           TEXT NOT NULL,
    start           TEXT NOT NULL,
    "end"           TEXT NOT NULL,
    location        TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    attendees       TEXT NOT NULL DEFAULT '[]',   -- JSON list of member_ids
    rrule           TEXT,
    response        TEXT
);
CREATE INDEX IF NOT EXISTS idx_calendar_events_space  ON calendar_events(space_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_start  ON calendar_events(start);
CREATE INDEX IF NOT EXISTS idx_calendar_events_source ON calendar_events(source);

CREATE TABLE IF NOT EXISTS calendar_feeds (
    id              TEXT PRIMARY KEY,
    space_id        TEXT NOT NULL DEFAULT '',
    actor           TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT 'native',
    source_label    TEXT NOT NULL DEFAULT '',
    visibility      TEXT NOT NULL DEFAULT 'adults',
    named_visible   TEXT NOT NULL DEFAULT '[]',
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT,
    tags            TEXT NOT NULL DEFAULT '[]',
    metadata        TEXT NOT NULL DEFAULT '{}',
    member_id       TEXT NOT NULL,
    feed_source     TEXT NOT NULL,
    account         TEXT NOT NULL,
    sync_token      TEXT,
    enabled         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_calendar_feeds_space  ON calendar_feeds(space_id);
CREATE INDEX IF NOT EXISTS idx_calendar_feeds_member ON calendar_feeds(member_id);
