"""Test suite for K0 migration runner with rollback support.

Tests forward migrations, rollback operations, dry-run mode, and rollback script
generation. Uses temporary SQLite databases to ensure test isolation.
"""

import logging
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from k0.automation.migrate import (
    MigrationError,
    MigrationResult,
    apply_migrations,
    generate_rollback_script,
    rollback_migration,
)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    yield db_path
    # Cleanup
    db_path.unlink(missing_ok=True)
    (db_path.parent / f"{db_path.stem}-wal").unlink(missing_ok=True)
    (db_path.parent / f"{db_path.stem}-shm").unlink(missing_ok=True)


@pytest.fixture
def migrations_dir():
    """Create a temporary migrations directory with test migration files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mig_dir = Path(tmpdir)

        # Create 0001_baseline.sql
        (mig_dir / "0001_baseline.sql").write_text(
            """\
-- Baseline migration
BEGIN;
PRAGMA foreign_keys=OFF;

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE INDEX idx_users_name ON users(name);

PRAGMA foreign_keys=ON;
COMMIT;
"""
        )

        # Create 0002_add_email.sql
        (mig_dir / "0002_add_email.sql").write_text(
            """\
-- Add email column
BEGIN;

ALTER TABLE users ADD COLUMN email TEXT;

COMMIT;
"""
        )

        # Create 0003_add_audit.sql
        (mig_dir / "0003_add_audit.sql").write_text(
            """\
-- Add audit logging table
BEGIN;

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TRIGGER trg_audit_insert
AFTER INSERT ON audit_log
BEGIN
  SELECT 1;  -- Placeholder
END;

COMMIT;
"""
        )

        yield mig_dir


# =============================================================================
# Tests: apply_migrations
# =============================================================================


def test_apply_migrations_forward(temp_db, migrations_dir):
    """Test applying forward migrations successfully."""
    results = apply_migrations(temp_db, migrations_path=migrations_dir)

    assert len(results) == 3
    assert results[0].action == "applied"
    assert results[0].version == "0001_baseline"
    assert results[0].checksum  # Checksum is computed
    assert results[0].duration_seconds is not None

    assert results[1].action == "applied"
    assert results[1].version == "0002_add_email"

    assert results[2].action == "applied"
    assert results[2].version == "0003_add_audit"

    # Verify database state
    import sqlite3

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()

    # Verify table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    assert cursor.fetchone() is not None

    # Verify schema_migrations records
    cursor.execute("SELECT COUNT(*) FROM schema_migrations")
    assert cursor.fetchone()[0] == 3

    conn.close()


def test_apply_migrations_dry_run(temp_db, migrations_dir):
    """Test dry-run mode reports pending migrations without applying."""
    results = apply_migrations(
        temp_db,
        migrations_path=migrations_dir,
        dry_run=True,
    )

    assert len(results) == 3
    assert all(r.action == "pending" for r in results)

    # Verify database is untouched
    import sqlite3

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()

    # schema_migrations should exist but be empty
    cursor.execute("SELECT COUNT(*) FROM schema_migrations")
    count = cursor.fetchone()[0]
    assert count == 0

    conn.close()


def test_apply_migrations_idempotent(temp_db, migrations_dir):
    """Test applying migrations twice is idempotent (second run skips)."""
    results1 = apply_migrations(temp_db, migrations_path=migrations_dir)
    assert all(r.action in ("applied", "skipped") for r in results1)

    results2 = apply_migrations(temp_db, migrations_path=migrations_dir)
    assert len(results2) == 3
    assert all(r.action == "skipped" for r in results2)


def test_apply_migrations_checksum_mismatch(temp_db, migrations_dir):
    """Test migration fails if file content changes after application."""
    # Apply once
    apply_migrations(temp_db, migrations_path=migrations_dir)

    # Modify migration file
    (migrations_dir / "0001_baseline.sql").write_text("-- Modified baseline\nBEGIN;\nCOMMIT;")

    # Second attempt should fail
    with pytest.raises(MigrationError, match="Checksum mismatch"):
        apply_migrations(temp_db, migrations_path=migrations_dir)


def test_apply_migrations_missing_directory():
    """Test error when migrations directory doesn't exist."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        with pytest.raises(MigrationError, match="does not exist"):
            apply_migrations(db_path, migrations_path="/nonexistent")
    finally:
        db_path.unlink()


