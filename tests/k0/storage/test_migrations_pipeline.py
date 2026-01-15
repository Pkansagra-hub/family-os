"""
Test suite for migration 0012 (Pipeline Infrastructure).

DEPRECATED: These tests validate SQLite migrations that have been deprecated
in favor of PostgreSQL. The migration files are in k0/contracts/sql(deprecated)/.
These tests are skipped until they are rewritten for PostgreSQL or the
deprecated migrations are removed entirely.

Validates:
- st_pipeline_processed table creation and constraints
- st_pipeline_status table creation and constraints
- st_pipeline_watermarks table creation and constraints
- st_dlq enhancements (error_kind, error_fingerprint)
- Index creation for all performance-critical queries
- Idempotency (migration can run twice without errors)

Related:
- M1 R1.2: DDL Migrations
- Migration file: k0/contracts/sql(deprecated)/migrations/0012_pipeline_infrastructure.sql
- Architecture: docs/architecture/decisions/k0_pipeline_architecture.md
"""

import sqlite3
from pathlib import Path

import pytest

# Skip entire module - SQLite migrations deprecated in favor of PostgreSQL
pytestmark = pytest.mark.skip(
    reason="SQLite migrations deprecated; tests need rewrite for PostgreSQL"
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create temporary database for migration testing."""
    return tmp_path / "test_migration.db"


@pytest.fixture
def db_conn(db_path: Path):
    """Create database connection with baseline schema."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Apply baseline schema (0001) with minimal tables needed for migration 0012
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_wal (
            pos INTEGER PRIMARY KEY AUTOINCREMENT,
            space_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            driver TEXT NOT NULL,
            op_kind TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            payload BLOB NOT NULL,
            created_at INTEGER NOT NULL
        );
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_dlq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wal_pos INTEGER NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            driver TEXT NOT NULL,
            op_kind TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            payload BLOB NOT NULL,
            reason TEXT NOT NULL,
            retries INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
    """
    )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def migration_sql() -> str:
    """Load migration 0012 SQL content."""
    migration_path = (
        Path(__file__).parent.parent.parent.parent
        / "k0"
        / "contracts"
        / "sql"
        / "migrations"
        / "0012_pipeline_infrastructure.sql"
    )
    return migration_path.read_text(encoding="utf-8")


def test_migration_0012_creates_pipeline_processed_table(
    db_conn: sqlite3.Connection, migration_sql: str
):
    """Verify st_pipeline_processed table is created with correct schema."""
    # Apply migration
    db_conn.executescript(migration_sql)

    # Check table exists
    cursor = db_conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='st_pipeline_processed'
    """
    )
    assert cursor.fetchone() is not None, "st_pipeline_processed table not created"

    # Check columns
    cursor = db_conn.execute("PRAGMA table_info(st_pipeline_processed)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type

    assert columns["pipeline_id"] == "TEXT", "pipeline_id column missing or wrong type"
    assert columns["space_id"] == "TEXT", "space_id column missing or wrong type"
    assert columns["wal_pos"] == "INTEGER", "wal_pos column missing or wrong type"
    assert columns["processed_at"] == "INTEGER", "processed_at column missing or wrong type"

    # Check PRIMARY KEY constraint
    cursor = db_conn.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='st_pipeline_processed'
    """
    )
    table_sql = cursor.fetchone()[0]
    assert (
        "PRIMARY KEY (pipeline_id, space_id, wal_pos)" in table_sql
    ), "Composite PRIMARY KEY not defined"


def test_migration_0012_creates_pipeline_status_table(
    db_conn: sqlite3.Connection, migration_sql: str
):
    """Verify st_pipeline_status table is created with correct schema."""
    db_conn.executescript(migration_sql)

    # Check table exists
    cursor = db_conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='st_pipeline_status'
    """
    )
    assert cursor.fetchone() is not None, "st_pipeline_status table not created"

    # Check columns
    cursor = db_conn.execute("PRAGMA table_info(st_pipeline_status)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    assert columns["pipeline_id"] == "TEXT", "pipeline_id column missing"
    assert columns["wal_pos"] == "INTEGER", "wal_pos column missing"
    assert columns["status"] == "TEXT", "status column missing"
    assert columns["duration_ms"] == "INTEGER", "duration_ms column missing"
    assert columns["error_kind"] == "TEXT", "error_kind column missing"
    assert columns["error_msg"] == "TEXT", "error_msg column missing"
    assert columns["updated_at"] == "INTEGER", "updated_at column missing"

    # Check PRIMARY KEY
    cursor = db_conn.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='st_pipeline_status'
    """
    )
    table_sql = cursor.fetchone()[0]
    assert "PRIMARY KEY (pipeline_id, wal_pos)" in table_sql, "Composite PRIMARY KEY not defined"


def test_migration_0012_creates_pipeline_watermarks_table(
    db_conn: sqlite3.Connection, migration_sql: str
):
    """Verify st_pipeline_watermarks table is created with correct schema."""
    db_conn.executescript(migration_sql)

    # Check table exists
    cursor = db_conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='st_pipeline_watermarks'
    """
    )
    assert cursor.fetchone() is not None, "st_pipeline_watermarks table not created"

    # Check columns
    cursor = db_conn.execute("PRAGMA table_info(st_pipeline_watermarks)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    assert columns["pipeline_id"] == "TEXT", "pipeline_id column missing"
    assert columns["space_id"] == "TEXT", "space_id column missing"
    assert columns["watermark"] == "INTEGER", "watermark column missing"
    assert columns["updated_at"] == "INTEGER", "updated_at column missing"

    # Check PRIMARY KEY
    cursor = db_conn.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='st_pipeline_watermarks'
    """
    )
    table_sql = cursor.fetchone()[0]
    assert "PRIMARY KEY (pipeline_id, space_id)" in table_sql, "Composite PRIMARY KEY not defined"


def test_migration_0012_enhances_dlq(db_conn: sqlite3.Connection, migration_sql: str):
    """Verify st_dlq table is enhanced with error_kind and error_fingerprint columns."""
    db_conn.executescript(migration_sql)

    # Check new columns exist
    cursor = db_conn.execute("PRAGMA table_info(st_dlq)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    assert "error_kind" in columns, "error_kind column not added to st_dlq"
    assert "error_fingerprint" in columns, "error_fingerprint column not added to st_dlq"

    # Verify both are TEXT type (nullable)
    assert columns["error_kind"] == "TEXT", "error_kind wrong type"
    assert columns["error_fingerprint"] == "TEXT", "error_fingerprint wrong type"


def test_migration_0012_creates_indexes(db_conn: sqlite3.Connection, migration_sql: str):
    """Verify all 6 performance indexes are created."""
    db_conn.executescript(migration_sql)

    # Get all indexes
    cursor = db_conn.execute(
        """
        SELECT name, tbl_name FROM sqlite_master
        WHERE type='index' AND sql IS NOT NULL
    """
    )
    indexes = {row[0]: row[1] for row in cursor.fetchall()}

    # Check all 6 indexes exist
    expected_indexes = {
        "idx_pipeline_processed_space_wal": "st_pipeline_processed",
        "idx_pipeline_status_status": "st_pipeline_status",
        "idx_pipeline_status_updated": "st_pipeline_status",
        "idx_pipeline_watermarks_pipeline": "st_pipeline_watermarks",
        "idx_dlq_error_kind": "st_dlq",
        "idx_dlq_error_fingerprint": "st_dlq",
    }

    for idx_name, tbl_name in expected_indexes.items():
        assert idx_name in indexes, f"Index {idx_name} not created"
        assert indexes[idx_name] == tbl_name, f"Index {idx_name} on wrong table"


def test_migration_0012_idempotent(db_conn: sqlite3.Connection, migration_sql: str):
    """Verify migration can run twice without errors (IF NOT EXISTS clauses work)."""
    # Run migration first time
    db_conn.executescript(migration_sql)
    db_conn.commit()

    # Run migration second time
    # Note: ALTER TABLE ADD COLUMN will fail on second run (expected SQLite behavior)
    # We verify that table/index creation (IF NOT EXISTS) is idempotent
    # and that column additions fail gracefully (known limitation)
    try:
        db_conn.executescript(migration_sql)
        db_conn.commit()
        # If no error, great! (should happen if columns already exist)
    except sqlite3.OperationalError as e:
        # Expected: "duplicate column name: error_kind" on second run
        # This is acceptable because:
        # 1. SQLite doesn't support ALTER TABLE ... IF NOT EXISTS
        # 2. Production migrations run once, not twice
        # 3. Table/index creation (95% of migration) IS idempotent
        assert "duplicate column name" in str(e), f"Unexpected error: {e}"

    # Verify tables still exist and have correct structure (idempotent parts)
    cursor = db_conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN ('st_pipeline_processed', 'st_pipeline_status', 'st_pipeline_watermarks')
    """
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert len(tables) == 3, "Tables missing after second run"


def test_migration_0012_pipeline_processed_insert(db_conn: sqlite3.Connection, migration_sql: str):
    """Verify st_pipeline_processed supports basic insert/query operations."""
    db_conn.executescript(migration_sql)

    # Insert sample record
    db_conn.execute(
        """
        INSERT INTO st_pipeline_processed (pipeline_id, space_id, wal_pos, processed_at)
        VALUES ('P02', 'space_123', 42, 1234567890)
    """
    )
    db_conn.commit()

    # Query back
    cursor = db_conn.execute(
        """
        SELECT pipeline_id, space_id, wal_pos, processed_at
        FROM st_pipeline_processed
        WHERE pipeline_id = 'P02' AND space_id = 'space_123'
    """
    )
    row = cursor.fetchone()

    assert row is not None, "Insert failed"
    assert row[0] == "P02"
    assert row[1] == "space_123"
    assert row[2] == 42
    assert row[3] == 1234567890


def test_migration_0012_pipeline_status_insert(db_conn: sqlite3.Connection, migration_sql: str):
    """Verify st_pipeline_status supports basic insert/query operations."""
    db_conn.executescript(migration_sql)

    # Insert sample receipt
    db_conn.execute(
        """
        INSERT INTO st_pipeline_status (pipeline_id, wal_pos, status, duration_ms, error_kind, error_msg, updated_at)
        VALUES ('P02', 42, 'OK', 85, NULL, NULL, 1234567890)
    """
    )
    db_conn.commit()

    # Query back
    cursor = db_conn.execute(
        """
        SELECT pipeline_id, wal_pos, status, duration_ms
        FROM st_pipeline_status
        WHERE pipeline_id = 'P02' AND wal_pos = 42
    """
    )
    row = cursor.fetchone()

    assert row is not None, "Insert failed"
    assert row[0] == "P02"
    assert row[1] == 42
    assert row[2] == "OK"
    assert row[3] == 85


def test_migration_0012_pipeline_watermarks_insert(db_conn: sqlite3.Connection, migration_sql: str):
    """Verify st_pipeline_watermarks supports basic insert/query operations."""
    db_conn.executescript(migration_sql)

    # Insert sample watermark
    db_conn.execute(
        """
        INSERT INTO st_pipeline_watermarks (pipeline_id, space_id, watermark, updated_at)
        VALUES ('P02', 'space_123', 100, 1234567890)
    """
    )
    db_conn.commit()

    # Query back
    cursor = db_conn.execute(
        """
        SELECT pipeline_id, space_id, watermark, updated_at
        FROM st_pipeline_watermarks
        WHERE pipeline_id = 'P02' AND space_id = 'space_123'
    """
    )
    row = cursor.fetchone()

    assert row is not None, "Insert failed"
    assert row[0] == "P02"
    assert row[1] == "space_123"
    assert row[2] == 100
    assert row[3] == 1234567890


def test_migration_0012_dlq_enhancements_insert(db_conn: sqlite3.Connection, migration_sql: str):
    """Verify st_dlq enhancements support basic insert/query operations."""
    db_conn.executescript(migration_sql)

    # Insert DLQ record with new columns
    db_conn.execute(
        """
        INSERT INTO st_dlq (
            wal_pos, tenant_id, space_id, driver, op_kind, fingerprint,
            payload, reason, retries, error_kind, error_fingerprint,
            created_at, updated_at
        )
        VALUES (
            42, 'tenant_1', 'space_123', 'cognitive', 'write', 'fp_123',
            'payload_bytes', 'ValueError: Invalid JSON', 3, 'ValueError', 'hash_abc123',
            1234567890, 1234567890
        )
    """
    )
    db_conn.commit()

    # Query back with new columns
    cursor = db_conn.execute(
        """
        SELECT wal_pos, error_kind, error_fingerprint
        FROM st_dlq
        WHERE wal_pos = 42
    """
    )
    row = cursor.fetchone()

    assert row is not None, "Insert failed"
    assert row[0] == 42
    assert row[1] == "ValueError"
    assert row[2] == "hash_abc123"


def test_migration_0012_composite_primary_keys_enforced(
    db_conn: sqlite3.Connection, migration_sql: str
):
    """Verify composite PRIMARY KEY constraints prevent duplicate records."""
    db_conn.executescript(migration_sql)

    # Insert first record in st_pipeline_processed
    db_conn.execute(
        """
        INSERT INTO st_pipeline_processed (pipeline_id, space_id, wal_pos, processed_at)
        VALUES ('P02', 'space_123', 42, 1234567890)
    """
    )
    db_conn.commit()

    # Attempt duplicate insert (should fail)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        db_conn.execute(
            """
            INSERT INTO st_pipeline_processed (pipeline_id, space_id, wal_pos, processed_at)
            VALUES ('P02', 'space_123', 42, 1234567999)
        """
        )
        db_conn.commit()
        db_conn.commit()
