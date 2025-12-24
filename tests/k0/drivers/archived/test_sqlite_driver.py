"""Tests for SQLite driver implementation.

Tests cover:
- Connection lifecycle (connect/close)
- Transaction management (begin/commit/rollback)
- CRUD operations (append/read/scan)
- Context manager support
- Error handling
- Integration with K0 outbox

Run with: python -m pytest tests/k0/drivers/test_sqlite_driver.py -v
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from k0.drivers.sqlite import SQLiteDriver


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Create temporary SQLite database with K0 infrastructure schema."""
    db_path = tmp_path / "test_k0.db"

    # Create K0 infrastructure tables (minimal schema for testing)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    # Create test table (st_epi) with subset of fields
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_epi (
            event_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            author_id TEXT NOT NULL,
            event_time TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
            owner_id TEXT NOT NULL,
            visible_to TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            crdt_vector_clock TEXT NOT NULL,
            crdt_tombstone INTEGER DEFAULT 0,
            crdt_lamport INTEGER NOT NULL,
            cognitive_trace_id TEXT NOT NULL
        )
    """
    )

    # Create test table (st_wal) for outbox integration test
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_wal (
            pos INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            envelope_json TEXT NOT NULL,
            schema_uri TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            device_id TEXT NOT NULL,
            commit_ts TEXT NOT NULL
        )
    """
    )

    # Create test table (st_outbox) for integration test
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wal_pos INTEGER NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            driver TEXT NOT NULL,
            op_kind TEXT NOT NULL,
            payload BLOB NOT NULL,
            fingerprint TEXT NOT NULL,
            requeue_seq INTEGER NOT NULL DEFAULT 0,
            retries INTEGER NOT NULL DEFAULT 0
        )
    """
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def driver(test_db: Path) -> SQLiteDriver:
    """Create SQLiteDriver instance for testing."""
    return SQLiteDriver(database_path=test_db, cognitive_trace_id="test-trace-001")


class TestSQLiteDriverConnection:
    """Test connection lifecycle."""

    def test_driver_init(self, test_db: Path) -> None:
        """Test driver initialization."""
        driver = SQLiteDriver(database_path=test_db, cognitive_trace_id="test-trace-001")
        assert driver.database_path == test_db
        assert driver.cognitive_trace_id == "test-trace-001"
        assert driver.conn is None
        assert driver._in_transaction is False

    def test_connect(self, driver: SQLiteDriver) -> None:
        """Test driver connection."""
        driver.connect()
        assert driver.conn is not None
        # Verify WAL mode
        cursor = driver.conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"
        driver.close()

    def test_connect_twice_raises_error(self, driver: SQLiteDriver) -> None:
        """Test connecting twice raises RuntimeError."""
        driver.connect()
        with pytest.raises(RuntimeError, match="Connection already established"):
            driver.connect()
        driver.close()

    def test_close(self, driver: SQLiteDriver) -> None:
        """Test driver close."""
        driver.connect()
        driver.close()
        assert driver.conn is None

    def test_close_with_active_transaction_rollback(self, driver: SQLiteDriver) -> None:
        """Test closing with active transaction triggers rollback."""
        driver.connect()
        driver.begin()
        assert driver._in_transaction is True
        driver.close()
        assert driver.conn is None
        assert driver._in_transaction is False


class TestSQLiteDriverTransactions:
    """Test transaction management."""

    def test_begin(self, driver: SQLiteDriver) -> None:
        """Test starting transaction."""
        driver.connect()
        driver.begin()
        assert driver._in_transaction is True
        driver.close()

    def test_begin_without_connection_raises_error(self, driver: SQLiteDriver) -> None:
        """Test begin without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Connection not established"):
            driver.begin()

    def test_begin_twice_raises_error(self, driver: SQLiteDriver) -> None:
        """Test beginning transaction twice raises RuntimeError."""
        driver.connect()
        driver.begin()
        with pytest.raises(RuntimeError, match="Transaction already active"):
            driver.begin()
        driver.close()

    def test_commit(self, driver: SQLiteDriver, test_db: Path) -> None:
        """Test committing transaction."""
        driver.connect()
        driver.begin()

        # Insert test row
        row_id = driver.append(
            "st_epi",
            {
                "event_id": "evt_001",
                "text": "Test memory",
                "author_id": "person_001",
                "event_time": "2025-11-10T12:00:00Z",
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "privacy_band": "AMBER",
                "owner_id": "person_001",
                "visible_to": '["person_001"]',
                "created_at": "2025-11-10T12:00:00Z",
                "updated_at": "2025-11-10T12:00:00Z",
                "crdt_vector_clock": '{"device1": 5}',
                "crdt_tombstone": 0,
                "crdt_lamport": 5,
                "cognitive_trace_id": "test-trace-001",
            },
        )
        assert row_id > 0

        driver.commit()
        assert driver._in_transaction is False
        driver.close()

        # Verify row persisted
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT * FROM st_epi WHERE event_id = ?", ("evt_001",))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "Test memory"  # text column
        conn.close()

    def test_commit_without_connection_raises_error(self, driver: SQLiteDriver) -> None:
        """Test commit without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Connection not established"):
            driver.commit()

    def test_commit_without_transaction_raises_error(self, driver: SQLiteDriver) -> None:
        """Test commit without active transaction raises RuntimeError."""
        driver.connect()
        with pytest.raises(RuntimeError, match="No transaction active"):
            driver.commit()
        driver.close()

    def test_rollback(self, driver: SQLiteDriver, test_db: Path) -> None:
        """Test rolling back transaction."""
        driver.connect()
        driver.begin()

        # Insert test row
        driver.append(
            "st_epi",
            {
                "event_id": "evt_002",
                "text": "Should be rolled back",
                "author_id": "person_001",
                "event_time": "2025-11-10T12:00:00Z",
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "privacy_band": "AMBER",
                "owner_id": "person_001",
                "visible_to": '["person_001"]',
                "created_at": "2025-11-10T12:00:00Z",
                "updated_at": "2025-11-10T12:00:00Z",
                "crdt_vector_clock": '{"device1": 5}',
                "crdt_tombstone": 0,
                "crdt_lamport": 5,
                "cognitive_trace_id": "test-trace-001",
            },
        )

        driver.rollback()
        assert driver._in_transaction is False
        driver.close()

        # Verify row was not persisted
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT * FROM st_epi WHERE event_id = ?", ("evt_002",))
        row = cursor.fetchone()
        assert row is None
        conn.close()

    def test_rollback_without_connection_raises_error(self, driver: SQLiteDriver) -> None:
        """Test rollback without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Connection not established"):
            driver.rollback()

    def test_rollback_without_transaction_raises_error(self, driver: SQLiteDriver) -> None:
        """Test rollback without active transaction raises RuntimeError."""
        driver.connect()
        with pytest.raises(RuntimeError, match="No transaction active"):
            driver.rollback()
        driver.close()