def test_apply_migrations_no_files():
    """Test error when migrations directory is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        try:
            with pytest.raises(MigrationError, match="No migration files"):
                apply_migrations(db_path, migrations_path=tmpdir)
        finally:
            db_path.unlink()


# =============================================================================
# Tests: rollback_migration
# =============================================================================


def test_rollback_migration_single(temp_db, migrations_dir):
    """Test rolling back a single migration."""
    # Apply all migrations
    apply_migrations(temp_db, migrations_path=migrations_dir)

    # Rollback to 0002
    results = rollback_migration(
        temp_db,
        target_version="0002_add_email",
        migrations_path=migrations_dir,
    )

    assert len(results) == 1
    assert results[0].action == "rolled_back"
    assert results[0].version == "0003_add_audit"
    assert results[0].rollback_script is not None
    assert "DROP TRIGGER" in results[0].rollback_script
    assert results[0].duration_seconds is not None

    # Verify database state
    import sqlite3

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()

    # Verify audit_log table no longer exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    assert cursor.fetchone() is None

    # Verify schema_migrations has correct count
    cursor.execute("SELECT COUNT(*) FROM schema_migrations")
    assert cursor.fetchone()[0] == 2

    conn.close()


def test_rollback_migration_multiple(temp_db, migrations_dir):
    """Test rolling back multiple migrations in reverse order."""
    # Apply all migrations
    apply_migrations(temp_db, migrations_path=migrations_dir)

    # Rollback to 0001
    results = rollback_migration(
        temp_db,
        target_version="0001_baseline",
        migrations_path=migrations_dir,
    )

    assert len(results) == 2
    # Should rollback in reverse order: 0003, then 0002
    assert results[0].version == "0003_add_audit"
    assert results[0].action == "rolled_back"
    assert results[1].version == "0002_add_email"
    assert results[1].action == "rolled_back"

    # Verify email column no longer exists
    import sqlite3

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "email" not in columns

    conn.close()


def test_rollback_migration_dry_run(temp_db, migrations_dir):
    """Test rollback dry-run shows plan without executing."""
    # Apply all migrations
    apply_migrations(temp_db, migrations_path=migrations_dir)

    # Dry-run rollback
    results = rollback_migration(
        temp_db,
        target_version="0002_add_email",
        migrations_path=migrations_dir,
        dry_run=True,
    )

    assert len(results) == 1
    assert results[0].action == "pending"
    assert results[0].rollback_script is not None

    # Verify audit_log table still exists (rollback wasn't executed)
    import sqlite3

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    assert cursor.fetchone() is not None

    conn.close()


def test_rollback_migration_invalid_target(temp_db, migrations_dir):
    """Test error when target version not found."""
    # Apply all migrations
    apply_migrations(temp_db, migrations_path=migrations_dir)

    with pytest.raises(MigrationError, match="not found in applied migrations"):
        rollback_migration(
            temp_db,
            target_version="0099_nonexistent",
            migrations_path=migrations_dir,
        )


def test_rollback_migration_already_at_target(temp_db, migrations_dir):
    """Test rollback when already at target version (no-op)."""
    # Apply all migrations
    apply_migrations(temp_db, migrations_path=migrations_dir)

    # Rollback to 0003 (last version, nothing to do)
    results = rollback_migration(
        temp_db,
        target_version="0003_add_audit",
        migrations_path=migrations_dir,
    )

    assert len(results) == 0  # No migrations rolled back


def test_rollback_migration_nonexistent_db():
    """Test error when database doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with tempfile.TemporaryDirectory() as migdir:
            (Path(migdir) / "0001_baseline.sql").write_text("BEGIN; COMMIT;")

            with pytest.raises(MigrationError, match="does not exist"):
                rollback_migration(
                    Path(tmpdir) / "nonexistent.db",
                    target_version="0001_baseline",
                    migrations_path=migdir,
                )


