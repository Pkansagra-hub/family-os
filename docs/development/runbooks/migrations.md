---
title: "SQLite Migration Runbook"
description: "Operations guide for database migrations and rollbacks in K0"
tier: "K0 Operations"
created_at: "2025-11-01"
last_updated: "2025-11-01"
---

# SQLite Migration Runbook

## Overview

This runbook covers database migration operations for K0 kernel storage. The migration system supports forward application, dry-run validation, and rollback operations with automatic script generation.

**Key Principles**:

- Migrations are applied in alphabetical order
- Rollbacks are applied in reverse order (newest first)
- All operations are transactional (atomic)
- Checksums prevent accidental migration corruption
- Prometheus telemetry tracks all operations

---

## Common Operations

### Apply Forward Migrations

**Command**:
```bash
python -m k0.automation.migrate --database-path k0_runtime.sqlite3
```

**What happens**:
1. Reads all `.sql` files from `k0/contracts/sql/migrations/` in alphabetical order
2. Checks `schema_migrations` table for already-applied migrations
3. For each new migration:
   - Begins transaction
   - Executes migration script
   - Records version and SHA256 checksum
   - Commits transaction
4. Emits Prometheus metrics: `k0_migration_duration_seconds`, `k0_migration_status`

**Success output**:
```
Applying migration 0001_baseline
Applying migration 0002_add_email
Applying migration 0003_add_audit
✅ Applied 3 migrations in 0.45s
```

**Idempotency**: Safe to run repeatedly; already-applied migrations are skipped.

---

### Dry-Run Validation

**Command**:
```bash
python -m k0.automation.migrate --database-path k0_runtime.sqlite3 --dry-run
```

**What happens**:
1. Reads all migration files
2. Checks which would be applied (not yet recorded)
3. Reports plan without executing
4. **Database is not modified**

**Use cases**:
- Pre-deployment validation
- CI checks for pending migrations
- Migration planning on new environments

---

### Rollback to Target Version

**Command**:
```bash
python -m k0.automation.migrate --database-path k0_runtime.sqlite3 --rollback --target-version=0001_baseline
```

**What happens**:
1. Validates target version exists in applied migrations
2. Identifies all newer versions to rollback (in reverse order)
3. For each migration to rollback:
   - Auto-generates DOWN script (DDL reversal)
   - Begins transaction
   - Executes DOWN script
   - Deletes version from `schema_migrations`
   - Commits transaction
4. Emits Prometheus metrics: `k0_migration_rollback_total`, `k0_migration_duration_seconds`

**Success output**:
```
Rolling back 2 migration(s) from 0003_add_audit to 0001_baseline
Rolling back migration 0003_add_audit
Rolling back migration 0002_add_email
✅ Rolled back 2 migrations in 0.32s
```

**Reverse order**: Ensures dependencies are respected (e.g., drop foreign keys before dropping tables)

---

### Dry-Run Rollback

**Command**:
```bash
python -m k0.automation.migrate --database-path k0_runtime.sqlite3 --rollback --target-version=0001_baseline --dry-run
```

**What happens**:
1. Generates rollback plan
2. Shows auto-generated DOWN scripts for review
3. **Database is not modified**

**Use cases**:
- Review planned DDL changes before executing
- Validate auto-generated rollback scripts (may need manual adjustment for complex migrations)
- Emergency recovery planning

**Example output**:
```
[dry-run] would rollback migration 0003_add_audit

-- Auto-generated DOWN migration (best-effort)
-- Review and adjust as needed for complex operations

BEGIN;

PRAGMA foreign_keys=OFF;

DROP TRIGGER IF EXISTS trg_audit_insert;
DROP TABLE IF EXISTS audit_log;

PRAGMA foreign_keys=ON;

COMMIT;
```

---

## Rollback Script Generation

The system auto-generates DOWN scripts by reversing DDL statements:

| UP Statement | DOWN Statement |
|---|---|
| `CREATE TABLE foo (...)` | `DROP TABLE IF EXISTS foo;` |
| `CREATE INDEX idx_foo ON table(...)` | `DROP INDEX IF EXISTS idx_foo;` |
| `CREATE TRIGGER trg_foo ...` | `DROP TRIGGER IF EXISTS trg_foo;` |
| `ALTER TABLE foo ADD COLUMN bar ...` | `ALTER TABLE foo DROP COLUMN bar;` |

**Important**: Auto-generated scripts are **best-effort**. For complex migrations (e.g., data transformations, constraint changes), inspect and adjust manually before executing in production.

---

## Emergency Procedures

### Scenario: Production Migration Fails

**Symptoms**:
- Migration error in logs
- Schema partially applied
- Database locked or corrupted

**Recovery**:

1. **Check current state**:
   ```bash
   sqlite3 k0_runtime.sqlite3 "SELECT version, applied_at FROM schema_migrations ORDER BY version"
   ```

2. **Identify last successful migration**:
   - Note which version is recorded
   - Check logs for failure point

3. **Dry-run rollback to last known-good version**:
   ```bash
   python -m k0.automation.migrate \
     --database-path k0_runtime.sqlite3 \
     --rollback \
     --target-version=0001_baseline \
     --dry-run
   ```

4. **Review generated DOWN scripts** for potential issues

