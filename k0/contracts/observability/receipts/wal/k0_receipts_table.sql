-- K0 Receipts Table Schema
-- ADR-0038b: K0 WAL Integration & Async Writes
-- Research: SQLite WAL mode, append-only logging, crash recovery

-- Enable WAL mode for concurrent reads/writes and crash recovery
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;  -- Balance performance vs durability
PRAGMA wal_autocheckpoint = 1000;  -- Checkpoint every 1000 pages
PRAGMA cache_size = -64000;  -- 64MB cache for performance
PRAGMA temp_store = MEMORY;  -- Temp tables in memory

-- Receipts table with hash chain integrity
CREATE TABLE IF NOT EXISTS receipts (
    -- Primary identifiers
    receipt_id TEXT PRIMARY KEY,  -- UUID v4
    session_id TEXT NOT NULL,
    space_id TEXT NOT NULL,
    user_id TEXT NOT NULL,

    -- Receipt metadata
    receipt_type TEXT NOT NULL CHECK (receipt_type IN ('TURN', 'TOOL', 'STATE', 'AGENT')),
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED')),
    timestamp INTEGER NOT NULL,  -- Unix timestamp in milliseconds

    -- Hash chain for tamper-evident audit trail
    previous_hash TEXT,  -- SHA-256 hash of previous receipt (NULL for first)
    current_hash TEXT NOT NULL,  -- SHA-256 hash of this receipt

    -- FlatBuffers serialized payload (compressed)
    payload BLOB NOT NULL,

    -- Additional metadata for querying
    turn_number INTEGER,  -- For TURN receipts
    tool_name TEXT,  -- For TOOL receipts
    agent_id TEXT,  -- For AGENT receipts
    section TEXT,  -- For STATE receipts

    -- Performance tracking
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
    batch_id TEXT,  -- For batch write tracking

    -- Constraints
    UNIQUE(session_id, timestamp),  -- Prevent duplicate timestamps per session
    CHECK (length(receipt_id) = 36),  -- UUID validation
    CHECK (length(current_hash) = 64),  -- SHA-256 hex length
    CHECK (previous_hash IS NULL OR length(previous_hash) = 64)
);

-- Indexes for query performance (<50ms query budget)
CREATE INDEX IF NOT EXISTS idx_receipts_session_timestamp
ON receipts(session_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_user_timestamp
ON receipts(user_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_privacy_band_timestamp
ON receipts(privacy_band, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_type_timestamp
ON receipts(receipt_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_batch_id
ON receipts(batch_id);

-- Partial indexes for common queries
CREATE INDEX IF NOT EXISTS idx_receipts_session_recent
ON receipts(session_id, timestamp DESC)
WHERE timestamp > (strftime('%s', 'now') - 86400) * 1000;  -- Last 24 hours

CREATE INDEX IF NOT EXISTS idx_receipts_user_recent
ON receipts(user_id, timestamp DESC)
WHERE timestamp > (strftime('%s', 'now') - 86400) * 1000;

-- Hash chain integrity verification index
CREATE INDEX IF NOT EXISTS idx_receipts_hash_chain
ON receipts(session_id, previous_hash, current_hash);

-- Retention policy support (for auto-deletion)
CREATE INDEX IF NOT EXISTS idx_receipts_retention
ON receipts(privacy_band, timestamp);

-- Statistics and monitoring
CREATE TABLE IF NOT EXISTS receipt_stats (
    stat_date DATE PRIMARY KEY,
    total_receipts INTEGER NOT NULL DEFAULT 0,
    receipts_by_type TEXT NOT NULL,  -- JSON: {"TURN": 100, "TOOL": 50, ...}
    receipts_by_band TEXT NOT NULL,  -- JSON: {"GREEN": 120, "AMBER": 30, ...}
    avg_creation_latency_ms REAL,
    total_size_bytes INTEGER,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
);

-- Batch write tracking for performance monitoring
CREATE TABLE IF NOT EXISTS receipt_batches (
    batch_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    receipt_count INTEGER NOT NULL,
    total_size_bytes INTEGER NOT NULL,
    write_start_ms INTEGER NOT NULL,
    write_end_ms INTEGER,
    fsync_duration_ms INTEGER,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
);

-- WAL checkpoint statistics
CREATE TABLE IF NOT EXISTS wal_checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_start_ms INTEGER NOT NULL,
    checkpoint_end_ms INTEGER NOT NULL,
    pages_written INTEGER NOT NULL,
    pages_synced INTEGER NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
);

-- Triggers for automatic statistics updates
CREATE TRIGGER IF NOT EXISTS update_receipt_stats
AFTER INSERT ON receipts
BEGIN
    INSERT OR REPLACE INTO receipt_stats (stat_date, total_receipts, receipts_by_type, receipts_by_band)
    SELECT
        date('now'),
        COUNT(*),
        json_group_object(receipt_type, COUNT(*)),
        json_group_object(privacy_band, COUNT(*))
    FROM receipts
    WHERE date(created_at / 1000, 'unixepoch') = date('now');
END;

-- Performance validation views
CREATE VIEW IF NOT EXISTS receipt_performance AS
SELECT
    receipt_type,
    COUNT(*) as count,
    AVG(created_at - timestamp) as avg_write_latency_ms,
    MAX(created_at - timestamp) as max_write_latency_ms,
    MIN(created_at - timestamp) as min_write_latency_ms
FROM receipts
WHERE created_at - timestamp < 100  -- Only recent writes
GROUP BY receipt_type;

-- Hash chain verification view
CREATE VIEW IF NOT EXISTS hash_chain_verification AS
SELECT
    r1.session_id,
    r1.receipt_id,
    r1.current_hash as r1_hash,
    r2.previous_hash as r2_previous_hash,
    CASE WHEN r1.current_hash = r2.previous_hash THEN 'VALID' ELSE 'BROKEN' END as chain_status
FROM receipts r1
LEFT JOIN receipts r2 ON r1.session_id = r2.session_id
    AND r2.timestamp = (SELECT MIN(timestamp) FROM receipts WHERE session_id = r1.session_id AND timestamp > r1.timestamp)
WHERE r1.current_hash IS NOT NULL;

-- Data integrity constraints
CREATE TRIGGER IF NOT EXISTS validate_hash_chain
BEFORE INSERT ON receipts
FOR EACH ROW
WHEN NEW.previous_hash IS NOT NULL
BEGIN
    SELECT CASE
        WHEN NOT EXISTS (
            SELECT 1 FROM receipts
            WHERE session_id = NEW.session_id
            AND current_hash = NEW.previous_hash
        ) THEN RAISE(ABORT, 'Invalid previous hash - chain broken')
    END;
END;

-- Performance monitoring triggers
CREATE TRIGGER IF NOT EXISTS monitor_batch_performance
AFTER INSERT ON receipt_batches
FOR EACH ROW
WHEN NEW.fsync_duration_ms > 5  -- >5ms fsync violates budget
BEGIN
    -- Log performance violation (would integrate with observability system)
    SELECT RAISE(IGNORE);  -- Just log, don't fail the insert
END;