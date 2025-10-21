-- Pruning Job History Table Schema
-- ADR-0038c: Retention Policies & Auto-Deletion
-- Research: Job execution tracking, failure recovery, compliance auditing

-- Track all pruning job executions for monitoring and compliance
CREATE TABLE IF NOT EXISTS pruning_job_history (
    -- Job execution identifiers
    job_id TEXT PRIMARY KEY,  -- UUID v4
    execution_sequence INTEGER,  -- Auto-incrementing sequence per job type

    -- Execution metadata
    status TEXT NOT NULL CHECK (status IN (
        'PENDING', 'RUNNING', 'COMPLETED', 'DRY_RUN_COMPLETED',
        'FAILED', 'SKIPPED', 'CANCELLED'
    )),
    start_time INTEGER NOT NULL,  -- Unix timestamp in milliseconds
    end_time INTEGER,  -- Unix timestamp in milliseconds (NULL if running)

    -- Job configuration
    dry_run BOOLEAN NOT NULL DEFAULT 0,
    force_execution BOOLEAN NOT NULL DEFAULT 0,
    triggered_by TEXT,  -- 'SCHEDULER', 'MANUAL', 'API'

    -- Execution results
    receipts_deleted INTEGER DEFAULT 0,
    eligible_for_deletion INTEGER DEFAULT 0,
    duration_ms INTEGER,  -- Computed as end_time - start_time

    -- Error information
    error_message TEXT,
    error_type TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Performance metrics
    peak_memory_mb REAL,
    cpu_usage_percent REAL,
    db_connections_used INTEGER,

    -- System context
    hostname TEXT,
    process_id INTEGER,
    thread_id TEXT,

    -- Audit trail
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),

    -- Constraints
    CHECK (length(job_id) = 36),  -- UUID validation
    CHECK (end_time IS NULL OR end_time >= start_time),  -- End after start
    CHECK (receipts_deleted >= 0),
    CHECK (eligible_for_deletion >= 0),
    CHECK (retry_count >= 0)
);

