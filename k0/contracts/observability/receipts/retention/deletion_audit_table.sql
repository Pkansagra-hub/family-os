-- Deletion Audit Table Schema
-- ADR-0038c: Retention Policies & Auto-Deletion
-- Research: GDPR Article 30 (processing records), audit trail integrity

-- Audit table for all receipt deletions (compliance requirement)
CREATE TABLE IF NOT EXISTS deletion_audit (
    -- Audit record identifier
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    deletion_timestamp INTEGER NOT NULL,  -- Unix timestamp in milliseconds

    -- Receipt information at time of deletion
    receipt_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED')),

    -- Deletion metadata
    deletion_reason TEXT NOT NULL CHECK (deletion_reason IN (
        'RETENTION_POLICY_EXPIRED',
        'USER_REQUEST_GDPR_ERASURE',
        'ADMINISTRATIVE_PURGE',
        'SYSTEM_MAINTENANCE'
    )),
    deleted_by TEXT,  -- User/system that initiated deletion
    deletion_batch_id TEXT,  -- Batch identifier for bulk deletions

    -- Additional audit information
    receipt_age_days INTEGER,  -- Age of receipt at deletion time
    original_timestamp INTEGER,  -- Original receipt timestamp
    hash_chain_position INTEGER,  -- Position in hash chain (for integrity verification)

    -- Compliance tracking
    gdpr_legal_basis TEXT,  -- Legal basis for deletion (GDPR Article 6/17)
    hipaa_authorization TEXT,  -- HIPAA authorization reference if applicable
    soc2_control_reference TEXT,  -- SOC2 control reference

    -- System metadata
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
    retention_check_timestamp INTEGER,  -- When retention policy was evaluated

    -- Constraints
    UNIQUE(receipt_id),  -- Each receipt can only be deleted once
    CHECK (length(receipt_id) = 36),  -- UUID validation
    CHECK (deletion_timestamp >= original_timestamp),  -- Can't delete future receipts
    CHECK (receipt_age_days >= 0)  -- Age must be non-negative
);

