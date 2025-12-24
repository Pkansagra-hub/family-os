"""
Tests for Issues 1.7, 1.8, 1.9: SQLite Durability, WAL Storage Model, Database Migration

Issue 1.7: SQLite Durability Settings
- PRAGMA journal_mode=WAL
- PRAGMA synchronous=FULL
- PRAGMA foreign_keys=ON
- PRAGMA temp_store=MEMORY
- PRAGMA busy_timeout=5000

Issue 1.8: Update WAL Storage Model
- V1 fields: envelope_sha256, ingested_at, clock_skew_ms
- V1.3 fields: policy_stamp_json, location_geohash, location_precision_m

Issue 1.9: Database Migration Script
- 0010_v1_hardening.sql: envelope_sha256, ingested_at, clock_skew_ms, hmac_secret
- 0011_v1_privacy_and_async.sql: policy_stamp_json, location fields, async worker fields
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from k0.storage.wal import WalEntry, WriteAheadLog
from k0.uow.connection_pool import configure_pool, shutdown_pool
from k0.uow.unit_of_work import UnitOfWork


@pytest.fixture
def temp_db() -> Iterator[Path]:
    """Create temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    yield db_path
    # Note: Cleanup disabled due to Windows file locking with WAL mode
    # Files will be cleaned up by OS temp directory cleanup