-- Indexes for job monitoring and compliance queries
CREATE INDEX IF NOT EXISTS idx_pruning_jobs_status_time
ON pruning_job_history(status, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_pruning_jobs_start_time
ON pruning_job_history(start_time DESC);

CREATE INDEX IF NOT EXISTS idx_pruning_jobs_end_time
ON pruning_job_history(end_time DESC) WHERE end_time IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pruning_jobs_duration
ON pruning_job_history(duration_ms DESC) WHERE duration_ms IS NOT NULL;

-- Partial indexes for common queries
CREATE INDEX IF NOT EXISTS idx_pruning_jobs_failed_recent
ON pruning_job_history(start_time DESC)
WHERE status = 'FAILED'
  AND start_time > (strftime('%s', 'now') - 7*24*3600) * 1000;  -- Last 7 days

CREATE INDEX IF NOT EXISTS idx_pruning_jobs_running
ON pruning_job_history(start_time DESC)
WHERE status = 'RUNNING';

CREATE INDEX IF NOT EXISTS idx_pruning_jobs_long_running
ON pruning_job_history(start_time DESC)
WHERE status = 'RUNNING'
  AND start_time < (strftime('%s', 'now') - 3600) * 1000;  -- Running >1 hour

-- Views for monitoring and compliance
CREATE VIEW IF NOT EXISTS pruning_job_summary AS
SELECT
    status,
    COUNT(*) as job_count,
    AVG(duration_ms) as avg_duration_ms,
    MIN(duration_ms) as min_duration_ms,
    MAX(duration_ms) as max_duration_ms,
    SUM(receipts_deleted) as total_receipts_deleted,
    AVG(receipts_deleted) as avg_receipts_deleted
FROM pruning_job_history
WHERE end_time IS NOT NULL
GROUP BY status
ORDER BY job_count DESC;

-- Daily job execution summary
CREATE VIEW IF NOT EXISTS pruning_job_daily_summary AS
SELECT
    date(start_time / 1000, 'unixepoch') as execution_date,
    COUNT(*) as total_jobs,
    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed_jobs,
    COUNT(CASE WHEN status = 'FAILED' THEN 1 END) as failed_jobs,
    COUNT(CASE WHEN status = 'SKIPPED' THEN 1 END) as skipped_jobs,
    SUM(receipts_deleted) as total_receipts_deleted,
    AVG(duration_ms) as avg_duration_ms,
    MAX(duration_ms) as max_duration_ms
FROM pruning_job_history
WHERE start_time > (strftime('%s', 'now') - 30*24*3600) * 1000  -- Last 30 days
GROUP BY execution_date
ORDER BY execution_date DESC;

-- Job failure analysis view
CREATE VIEW IF NOT EXISTS pruning_job_failure_analysis AS
SELECT
    error_type,
    error_message,
    COUNT(*) as failure_count,
    AVG(retry_count) as avg_retries,
    MIN(start_time) as first_failure,
    MAX(start_time) as last_failure,
    AVG(duration_ms) as avg_failure_duration
FROM pruning_job_history
WHERE status = 'FAILED'
  AND start_time > (strftime('%s', 'now') - 30*24*3600) * 1000  -- Last 30 days
GROUP BY error_type, error_message
ORDER BY failure_count DESC;

-- Performance tracking view
CREATE VIEW IF NOT EXISTS pruning_job_performance AS
SELECT
    job_id,
    start_time,
    duration_ms,
    receipts_deleted,
    peak_memory_mb,
    cpu_usage_percent,
    CASE
        WHEN duration_ms > 5000 THEN 'OVER_BUDGET'
        WHEN receipts_deleted > 10000 THEN 'HIGH_VOLUME'
        WHEN retry_count > 0 THEN 'RETRIED'
        ELSE 'NORMAL'
    END as performance_category
FROM pruning_job_history
WHERE status = 'COMPLETED'
  AND start_time > (strftime('%s', 'now') - 7*24*3600) * 1000  -- Last 7 days
ORDER BY start_time DESC;

-- Triggers for automatic metadata management
CREATE TRIGGER IF NOT EXISTS update_pruning_job_updated_at
AFTER UPDATE ON pruning_job_history
FOR EACH ROW
BEGIN
    UPDATE pruning_job_history
    SET updated_at = (strftime('%s', 'now') * 1000)
    WHERE job_id = NEW.job_id;
END;

-- Trigger to compute duration_ms automatically
CREATE TRIGGER IF NOT EXISTS compute_pruning_job_duration
BEFORE UPDATE ON pruning_job_history
FOR EACH ROW
WHEN NEW.end_time IS NOT NULL AND NEW.duration_ms IS NULL
BEGIN
    SELECT (NEW.end_time - NEW.start_time)
    INTO NEW.duration_ms;
END;

-- Trigger to assign execution sequence
CREATE TRIGGER IF NOT EXISTS assign_pruning_job_sequence
BEFORE INSERT ON pruning_job_history
FOR EACH ROW
BEGIN
    SELECT COALESCE(MAX(execution_sequence), 0) + 1
    FROM pruning_job_history
    INTO NEW.execution_sequence;
END;

-- Job execution statistics table
CREATE TABLE IF NOT EXISTS pruning_job_statistics (
    stat_date DATE PRIMARY KEY,
    total_jobs INTEGER NOT NULL DEFAULT 0,
    completed_jobs INTEGER NOT NULL DEFAULT 0,
    failed_jobs INTEGER NOT NULL DEFAULT 0,
    skipped_jobs INTEGER NOT NULL DEFAULT 0,
    total_receipts_deleted INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms REAL,
    max_duration_ms INTEGER,
    total_retry_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
);

-- Automatic statistics updates
CREATE TRIGGER IF NOT EXISTS update_pruning_job_stats
AFTER INSERT ON pruning_job_history
FOR EACH ROW
WHEN NEW.end_time IS NOT NULL
BEGIN
    INSERT OR REPLACE INTO pruning_job_statistics (
        stat_date, total_jobs, completed_jobs, failed_jobs, skipped_jobs,
        total_receipts_deleted, avg_duration_ms, max_duration_ms, total_retry_count
    )
    SELECT
        date('now'),
        COUNT(*),
        COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END),
        COUNT(CASE WHEN status = 'FAILED' THEN 1 END),
        COUNT(CASE WHEN status = 'SKIPPED' THEN 1 END),
        COALESCE(SUM(receipts_deleted), 0),
        AVG(duration_ms),
        MAX(duration_ms),
        COALESCE(SUM(retry_count), 0)
    FROM pruning_job_history
    WHERE date(start_time / 1000, 'unixepoch') = date('now')
      AND end_time IS NOT NULL;
END;

-- Cleanup policy for job history (keep 90 days)
CREATE TABLE IF NOT EXISTS pruning_job_cleanup_policy (
    policy_id INTEGER PRIMARY KEY CHECK (policy_id = 1),  -- Singleton table
    max_history_age_days INTEGER NOT NULL DEFAULT 90,
    last_cleanup_timestamp INTEGER,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
);

-- Insert default cleanup policy
INSERT OR IGNORE INTO pruning_job_cleanup_policy (policy_id, max_history_age_days) VALUES (1, 90);