class TestSQLiteDriverCRUD:
    """Test CRUD operations."""

    def test_append(self, driver: SQLiteDriver) -> None:
        """Test appending row to table."""
        driver.connect()
        driver.begin()

        row_id = driver.append(
            "st_epi",
            {
                "event_id": "evt_003",
                "text": "Test append",
                "author_id": "person_001",
                "event_time": "2025-11-10T12:00:00Z",
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "privacy_band": "GREEN",
                "owner_id": "person_001",
                "visible_to": '["person_001"]',
                "created_at": "2025-11-10T12:00:00Z",
                "updated_at": "2025-11-10T12:00:00Z",
                "crdt_vector_clock": '{"device1": 5}',
                "crdt_tombstone": 0,
                "crdt_lamport": 5,
                "cognitive_trace_id": "test-trace-001",
            },
        )

        assert isinstance(row_id, int)
        assert row_id > 0

        driver.commit()
        driver.close()

    def test_append_without_connection_raises_error(self, driver: SQLiteDriver) -> None:
        """Test append without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Connection not established"):
            driver.append("st_epi", {"event_id": "evt_004"})

    def test_read(self, driver: SQLiteDriver) -> None:
        """Test reading rows from table."""
        driver.connect()
        driver.begin()

        # Insert test rows
        driver.append(
            "st_epi",
            {
                "event_id": "evt_005",
                "text": "First memory",
                "author_id": "person_001",
                "event_time": "2025-11-10T12:00:00Z",
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "privacy_band": "GREEN",
                "owner_id": "person_001",
                "visible_to": '["person_001"]',
                "created_at": "2025-11-10T12:00:00Z",
                "updated_at": "2025-11-10T12:00:00Z",
                "crdt_vector_clock": '{"device1": 5}',
                "crdt_tombstone": 0,
                "crdt_lamport": 5,
                "cognitive_trace_id": "test-trace-001",
            },
        )

        driver.append(
            "st_epi",
            {
                "event_id": "evt_006",
                "text": "Second memory",
                "author_id": "person_001",
                "event_time": "2025-11-10T13:00:00Z",
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "privacy_band": "AMBER",
                "owner_id": "person_001",
                "visible_to": '["person_001"]',
                "created_at": "2025-11-10T13:00:00Z",
                "updated_at": "2025-11-10T13:00:00Z",
                "crdt_vector_clock": '{"device1": 6}',
                "crdt_tombstone": 0,
                "crdt_lamport": 6,
                "cognitive_trace_id": "test-trace-001",
            },
        )

        driver.commit()

        # Read by event_id
        results = driver.read("st_epi", {"event_id": "evt_005"})
        assert len(results) == 1
        assert results[0]["text"] == "First memory"

        # Read by author_id (multiple results)
        results = driver.read("st_epi", {"author_id": "person_001"})
        assert len(results) == 2

        driver.close()

    def test_read_without_connection_raises_error(self, driver: SQLiteDriver) -> None:
        """Test read without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Connection not established"):
            driver.read("st_epi", {"event_id": "evt_007"})

    def test_scan(self, driver: SQLiteDriver) -> None:
        """Test scanning table with pagination."""
        driver.connect()
        driver.begin()

        # Insert 10 test rows
        for i in range(10):
            driver.append(
                "st_epi",
                {
                    "event_id": f"evt_{100+i}",
                    "text": f"Memory {i}",
                    "author_id": "person_001",
                    "event_time": f"2025-11-10T{12+i}:00:00Z",
                    "tenant_id": "tenant-001",
                    "space_id": "personal:person_001",
                    "privacy_band": "GREEN",
                    "owner_id": "person_001",
                    "visible_to": '["person_001"]',
                    "created_at": f"2025-11-10T{12+i}:00:00Z",
                    "updated_at": f"2025-11-10T{12+i}:00:00Z",
                    "crdt_vector_clock": f'{{"device1": {i+1}}}',
                    "crdt_tombstone": 0,
                    "crdt_lamport": i + 1,
                    "cognitive_trace_id": "test-trace-001",
                },
            )

        driver.commit()

        # Scan first 5 rows
        results = driver.scan("st_epi", limit=5, offset=0)
        assert len(results) == 5

        # Scan next 5 rows
        results = driver.scan("st_epi", limit=5, offset=5)
        assert len(results) == 5

        # Scan all rows (default limit=100)
        results = driver.scan("st_epi")
        assert len(results) == 10

        driver.close()

    def test_scan_without_connection_raises_error(self, driver: SQLiteDriver) -> None:
        """Test scan without connection raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Connection not established"):
            driver.scan("st_epi")

    def test_execute(self, driver: SQLiteDriver) -> None:
        """Test executing arbitrary SQL."""
        driver.connect()
        driver.begin()

        # Insert via execute
        cursor = driver.execute(
            "INSERT INTO st_epi (event_id, text, author_id, event_time, tenant_id, space_id, privacy_band, owner_id, visible_to, created_at, updated_at, crdt_vector_clock, crdt_tombstone, crdt_lamport, cognitive_trace_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "evt_200",
                "Custom SQL memory",
                "person_001",
                "2025-11-10T12:00:00Z",
                "tenant-001",
                "personal:person_001",
                "RED",
                "person_001",
                '["person_001"]',
                "2025-11-10T12:00:00Z",
                "2025-11-10T12:00:00Z",
                '{"device1": 1}',
                0,
                1,
                "test-trace-001",
            ),
        )

        driver.commit()

        # Query via execute
        cursor = driver.execute("SELECT * FROM st_epi WHERE event_id = ?", ("evt_200",))
        row = cursor.fetchone()
        assert row is not None
        assert dict(row)["text"] == "Custom SQL memory"

        driver.close()


class TestSQLiteDriverContextManager:
    """Test context manager support."""

    def test_context_manager_success(self, test_db: Path) -> None:
        """Test context manager with successful transaction."""
        with SQLiteDriver(database_path=test_db, cognitive_trace_id="test-trace-001") as driver:
            driver.append(
                "st_epi",
                {
                    "event_id": "evt_300",
                    "text": "Context manager memory",
                    "author_id": "person_001",
                    "event_time": "2025-11-10T12:00:00Z",
                    "tenant_id": "tenant-001",
                    "space_id": "personal:person_001",
                    "privacy_band": "GREEN",
                    "owner_id": "person_001",
                    "visible_to": '["person_001"]',
                    "created_at": "2025-11-10T12:00:00Z",
                    "updated_at": "2025-11-10T12:00:00Z",
                    "crdt_vector_clock": '{"device1": 1}',
                    "crdt_tombstone": 0,
                    "crdt_lamport": 1,
                    "cognitive_trace_id": "test-trace-001",
                },
            )

        # Verify transaction committed and connection closed
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT * FROM st_epi WHERE event_id = ?", ("evt_300",))
        row = cursor.fetchone()
        assert row is not None
        conn.close()

    def test_context_manager_exception_rollback(self, test_db: Path) -> None:
        """Test context manager with exception triggers rollback."""
        try:
            with SQLiteDriver(database_path=test_db, cognitive_trace_id="test-trace-001") as driver:
                driver.append(
                    "st_epi",
                    {
                        "event_id": "evt_400",
                        "text": "Should be rolled back",
                        "author_id": "person_001",
                        "event_time": "2025-11-10T12:00:00Z",
                        "tenant_id": "tenant-001",
                        "space_id": "personal:person_001",
                        "privacy_band": "GREEN",
                        "owner_id": "person_001",
                        "visible_to": '["person_001"]',
                        "created_at": "2025-11-10T12:00:00Z",
                        "updated_at": "2025-11-10T12:00:00Z",
                        "crdt_vector_clock": '{"device1": 1}',
                        "crdt_tombstone": 0,
                        "crdt_lamport": 1,
                        "cognitive_trace_id": "test-trace-001",
                    },
                )
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Verify transaction rolled back
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT * FROM st_epi WHERE event_id = ?", ("evt_400",))
        row = cursor.fetchone()
        assert row is None
        conn.close()


class TestSQLiteDriverOutboxIntegration:
    """Test integration with K0 outbox → driver flow."""

    def test_outbox_to_driver_flow(self, driver: SQLiteDriver) -> None:
        """Test outbox entry → driver.apply() → SQLite insert flow."""
        driver.connect()
        driver.begin()

        # Simulate outbox entry creation
        outbox_id = driver.append(
            "st_outbox",
            {
                "wal_pos": 1,
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "driver": "sqlite",
                "op_kind": "insert",
                "payload": b'{"event_id": "evt_500", "text": "Outbox memory"}',
                "fingerprint": "abc123",
                "requeue_seq": 0,
                "retries": 0,
            },
        )

        assert isinstance(outbox_id, int)
        assert outbox_id > 0

        # Simulate driver processing outbox entry
        import json

        outbox_entries = driver.read("st_outbox", {"id": outbox_id})
        assert len(outbox_entries) == 1

        payload = json.loads(outbox_entries[0]["payload"])

        # Driver applies payload to target table
        driver.append(
            "st_epi",
            {
                "event_id": payload["event_id"],
                "text": payload["text"],
                "author_id": "person_001",
                "event_time": "2025-11-10T12:00:00Z",
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "privacy_band": "AMBER",
                "owner_id": "person_001",
                "visible_to": '["person_001"]',
                "created_at": "2025-11-10T12:00:00Z",
                "updated_at": "2025-11-10T12:00:00Z",
                "crdt_vector_clock": '{"device1": 1}',
                "crdt_tombstone": 0,
                "crdt_lamport": 1,
                "cognitive_trace_id": "test-trace-001",
            },
        )

        driver.commit()

        # Verify memory persisted
        results = driver.read("st_epi", {"event_id": "evt_500"})
        assert len(results) == 1
        assert results[0]["text"] == "Outbox memory"

        driver.close()

    def test_wal_to_outbox_to_driver_flow(self, driver: SQLiteDriver) -> None:
        """Test complete WAL → outbox → driver flow."""
        driver.connect()
        driver.begin()

        # 1. Write to WAL
        wal_pos = driver.append(
            "st_wal",
            {
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "topic": "memory.create",
                "envelope_json": '{"type": "memory.create", "data": {"text": "WAL memory"}}',
                "schema_uri": "https://example.com/schemas/memory",
                "schema_version": "1.0.0",
                "device_id": "device-001",
                "commit_ts": "2025-11-10T12:00:00Z",
            },
        )

        # 2. Create outbox entry pointing to WAL
        outbox_id = driver.append(
            "st_outbox",
            {
                "wal_pos": wal_pos,
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "driver": "sqlite",
                "op_kind": "insert",
                "payload": b'{"event_id": "evt_600", "text": "WAL memory"}',
                "fingerprint": "def456",
                "requeue_seq": 0,
                "retries": 0,
            },
        )
        assert outbox_id > 0

        # 3. Driver processes outbox → SQLite
        import json

        outbox_entries = driver.read("st_outbox", {"wal_pos": wal_pos})
        assert len(outbox_entries) == 1

        payload = json.loads(outbox_entries[0]["payload"])
        driver.append(
            "st_epi",
            {
                "event_id": payload["event_id"],
                "text": payload["text"],
                "author_id": "person_001",
                "event_time": "2025-11-10T12:00:00Z",
                "tenant_id": "tenant-001",
                "space_id": "personal:person_001",
                "privacy_band": "GREEN",
                "owner_id": "person_001",
                "visible_to": '["person_001"]',
                "created_at": "2025-11-10T12:00:00Z",
                "updated_at": "2025-11-10T12:00:00Z",
                "crdt_vector_clock": '{"device1": 1}',
                "crdt_tombstone": 0,
                "crdt_lamport": 1,
                "cognitive_trace_id": "test-trace-001",
            },
        )

        driver.commit()

        # Verify complete flow
        wal_entries = driver.read("st_wal", {"pos": wal_pos})
        assert len(wal_entries) == 1

        epi_entries = driver.read("st_epi", {"event_id": "evt_600"})
        assert len(epi_entries) == 1
        assert epi_entries[0]["text"] == "WAL memory"

        driver.close()