# =============================================================================
# Tests: generate_rollback_script
# =============================================================================


def test_generate_rollback_script_create_table():
    """Test rollback script generation for CREATE TABLE."""
    up_script = """\
BEGIN;
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    assert "DROP TABLE IF EXISTS users;" in down_script
    assert "PRAGMA foreign_keys=OFF;" in down_script
    assert "BEGIN;" in down_script
    assert "COMMIT;" in down_script


def test_generate_rollback_script_create_index():
    """Test rollback script generation for CREATE INDEX."""
    up_script = """\
BEGIN;
CREATE INDEX idx_users_name ON users(name);
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    assert "DROP INDEX IF EXISTS idx_users_name;" in down_script


def test_generate_rollback_script_create_unique_index():
    """Test rollback script for CREATE UNIQUE INDEX."""
    up_script = """\
BEGIN;
CREATE UNIQUE INDEX uq_users_email ON users(email);
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    assert "DROP INDEX IF EXISTS uq_users_email;" in down_script


def test_generate_rollback_script_create_trigger():
    """Test rollback script for CREATE TRIGGER."""
    up_script = """\
BEGIN;
CREATE TRIGGER trg_audit_insert
AFTER INSERT ON audit_log
BEGIN
  SELECT 1;
END;
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    assert "DROP TRIGGER IF EXISTS trg_audit_insert;" in down_script


def test_generate_rollback_script_alter_add_column():
    """Test rollback script for ALTER TABLE ADD COLUMN."""
    up_script = """\
BEGIN;
ALTER TABLE users ADD COLUMN email TEXT;
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    assert "ALTER TABLE users DROP COLUMN email;" in down_script


def test_generate_rollback_script_multiple_statements():
    """Test rollback script generation with multiple DDL statements."""
    up_script = """\
BEGIN;
CREATE TABLE users (id INTEGER PRIMARY KEY);
CREATE TABLE orders (id INTEGER PRIMARY KEY);
CREATE INDEX idx_orders_user ON orders(user_id);
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    # Statements should be reversed (newest first)
    lines = down_script.split("\n")
    idx_line = next(i for i, line in enumerate(lines) if "DROP INDEX" in line)
    orders_line = next(i for i, line in enumerate(lines) if "DROP TABLE IF EXISTS orders" in line)
    users_line = next(i for i, line in enumerate(lines) if "DROP TABLE IF EXISTS users" in line)

    # Index should come before tables (reverse order)
    assert idx_line < orders_line < users_line


def test_generate_rollback_script_ignores_comments_and_pragmas():
    """Test that comments and pragmas are ignored in rollback generation."""
    up_script = """\
-- This is a comment
BEGIN;
PRAGMA journal_mode=WAL;
CREATE TABLE users (id INTEGER PRIMARY KEY);
PRAGMA foreign_keys=OFF;
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    # Should not contain original comments/pragmas
    assert "journal_mode=WAL" not in down_script
    assert "This is a comment" not in down_script
    # But should contain the DDL reversal
    assert "DROP TABLE IF EXISTS users;" in down_script


def test_generate_rollback_script_dml_statements_ignored():
    """Test that DML statements (INSERT, UPDATE, DELETE) are ignored."""
    up_script = """\
