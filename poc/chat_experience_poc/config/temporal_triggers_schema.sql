-- Temporal Triggers Schema
-- Purpose: Store time-based triggers for proactive features
-- Location: poc/chat_experience_poc/config/temporal_triggers_schema.sql
-- Database: SQLite
--
-- Trigger Types:
--   - TimeBasedTrigger: Fire at specific time (e.g., 8:00am)
--   - RecurringTrigger: Fire on schedule (e.g., every 4 hours, daily, weekly)
--   - PatternTrigger: Fire based on detected patterns (e.g., "milk day")
--   - AnomalyTrigger: Fire on unusual activity

-- Main triggers table
CREATE TABLE IF NOT EXISTS temporal_triggers (
    -- Identification
    trigger_id TEXT PRIMARY KEY,          -- UUID
    trigger_type TEXT NOT NULL,           -- "time_based", "recurring", "pattern", "anomaly"

    -- Scheduling
    fire_time TEXT NOT NULL,              -- ISO 8601 datetime (next fire time)
    recurrence TEXT,                      -- NULL or "4h", "daily", "weekly", "monthly"

    -- Trigger content
    message TEXT NOT NULL,                -- Notification text
    action TEXT NOT NULL,                 -- What to do when fired (JSON)
    metadata TEXT,                        -- Additional context (JSON)

    -- User association
    user_id TEXT NOT NULL,                -- User this trigger belongs to
    session_id TEXT,                      -- Optional session context

    -- State management
    active BOOLEAN NOT NULL DEFAULT 1,    -- 1=active, 0=soft deleted
    fire_count INTEGER NOT NULL DEFAULT 0, -- How many times fired
    last_fired TEXT,                      -- ISO 8601 datetime (last fire time)

    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_triggers_fire_time ON temporal_triggers(fire_time);
CREATE INDEX IF NOT EXISTS idx_triggers_active ON temporal_triggers(active);
CREATE INDEX IF NOT EXISTS idx_triggers_user_id ON temporal_triggers(user_id);
CREATE INDEX IF NOT EXISTS idx_triggers_type ON temporal_triggers(trigger_type);

-- Trigger history (for audit trail)
CREATE TABLE IF NOT EXISTS trigger_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_id TEXT NOT NULL,
    fire_time TEXT NOT NULL,              -- When it actually fired
    status TEXT NOT NULL,                 -- "success", "error", "skipped"
    error_message TEXT,                   -- Error details if failed
    execution_time_ms REAL,               -- How long execution took
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (trigger_id) REFERENCES temporal_triggers(trigger_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_trigger_id ON trigger_history(trigger_id);
CREATE INDEX IF NOT EXISTS idx_history_fire_time ON trigger_history(fire_time);

-- Auto-update updated_at timestamp on triggers table
CREATE TRIGGER IF NOT EXISTS update_triggers_timestamp
AFTER UPDATE ON temporal_triggers
FOR EACH ROW
BEGIN
    UPDATE temporal_triggers
    SET updated_at = datetime('now')
    WHERE trigger_id = NEW.trigger_id;
END;

-- ============================================================
-- SCHEMA DOCUMENTATION
-- ============================================================

-- Trigger Types:
--
-- 1. TIME_BASED:
--    - Fire at specific time
--    - Example: "Remind me at 8:00am to take medication"
--    - recurrence: NULL
--    - fire_time: "2025-11-06T08:00:00Z"
--
-- 2. RECURRING:
--    - Fire on schedule
--    - Example: "Remind me every 4 hours to drink water"
--    - recurrence: "4h", "daily", "weekly", "monthly"
--    - fire_time: next occurrence (auto-updated after firing)
--
-- 3. PATTERN:
--    - Fire based on detected patterns
--    - Example: "Today might be milk day" (detected from calendar pattern)
--    - recurrence: NULL (pattern engine reschedules)
--    - fire_time: when pattern detected
--
-- 4. ANOMALY:
--    - Fire on unusual activity
--    - Example: "You haven't logged exercise in 3 days"
--    - recurrence: NULL (anomaly detector reschedules)
--    - fire_time: when anomaly detected

-- Action Format (JSON):
-- {
--   "type": "notification" | "execute_task" | "run_agent",
--   "target": "user" | "agent_id",
--   "params": {...}
-- }

-- Metadata Format (JSON):
-- {
--   "priority": "urgent" | "standard" | "low",
--   "category": "health" | "work" | "family" | "finance",
--   "source": "user_request" | "pattern_detector" | "anomaly_detector",
--   "related_entities": ["entity_id_1", "entity_id_2"]
-- }

-- Recurrence Format:
-- - "4h" = every 4 hours
-- - "daily" = every day at same time
-- - "weekly" = every week on same day
-- - "monthly" = every month on same date
-- - "2d" = every 2 days
-- - "30m" = every 30 minutes

-- Performance Targets:
-- - Trigger lookup: <5ms P95
-- - Trigger insert: <10ms P95
-- - Scheduler query: <10ms P95 (for all due triggers)
-- - History insert: <5ms P95