5. **Execute rollback** (if scripts look safe):
   ```bash
   python -m k0.automation.migrate \
     --database-path k0_runtime.sqlite3 \
     --rollback \
     --target-version=0001_baseline
   ```

6. **Investigate root cause** (schema error, permissions, disk space, etc.)

7. **Re-apply migrations** once fixed:
   ```bash
   python -m k0.automation.migrate --database-path k0_runtime.sqlite3
   ```

### Scenario: Checksum Mismatch

**Symptoms**:
```
MigrationError: Checksum mismatch for migration '0001_baseline'.
Expected abc123..., found def456...
```

**Causes**:
- Migration file was modified after application
- Corrupted database record
- Wrong database version applied

**Recovery**:

1. **Check if modification is intentional**:
   ```bash
   git diff k0/contracts/sql/migrations/0001_baseline.sql
   ```

2. **If intentional**: Create a new migration (never modify existing)
   ```bash
   cp k0/contracts/sql/migrations/0001_baseline.sql \
      k0/contracts/sql/migrations/0004_fix_baseline.sql
   # Edit 0004 with desired changes
   python -m k0.automation.migrate --database-path k0_runtime.sqlite3
   ```

3. **If accidental**: Restore file from git
   ```bash
   git restore k0/contracts/sql/migrations/0001_baseline.sql
   python -m k0.automation.migrate --database-path k0_runtime.sqlite3
   ```

---

## Telemetry & Monitoring

### Prometheus Metrics

```
# HELP k0_migration_duration_seconds Duration of migration application in seconds
# TYPE k0_migration_duration_seconds histogram
k0_migration_duration_seconds_bucket{le="0.1"} 1.0
k0_migration_duration_seconds_bucket{le="0.5"} 10.0
k0_migration_duration_seconds_bucket{le="1.0"} 11.0
k0_migration_duration_seconds_bucket{le="2.5"} 11.0

# HELP k0_migration_rollback_total Total number of rollback operations
# TYPE k0_migration_rollback_total counter
k0_migration_rollback_total 2.0

# HELP k0_migration_status Last migration status (1=success, 0=pending, -1=error)
# TYPE k0_migration_status gauge
k0_migration_status 1.0
```

### Alerts

Set up alerts for:
- `k0_migration_status == -1` (last operation failed)
- `k0_migration_duration_seconds > 5.0` (unexpectedly slow)
- `k0_migration_rollback_total > 0` (rollback occurred; may need investigation)

---

## Testing

### Automated Tests

27 comprehensive tests in `tests/k0/automation/test_migrate.py`:

```bash
# Run all migration tests
python -m pytest tests/k0/automation/test_migrate.py -v

# Run specific test
python -m pytest tests/k0/automation/test_migrate.py::test_rollback_migration_single -v

# Run with coverage
python -m pytest tests/k0/automation/test_migrate.py --cov=k0.automation.migrate
```

### Manual Testing

**Test environment migration cycle**:

```bash
# 1. Create test database
sqlite3 test_migrations.db "SELECT 1"

# 2. Apply all migrations
python -m k0.automation.migrate --database-path test_migrations.db

# 3. Verify schema
sqlite3 test_migrations.db ".tables"

# 4. Rollback one migration
python -m k0.automation.migrate \
  --database-path test_migrations.db \
  --rollback \
  --target-version=0002_add_email

# 5. Reapply
python -m k0.automation.migrate --database-path test_migrations.db

# 6. Cleanup
rm test_migrations.db*
```

---

## Best Practices

### Creating Migrations

1. **One logical change per migration**
   - Good: `0005_add_audit_table.sql`
   - Bad: `0005_refactor_everything.sql`

2. **Make migrations replayable** (idempotent)
   ```sql
   CREATE TABLE IF NOT EXISTS users (...);  -- Good
   CREATE TABLE users (...);                 -- Risky
   ```

3. **Include comments explaining changes**
   ```sql
   -- Add device key rotation support (ADR 001)
   -- Tracks key state: PENDING -> ACTIVE -> ROTATING -> REVOKED
   CREATE TABLE st_device_keys (...)
   ```

4. **Test rollback scripts** manually for complex migrations
   ```bash
   # Dry-run rollback before committing
   python -m k0.automation.migrate \
     --database-path test.db \
     --rollback \
     --target-version=0002 \
     --dry-run
   ```

### Deployment

1. **Pre-deployment checks** (in CI):
   ```bash
   python -m k0.automation.migrate \
     --database-path staging.db \
     --dry-run
   ```

2. **Production deployment**:
   ```bash
   # Backup database
   cp k0_runtime.sqlite3 k0_runtime.sqlite3.backup

   # Apply migrations
   python -m k0.automation.migrate --database-path k0_runtime.sqlite3

   # Verify
   python -m pytest tests/k0/ -k migration
   ```

3. **Post-deployment verification**:
   ```bash
   sqlite3 k0_runtime.sqlite3 "SELECT COUNT(*) FROM schema_migrations"
   curl http://localhost:9090/metrics | grep k0_migration
   ```

---

## References

- **Module**: `k0/automation/migrate.py`
- **Tests**: `tests/k0/automation/test_migrate.py`
- **Contracts**: `k0/contracts/sql/migrations/`
- **Telemetry**: Prometheus metrics (requires `prometheus-client`)
- **ADR**: `docs/architecture/decisions/` (if applicable)