BEGIN;
CREATE TABLE users (id INTEGER PRIMARY KEY);
INSERT INTO users VALUES (1);
UPDATE users SET id = 2 WHERE id = 1;
DELETE FROM users WHERE id = 2;
COMMIT;
"""

    down_script = generate_rollback_script(up_script)

    # Should only reverse the CREATE TABLE, not DML
    assert "DROP TABLE IF EXISTS users;" in down_script
    assert "INSERT INTO" not in down_script
    assert "UPDATE users" not in down_script
    assert "DELETE FROM" not in down_script


# =============================================================================
# Tests: Telemetry and Error Handling
# =============================================================================


@mock.patch("k0.automation.migrate._TELEMETRY_ENABLED", False)
def test_apply_migrations_telemetry_disabled(temp_db, migrations_dir):
    """Test migrations work correctly when Prometheus telemetry is disabled."""
    results = apply_migrations(temp_db, migrations_path=migrations_dir)
    assert len(results) == 3
    assert all(r.action == "applied" for r in results)


def test_migration_result_dataclass():
    """Test MigrationResult dataclass attributes."""
    result = MigrationResult(
        version="0001_baseline",
        action="applied",
        checksum="abc123",
        path=Path("/tmp/0001_baseline.sql"),
        duration_seconds=0.5,
        rollback_script="DROP TABLE IF EXISTS users;",
    )

    assert result.version == "0001_baseline"
    assert result.action == "applied"
    assert result.duration_seconds == 0.5
    assert result.rollback_script is not None


def test_migration_error_inheritance():
    """Test MigrationError is a RuntimeError."""
    err = MigrationError("Test error")
    assert isinstance(err, RuntimeError)


# =============================================================================
# Tests: Integration (Forward + Rollback + Reapply)
# =============================================================================


def test_integration_forward_rollback_forward(temp_db, migrations_dir):
    """Test complete cycle: apply -> rollback -> reapply."""
    # Apply all migrations
    results1 = apply_migrations(temp_db, migrations_path=migrations_dir)
    assert len(results1) == 3
    assert all(r.action == "applied" for r in results1)

    # Rollback to 0001
    results2 = rollback_migration(
        temp_db,
        target_version="0001_baseline",
        migrations_path=migrations_dir,
    )
    assert len(results2) == 2
    assert all(r.action == "rolled_back" for r in results2)

    # Reapply migrations
    results3 = apply_migrations(temp_db, migrations_path=migrations_dir)
    assert len(results3) == 3
    assert results3[0].action == "skipped"  # 0001 already applied
    assert results3[1].action == "applied"  # 0002 reapplied
    assert results3[2].action == "applied"  # 0003 reapplied

    # Verify final state
    import sqlite3

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM schema_migrations")
    assert cursor.fetchone()[0] == 3
    conn.close()


def test_integration_logging(temp_db, migrations_dir, caplog):
    """Test that migration operations produce appropriate log messages."""
    logger = logging.getLogger("k0.automation.migrate")

    with caplog.at_level(logging.INFO, logger="k0.automation.migrate"):
        apply_migrations(temp_db, migrations_path=migrations_dir, logger=logger)

    assert "Applying migration 0001_baseline" in caplog.text
    assert "Applying migration 0002_add_email" in caplog.text
    assert "Applying migration 0003_add_audit" in caplog.text


# =============================================================================
# Performance Tests (Optional)
# =============================================================================


@pytest.mark.performance
def test_performance_apply_migrations_baseline(temp_db, migrations_dir):
    """Baseline performance test for applying migrations."""
    import time

    start = time.perf_counter()
    apply_migrations(temp_db, migrations_path=migrations_dir)
    elapsed = time.perf_counter() - start

    # Should complete well under 1 second
    assert elapsed < 1.0, f"Migration apply took {elapsed}s, expected < 1.0s"


@pytest.mark.performance
def test_performance_rollback_baseline(temp_db, migrations_dir):
    """Baseline performance test for rollback operations."""
    apply_migrations(temp_db, migrations_path=migrations_dir)

    import time

    start = time.perf_counter()
    rollback_migration(
        temp_db,
        target_version="0001_baseline",
        migrations_path=migrations_dir,
    )
    elapsed = time.perf_counter() - start

    # Should complete well under 1 second
    assert elapsed < 1.0, f"Migration rollback took {elapsed}s, expected < 1.0s"