-- Indexes for audit trail queries (GDPR Article 15 compliance)
CREATE INDEX IF NOT EXISTS idx_deletion_audit_user_timestamp
ON deletion_audit(user_id, deletion_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_deletion_audit_privacy_band_timestamp
ON deletion_audit(privacy_band, deletion_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_deletion_audit_reason_timestamp
ON deletion_audit(deletion_reason, deletion_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_deletion_audit_batch_id
ON deletion_audit(deletion_batch_id);

-- Partial indexes for common compliance queries
CREATE INDEX IF NOT EXISTS idx_deletion_audit_gdpr_recent
ON deletion_audit(user_id, deletion_timestamp DESC)
WHERE deletion_reason = 'USER_REQUEST_GDPR_ERASURE'
  AND deletion_timestamp > (strftime('%s', 'now') - 365*24*3600) * 1000;  -- Last year

CREATE INDEX IF NOT EXISTS idx_deletion_audit_retention_recent
ON deletion_audit(privacy_band, deletion_timestamp DESC)
WHERE deletion_reason = 'RETENTION_POLICY_EXPIRED'
  AND deletion_timestamp > (strftime('%s', 'now') - 30*24*3600) * 1000;  -- Last 30 days

-- Views for compliance reporting
CREATE VIEW IF NOT EXISTS deletion_compliance_summary AS
SELECT
    privacy_band,
    deletion_reason,
    COUNT(*) as deletion_count,
    MIN(deletion_timestamp) as earliest_deletion,
    MAX(deletion_timestamp) as latest_deletion,
    AVG(receipt_age_days) as avg_age_at_deletion
FROM deletion_audit
WHERE deletion_timestamp > (strftime('%s', 'now') - 90*24*3600) * 1000  -- Last 90 days
GROUP BY privacy_band, deletion_reason
ORDER BY privacy_band, deletion_count DESC;

-- GDPR Article 15 export view (user's right to access processing records)
CREATE VIEW IF NOT EXISTS gdpr_deletion_history AS
SELECT
    user_id,
    deletion_timestamp,
    receipt_id,
    privacy_band,
    deletion_reason,
    gdpr_legal_basis,
    receipt_age_days,
    CASE
        WHEN deletion_reason = 'USER_REQUEST_GDPR_ERASURE' THEN 'User Initiated'
        WHEN deletion_reason = 'RETENTION_POLICY_EXPIRED' THEN 'Automated Retention'
        ELSE 'Administrative'
    END as deletion_category
FROM deletion_audit
ORDER BY user_id, deletion_timestamp DESC;

-- Retention policy effectiveness view
CREATE VIEW IF NOT EXISTS retention_policy_effectiveness AS
SELECT
    privacy_band,
    deletion_reason,
    strftime('%Y-%m', deletion_timestamp / 1000, 'unixepoch') as month,
    COUNT(*) as deletions_per_month,
    AVG(receipt_age_days) as avg_age_days,
    MIN(receipt_age_days) as min_age_days,
    MAX(receipt_age_days) as max_age_days
FROM deletion_audit
WHERE deletion_reason = 'RETENTION_POLICY_EXPIRED'
GROUP BY privacy_band, month
ORDER BY privacy_band, month DESC;

-- Triggers for automatic audit enrichment
CREATE TRIGGER IF NOT EXISTS enrich_deletion_audit
BEFORE INSERT ON deletion_audit
FOR EACH ROW
BEGIN
    -- Calculate receipt age at deletion time
    SELECT
        CASE
            WHEN NEW.original_timestamp IS NOT NULL
            THEN ROUND((NEW.deletion_timestamp - NEW.original_timestamp) / (1000.0 * 60 * 60 * 24))
            ELSE NULL
        END
    INTO NEW.receipt_age_days;

    -- Set retention check timestamp if not provided
    SELECT
        CASE
            WHEN NEW.retention_check_timestamp IS NULL
            THEN NEW.deletion_timestamp
            ELSE NEW.retention_check_timestamp
        END
    INTO NEW.retention_check_timestamp;
END;

-- Integrity verification trigger
CREATE TRIGGER IF NOT EXISTS validate_deletion_audit
BEFORE INSERT ON deletion_audit
FOR EACH ROW
BEGIN
    -- Verify receipt actually existed (if we have the data)
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM receipts
            WHERE receipt_id = NEW.receipt_id
            AND session_id = NEW.session_id
            AND user_id = NEW.user_id
        ) OR NEW.deletion_reason = 'RETENTION_POLICY_EXPIRED' THEN NULL
        ELSE RAISE(ABORT, 'Cannot audit deletion of non-existent receipt')
    END;
END;

-- Statistics table for deletion patterns
CREATE TABLE IF NOT EXISTS deletion_statistics (
    stat_date DATE PRIMARY KEY,
    total_deletions INTEGER NOT NULL DEFAULT 0,
    deletions_by_band TEXT NOT NULL,  -- JSON: {"GREEN": 100, "AMBER": 50, ...}
    deletions_by_reason TEXT NOT NULL,  -- JSON: {"RETENTION_POLICY_EXPIRED": 120, ...}
    avg_age_at_deletion_days REAL,
    total_space_reclaimed_bytes INTEGER,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
);

-- Automatic statistics updates
CREATE TRIGGER IF NOT EXISTS update_deletion_stats
AFTER INSERT ON deletion_audit
BEGIN
    INSERT OR REPLACE INTO deletion_statistics (stat_date, total_deletions, deletions_by_band, deletions_by_reason)
    SELECT
        date('now'),
        COUNT(*),
        json_group_object(privacy_band, COUNT(*)),
        json_group_object(deletion_reason, COUNT(*))
    FROM deletion_audit
    WHERE date(deletion_timestamp / 1000, 'unixepoch') = date('now');
END;

-- Data retention for audit table itself (keep 7 years for GDPR compliance)
CREATE TABLE IF NOT EXISTS audit_retention_policy (
    policy_id INTEGER PRIMARY KEY CHECK (policy_id = 1),  -- Singleton table
    max_audit_age_years INTEGER NOT NULL DEFAULT 7,
    last_cleanup_timestamp INTEGER,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
);

-- Insert default audit retention policy
INSERT OR IGNORE INTO audit_retention_policy (policy_id, max_audit_age_years) VALUES (1, 7);