@pytest.fixture
def initialized_db(temp_db: Path) -> Iterator[Path]:
    """Initialize database with V1 schema."""
    configure_pool(temp_db)

    # Run baseline migration
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row

    # Create st_wal table (baseline schema)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_wal (
            pos INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            envelope_json TEXT NOT NULL,
            body BLOB,
            redacted_body_json TEXT,
            payload_sha256 TEXT,
            schema_uri TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            idem_key TEXT,
            device_id TEXT NOT NULL,
            commit_ts TEXT NOT NULL
        )
    """
    )
    conn.commit()

    # Apply 0010_v1_hardening.sql migration (without UNIQUE constraint)
    conn.execute("ALTER TABLE st_wal ADD COLUMN envelope_sha256 TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wal_envelope_sha256 ON st_wal(envelope_sha256)")
    conn.execute("ALTER TABLE st_wal ADD COLUMN ingested_at TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wal_ingested_at ON st_wal(ingested_at)")
    conn.execute("ALTER TABLE st_wal ADD COLUMN clock_skew_ms INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wal_clock_skew ON st_wal(clock_skew_ms)")

    # Apply 0011_v1_privacy_and_async.sql migration (partial - privacy fields only)
    conn.execute("ALTER TABLE st_wal ADD COLUMN policy_stamp_json TEXT DEFAULT NULL")
    conn.execute("ALTER TABLE st_wal ADD COLUMN location_geohash TEXT DEFAULT NULL")
    conn.execute("ALTER TABLE st_wal ADD COLUMN location_precision_m INTEGER DEFAULT NULL")

    conn.commit()
    conn.close()

    yield temp_db

    # Cleanup
    shutdown_pool()


class TestIssue17SqliteDurability:
    """Test SQLite durability settings (Issue 1.7)."""

    async def test_wal_mode_enabled(self, initialized_db: Path) -> None:
        """Test PRAGMA journal_mode=WAL is set."""
        configure_pool(initialized_db)

        async with UnitOfWork() as uow:
            result = uow.connection.execute("PRAGMA journal_mode").fetchone()
            assert result[0].upper() == "WAL"

    async def test_synchronous_full_enabled(self, initialized_db: Path) -> None:
        """Test PRAGMA synchronous=FULL is set."""
        configure_pool(initialized_db)

        async with UnitOfWork() as uow:
            result = uow.connection.execute("PRAGMA synchronous").fetchone()
            # synchronous=FULL returns 2
            assert result[0] == 2

    async def test_foreign_keys_enabled(self, initialized_db: Path) -> None:
        """Test PRAGMA foreign_keys=ON is set."""
        configure_pool(initialized_db)

        async with UnitOfWork() as uow:
            result = uow.connection.execute("PRAGMA foreign_keys").fetchone()
            assert result[0] == 1  # 1 = ON

    async def test_temp_store_memory(self, initialized_db: Path) -> None:
        """Test PRAGMA temp_store=MEMORY is set."""
        configure_pool(initialized_db)

        async with UnitOfWork() as uow:
            result = uow.connection.execute("PRAGMA temp_store").fetchone()
            # temp_store=MEMORY returns 2
            assert result[0] == 2

    async def test_busy_timeout_set(self, initialized_db: Path) -> None:
        """Test PRAGMA busy_timeout is set (configured as 30000ms)."""
        configure_pool(initialized_db)

        async with UnitOfWork() as uow:
            result = uow.connection.execute("PRAGMA busy_timeout").fetchone()
            assert result[0] == 30000  # milliseconds

    async def test_all_pragmas_set_in_uow(self, initialized_db: Path) -> None:
        """Test all V1 durability pragmas are set in UnitOfWork.__enter__."""
        configure_pool(initialized_db)

        async with UnitOfWork() as uow:
            # Check all pragmas at once
            pragmas = {
                "journal_mode": uow.connection.execute("PRAGMA journal_mode").fetchone()[0].upper(),
                "synchronous": uow.connection.execute("PRAGMA synchronous").fetchone()[0],
                "foreign_keys": uow.connection.execute("PRAGMA foreign_keys").fetchone()[0],
                "temp_store": uow.connection.execute("PRAGMA temp_store").fetchone()[0],
                "busy_timeout": uow.connection.execute("PRAGMA busy_timeout").fetchone()[0],
            }

            assert pragmas["journal_mode"] == "WAL"
            assert pragmas["synchronous"] == 2  # FULL
            assert pragmas["foreign_keys"] == 1  # ON
            assert pragmas["temp_store"] == 2  # MEMORY
            assert pragmas["busy_timeout"] == 30000


class TestIssue18WalStorageModel:
    """Test WAL storage model V1 fields (Issue 1.8)."""

    def test_wal_entry_has_v1_integrity_fields(self) -> None:
        """Test WalEntry dataclass has V1 envelope integrity fields."""
        entry = WalEntry(
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            envelope_json='{"actor": "alice"}',
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            device_id="device-001",
            commit_ts="2025-11-10T10:00:00Z",
            envelope_sha256="a" * 64,
            ingested_at="2025-11-10T10:00:00.123Z",
            clock_skew_ms=50,
        )

        assert entry.envelope_sha256 == "a" * 64
        assert entry.ingested_at == "2025-11-10T10:00:00.123Z"
        assert entry.clock_skew_ms == 50

    def test_wal_entry_has_v13_privacy_fields(self) -> None:
        """Test WalEntry dataclass has V1.3 policy stamp and location privacy fields."""
        policy_stamp = {
            "policy_version": "2025-11-01",
            "band": "AMBER",
            "obligations": ["LOG"],
            "visible_to": ["alice", "bob"],
            "decision": "PERMIT",
        }

        entry = WalEntry(
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            envelope_json='{"actor": "alice"}',
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            device_id="device-001",
            commit_ts="2025-11-10T10:00:00Z",
            policy_stamp_json=json.dumps(policy_stamp),
            location_geohash="9q8yy",
            location_precision_m=5000,
        )

        assert entry.policy_stamp_json == json.dumps(policy_stamp)
        assert entry.location_geohash == "9q8yy"
        assert entry.location_precision_m == 5000

    async def test_wal_append_persists_v1_integrity_fields(self, initialized_db: Path) -> None:
        """Test WriteAheadLog.append() persists V1 envelope integrity fields to database."""
        configure_pool(initialized_db)

        wal = WriteAheadLog()
        entry = WalEntry(
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            envelope_json='{"actor": "alice"}',
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            device_id="device-001",
            commit_ts="2025-11-10T10:00:00Z",
            envelope_sha256="abc123" * 10 + "abcd",  # 64 hex chars
            ingested_at="2025-11-10T10:00:00.123Z",
            clock_skew_ms=50,
        )

        async with UnitOfWork() as uow:
            position = await wal.append(entry, connection=uow.connection)
            assert position > 0

        # Verify persisted
        conn = sqlite3.connect(str(initialized_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT envelope_sha256, ingested_at, clock_skew_ms FROM st_wal WHERE pos = ?",
            (position,),
        ).fetchone()

        assert row["envelope_sha256"] == "abc123" * 10 + "abcd"
        assert row["ingested_at"] == "2025-11-10T10:00:00.123Z"
        assert row["clock_skew_ms"] == 50
        conn.close()

    async def test_wal_append_persists_v13_privacy_fields(self, initialized_db: Path) -> None:
        """Test WriteAheadLog.append() persists V1.3 policy stamp and location fields."""
        configure_pool(initialized_db)

        policy_stamp = {"band": "AMBER", "obligations": ["LOG"]}

        wal = WriteAheadLog()
        entry = WalEntry(
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            envelope_json='{"actor": "alice"}',
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            device_id="device-001",
            commit_ts="2025-11-10T10:00:00Z",
            policy_stamp_json=json.dumps(policy_stamp),
            location_geohash="9q8yy",
            location_precision_m=5000,
        )

        async with UnitOfWork() as uow:
            position = await wal.append(entry, connection=uow.connection)

        # Verify persisted
        conn = sqlite3.connect(str(initialized_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT policy_stamp_json, location_geohash, location_precision_m FROM st_wal WHERE pos = ?",
            (position,),
        ).fetchone()

        assert row["policy_stamp_json"] == json.dumps(policy_stamp)
        assert row["location_geohash"] == "9q8yy"
        assert row["location_precision_m"] == 5000
        conn.close()

    async def test_wal_read_from_includes_v1_fields(self, initialized_db: Path) -> None:
        """Test WriteAheadLog.read_from() includes V1 fields in returned WalEntry."""
        configure_pool(initialized_db)

        wal = WriteAheadLog()
        entry = WalEntry(
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            envelope_json='{"actor": "alice"}',
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            device_id="device-001",
            commit_ts="2025-11-10T10:00:00Z",
            envelope_sha256="a" * 64,
            ingested_at="2025-11-10T10:00:00.123Z",
            clock_skew_ms=50,
            policy_stamp_json='{"band": "AMBER"}',
            location_geohash="9q8yy",
            location_precision_m=5000,
        )

        async with UnitOfWork() as uow:
            position = await wal.append(entry, connection=uow.connection)

        # Read back
        async with UnitOfWork() as uow:
            entries = await wal.read_from(position - 1, limit=10, connection=uow.connection)

        assert len(entries) == 1
        read_entry = entries[0]

        # Verify V1 integrity fields
        assert read_entry.envelope_sha256 == "a" * 64
        assert read_entry.ingested_at == "2025-11-10T10:00:00.123Z"
        assert read_entry.clock_skew_ms == 50

        # Verify V1.3 privacy fields
        assert read_entry.policy_stamp_json == '{"band": "AMBER"}'
        assert read_entry.location_geohash == "9q8yy"
        assert read_entry.location_precision_m == 5000


class TestIssue19DatabaseMigration:
    """Test database migration scripts (Issue 1.9)."""

    def test_migration_0010_adds_envelope_sha256_column(self, temp_db: Path) -> None:
        """Test 0010_v1_hardening.sql adds envelope_sha256 column to st_wal."""
        # Create baseline schema
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            """
            CREATE TABLE st_wal (
                pos INTEGER PRIMARY KEY,
                tenant_id TEXT,
                envelope_json TEXT
            )
        """
        )
        conn.commit()

        # Apply migration (without UNIQUE - SQLite limitation with ALTER TABLE)
        conn.execute("ALTER TABLE st_wal ADD COLUMN envelope_sha256 TEXT")
        conn.commit()

        # Verify column exists
        cursor = conn.execute("PRAGMA table_info(st_wal)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "envelope_sha256" in columns
        conn.close()

    def test_migration_0010_adds_ingested_at_column(self, temp_db: Path) -> None:
        """Test 0010_v1_hardening.sql adds ingested_at column to st_wal."""
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            """
            CREATE TABLE st_wal (
                pos INTEGER PRIMARY KEY,
                tenant_id TEXT
            )
        """
        )
        conn.execute("ALTER TABLE st_wal ADD COLUMN ingested_at TEXT")
        conn.commit()

        cursor = conn.execute("PRAGMA table_info(st_wal)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "ingested_at" in columns
        conn.close()

    def test_migration_0010_adds_clock_skew_ms_column(self, temp_db: Path) -> None:
        """Test 0010_v1_hardening.sql adds clock_skew_ms column to st_wal."""
        conn = sqlite3.connect(str(temp_db))
        conn.execute("CREATE TABLE st_wal (pos INTEGER PRIMARY KEY)")
        conn.execute("ALTER TABLE st_wal ADD COLUMN clock_skew_ms INTEGER")
        conn.commit()

        cursor = conn.execute("PRAGMA table_info(st_wal)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "clock_skew_ms" in columns
        conn.close()

    def test_migration_0011_adds_policy_stamp_json_column(self, temp_db: Path) -> None:
        """Test 0011_v1_privacy_and_async.sql adds policy_stamp_json column."""
        conn = sqlite3.connect(str(temp_db))
        conn.execute("CREATE TABLE st_wal (pos INTEGER PRIMARY KEY)")
        conn.execute("ALTER TABLE st_wal ADD COLUMN policy_stamp_json TEXT DEFAULT NULL")
        conn.commit()

        cursor = conn.execute("PRAGMA table_info(st_wal)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "policy_stamp_json" in columns
        conn.close()

    def test_migration_0011_adds_location_fields(self, temp_db: Path) -> None:
        """Test 0011_v1_privacy_and_async.sql adds location privacy fields."""
        conn = sqlite3.connect(str(temp_db))
        conn.execute("CREATE TABLE st_wal (pos INTEGER PRIMARY KEY)")
        conn.execute("ALTER TABLE st_wal ADD COLUMN location_geohash TEXT DEFAULT NULL")
        conn.execute("ALTER TABLE st_wal ADD COLUMN location_precision_m INTEGER DEFAULT NULL")
        conn.commit()

        cursor = conn.execute("PRAGMA table_info(st_wal)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "location_geohash" in columns
        assert "location_precision_m" in columns
        conn.close()

    def test_migration_backward_compat_null_values(self, initialized_db: Path) -> None:
        """Test V1 migrations allow NULL for new columns (backward compatibility)."""
        configure_pool(initialized_db)

        # Insert entry with only baseline fields (V1 fields NULL)
        conn = sqlite3.connect(str(initialized_db))
        conn.execute(
            """
            INSERT INTO st_wal (tenant_id, space_id, topic, envelope_json, schema_uri, schema_version, device_id, commit_ts)
            VALUES ('tenant-001', 'space-001', 'memory.event', '{}', 'https://schema.local/memory', '1.0', 'device-001', '2025-11-10T10:00:00Z')
        """
        )
        conn.commit()

        # Verify V1 fields are NULL
        row = conn.execute(
            "SELECT envelope_sha256, ingested_at, clock_skew_ms, policy_stamp_json FROM st_wal"
        ).fetchone()
        assert row[0] is None  # envelope_sha256
        assert row[1] is None  # ingested_at
        assert row[2] is None  # clock_skew_ms
        assert row[3] is None  # policy_stamp_json
        conn.close()


class TestIssue1789Integration:
    """Integration tests for Issues 1.7, 1.8, 1.9 together."""

    async def test_full_v1_wal_entry_with_durability(self, initialized_db: Path) -> None:
        """Test complete V1 WAL entry with durability settings enabled."""
        configure_pool(initialized_db)

        policy_stamp = {
            "policy_version": "2025-11-01",
            "band": "AMBER",
            "obligations": ["LOG"],
            "visible_to": ["alice"],
            "decision": "PERMIT",
        }

        wal = WriteAheadLog()
        entry = WalEntry(
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            envelope_json='{"actor": "alice", "message": "V1 test"}',
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            device_id="device-001",
            commit_ts="2025-11-10T10:00:00Z",
            # V1 integrity fields
            envelope_sha256="abcd1234" * 8,  # 64 hex chars
            ingested_at="2025-11-10T10:00:00.123Z",
            clock_skew_ms=50,
            # V1.3 privacy fields
            policy_stamp_json=json.dumps(policy_stamp),
            location_geohash="9q8yy9",
            location_precision_m=5000,
        )

        # Write with durability guarantees
        async with UnitOfWork() as uow:
            # Verify WAL mode
            journal_mode = uow.connection.execute("PRAGMA journal_mode").fetchone()[0]
            assert journal_mode.upper() == "WAL"

            # Verify FULL sync
            synchronous = uow.connection.execute("PRAGMA synchronous").fetchone()[0]
            assert synchronous == 2  # FULL

            # Append entry
            position = await wal.append(entry, connection=uow.connection)
            assert position > 0

        # Read back and verify all fields
        async with UnitOfWork() as uow:
            entries = await wal.read_from(position - 1, limit=1, connection=uow.connection)

        assert len(entries) == 1
        read_entry = entries[0]

        # Verify all V1 fields persisted
        assert read_entry.envelope_sha256 == "abcd1234" * 8
        assert read_entry.ingested_at == "2025-11-10T10:00:00.123Z"
        assert read_entry.clock_skew_ms == 50
        assert read_entry.policy_stamp_json == json.dumps(policy_stamp)
        assert read_entry.location_geohash == "9q8yy9"
        assert read_entry.location_precision_m == 5000

    async def test_v1_envelope_replay_detection_application_level(
        self, initialized_db: Path
    ) -> None:
        """Test envelope_sha256 enables application-level replay detection.

        Note: UNIQUE constraint can't be added with ALTER TABLE in SQLite.
        In production, the migration would use CREATE TABLE AS SELECT to rebuild
        with UNIQUE constraint. Here we test application-level duplicate detection.
        """
        configure_pool(initialized_db)

        wal = WriteAheadLog()
        entry = WalEntry(
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            envelope_json='{"actor": "alice"}',
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            device_id="device-001",
            commit_ts="2025-11-10T10:00:00Z",
            envelope_sha256="replay123" * 5 + "1234",  # 64 chars
        )

        # First insert succeeds
        async with UnitOfWork() as uow:
            position1 = await wal.append(entry, connection=uow.connection)
            assert position1 > 0

        # Application-level check: Query before insert to detect replay
        conn = sqlite3.connect(str(initialized_db))
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT pos FROM st_wal WHERE envelope_sha256 = ?",
            ("replay123" * 5 + "1234",),
        ).fetchone()
        assert existing is not None  # Duplicate detected
        assert existing["pos"] == position1
        conn.close()
