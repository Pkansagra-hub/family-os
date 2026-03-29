"""
Tests for LocalColdArchive - Offline-Safe Local Archive (K1 SQLite)
=====================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.7

Test Coverage:
1. Construction and initialization
2. Schema creation
3. Archive operations
4. Restore operations
5. List/query operations
6. Delete operations
7. Checkpoint operations
8. Size/stats operations
9. Maintenance operations
10. Error handling
11. SLA compliance
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from k1.sessionstate.local_cold import (
    ARCHIVE_TABLES,
    SLA_RESTORE_MS,
    ArchiveEntry,
    ArchiveResult,
    LocalColdArchive,
    RestoreResult,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Get a temporary database path."""
    return tmp_path / "test_sessionstate.db"


@pytest.fixture
def archive(db_path: Path) -> LocalColdArchive:
    """Create a LocalColdArchive with temporary database."""
    arc = LocalColdArchive(db_path=db_path)
    yield arc
    arc.close()


@pytest.fixture
def sample_data() -> bytes:
    """Sample data for archiving."""
    return b"test_flatbuffer_serialized_data_0123456789" * 10


@pytest.fixture
def session_id() -> str:
    """Sample session ID."""
    return "test-session-12345678"


# =============================================================================
# TEST CLASS: Construction
# =============================================================================


class TestConstruction:
    """Test LocalColdArchive construction and initialization."""

    def test_construct_with_path(self, db_path: Path) -> None:
        """Test construction with explicit path."""
        archive = LocalColdArchive(db_path=db_path)
        assert archive.db_path == db_path
        assert not archive.is_closed
        archive.close()

    def test_construct_creates_directory(self, tmp_path: Path) -> None:
        """Test construction creates parent directory."""
        nested_path = tmp_path / "deep" / "nested" / "dir" / "test.db"
        archive = LocalColdArchive(db_path=nested_path)
        assert nested_path.parent.exists()
        archive.close()

    def test_construct_creates_database_file(self, db_path: Path) -> None:
        """Test construction creates database file."""
        archive = LocalColdArchive(db_path=db_path)
        assert db_path.exists()
        archive.close()

    def test_context_manager(self, db_path: Path) -> None:
        """Test context manager pattern."""
        with LocalColdArchive(db_path=db_path) as archive:
            assert not archive.is_closed
        assert archive.is_closed

    def test_close_is_idempotent(self, archive: LocalColdArchive) -> None:
        """Test close can be called multiple times."""
        archive.close()
        archive.close()  # Should not raise
        assert archive.is_closed


# =============================================================================
# TEST CLASS: Schema
# =============================================================================


class TestSchema:
    """Test database schema creation."""

    def test_all_tables_created(self, archive: LocalColdArchive) -> None:
        """Test all required tables are created."""
        cursor = archive._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor}

        for table in ARCHIVE_TABLES:
            assert table in tables

    def test_indexes_created(self, archive: LocalColdArchive) -> None:
        """Test indexes are created."""
        cursor = archive._conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row["name"] for row in cursor}

        assert "idx_checkpoints_session" in indexes
        assert "idx_beliefs_session" in indexes
        assert "idx_history_session" in indexes
        assert "idx_narrative_session" in indexes

    def test_wal_mode_enabled(self, archive: LocalColdArchive) -> None:
        """Test WAL mode is enabled."""
        cursor = archive._conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"


# =============================================================================
# TEST CLASS: Archive Operations
# =============================================================================


class TestArchiveOperations:
    """Test archive operations."""

    def test_archive_beliefs_active(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving beliefs_active section."""
        result = archive.archive(
            section="beliefs_active",
            data=sample_data,
            session_id=session_id,
            metadata={"reason": "eviction", "turn_id": "turn-1"},
        )

        assert result.success is True
        assert result.archive_id
        assert result.size_bytes == len(sample_data)
        assert result.duration_ms > 0
        assert result.error is None

    def test_archive_beliefs_history(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving beliefs_history section."""
        result = archive.archive(
            section="beliefs_history",
            data=sample_data,
            session_id=session_id,
        )
        assert result.success is True

    def test_archive_history_active(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving history_active section."""
        result = archive.archive(
            section="history_active",
            data=sample_data,
            session_id=session_id,
            metadata={"turn_range": "1-10"},
        )
        assert result.success is True

    def test_archive_history_recent(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving history_recent section."""
        result = archive.archive(
            section="history_recent",
            data=sample_data,
            session_id=session_id,
        )
        assert result.success is True

    def test_archive_narrative_active(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving narrative_active section."""
        result = archive.archive(
            section="narrative_active",
            data=sample_data,
            session_id=session_id,
            metadata={"thread_id": "main-thread"},
        )
        assert result.success is True

    def test_archive_invalid_section(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving invalid section fails gracefully."""
        result = archive.archive(
            section="invalid_section",
            data=sample_data,
            session_id=session_id,
        )
        assert result.success is False
        assert "Unknown section" in (result.error or "")

    def test_archive_empty_data(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test archiving empty data."""
        result = archive.archive(
            section="beliefs_active",
            data=b"",
            session_id=session_id,
        )
        assert result.success is True
        assert result.size_bytes == 0

    def test_archive_large_data(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test archiving large data (1MB)."""
        large_data = b"x" * (1024 * 1024)  # 1MB
        result = archive.archive(
            section="beliefs_active",
            data=large_data,
            session_id=session_id,
        )
        assert result.success is True
        assert result.size_bytes == 1024 * 1024

    def test_archive_with_no_metadata(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving without metadata."""
        result = archive.archive(
            section="beliefs_active",
            data=sample_data,
            session_id=session_id,
        )
        assert result.success is True

    def test_archive_generates_unique_ids(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test each archive generates unique ID."""
        ids = set()
        for _ in range(10):
            result = archive.archive(
                section="beliefs_active",
                data=sample_data,
                session_id=session_id,
            )
            assert result.archive_id not in ids
            ids.add(result.archive_id)


# =============================================================================
# TEST CLASS: Restore Operations
# =============================================================================


class TestRestoreOperations:
    """Test restore operations."""

    def test_restore_archived_data(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test restoring archived data."""
        # Archive
        archive_result = archive.archive(
            section="beliefs_active",
            data=sample_data,
            session_id=session_id,
        )

        # Restore
        restore_result = archive.restore(
            section="beliefs_active",
            session_id=session_id,
        )

        assert restore_result.success is True
        assert restore_result.data == sample_data
        assert restore_result.archive_id == archive_result.archive_id
        assert restore_result.size_bytes == len(sample_data)
        assert restore_result.error is None

    def test_restore_not_found(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restoring non-existent data."""
        result = archive.restore(
            section="beliefs_active",
            session_id=session_id,
        )
        assert result.success is False
        assert result.data is None
        assert "No archive found" in (result.error or "")

    def test_restore_by_archive_id(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test restoring by specific archive ID."""
        # Archive multiple
        first = archive.archive("beliefs_active", b"first", session_id)
        second = archive.archive("beliefs_active", b"second", session_id)

        # Restore specific one
        result = archive.restore(
            section="beliefs_active",
            session_id=session_id,
            filters={"archive_id": first.archive_id},
        )

        assert result.success is True
        assert result.data == b"first"
        assert result.archive_id == first.archive_id

    def test_restore_returns_latest(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restore returns most recent archive."""
        archive.archive("beliefs_active", b"first", session_id)
        time.sleep(0.01)  # Ensure different timestamp
        archive.archive("beliefs_active", b"second", session_id)
        time.sleep(0.01)
        archive.archive("beliefs_active", b"third", session_id)

        result = archive.restore("beliefs_active", session_id)

        assert result.success is True
        assert result.data == b"third"

    def test_restore_invalid_section(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restoring invalid section fails gracefully."""
        result = archive.restore(
            section="invalid_section",
            session_id=session_id,
        )
        assert result.success is False
        assert "Unknown section" in (result.error or "")

    def test_restore_different_sections_isolated(
        self, archive: LocalColdArchive, session_id: str
    ) -> None:
        """Test different sections don't interfere."""
        archive.archive("beliefs_active", b"beliefs_data", session_id)
        archive.archive("history_active", b"history_data", session_id)

        beliefs = archive.restore("beliefs_active", session_id)
        history = archive.restore("history_active", session_id)

        assert beliefs.data == b"beliefs_data"
        assert history.data == b"history_data"

    def test_restore_all(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restore_all returns multiple archives."""
        import time

        archive.archive("beliefs_active", b"data1", session_id)
        time.sleep(0.01)  # Ensure different timestamps
        archive.archive("beliefs_active", b"data2", session_id)
        time.sleep(0.01)
        archive.archive("beliefs_active", b"data3", session_id)

        results = archive.restore_all("beliefs_active", session_id)

        assert len(results) == 3
        # Should be newest first
        assert results[0].data == b"data3"
        assert results[1].data == b"data2"
        assert results[2].data == b"data1"

    def test_restore_all_with_limit(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restore_all respects limit."""
        for i in range(10):
            archive.archive("beliefs_active", f"data{i}".encode(), session_id)

        results = archive.restore_all("beliefs_active", session_id, limit=3)

        assert len(results) == 3


# =============================================================================
# TEST CLASS: List/Query Operations
# =============================================================================


class TestListOperations:
    """Test list and query operations."""

    def test_list_archives_empty(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test list_archives on empty database."""
        entries = archive.list_archives(session_id)
        assert entries == []

    def test_list_archives_all(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test list_archives returns all sections."""
        archive.archive("beliefs_active", b"data1", session_id)
        archive.archive("history_active", b"data2", session_id)
        archive.archive("narrative_active", b"data3", session_id)

        entries = archive.list_archives(session_id)

        assert len(entries) == 3
        sections = {e.section for e in entries}
        assert "beliefs_active" in sections
        assert "history_active" in sections
        assert "narrative_active" in sections

    def test_list_archives_by_section(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test list_archives with section filter."""
        archive.archive("beliefs_active", b"data1", session_id)
        archive.archive("beliefs_active", b"data2", session_id)
        archive.archive("history_active", b"data3", session_id)

        entries = archive.list_archives(session_id, section="beliefs_active")

        assert len(entries) == 2
        for e in entries:
            assert e.section == "beliefs_active"

    def test_list_archives_different_sessions(self, archive: LocalColdArchive) -> None:
        """Test list_archives isolates sessions."""
        archive.archive("beliefs_active", b"data1", "session-1")
        archive.archive("beliefs_active", b"data2", "session-2")
        archive.archive("beliefs_active", b"data3", "session-1")

        entries1 = archive.list_archives("session-1")
        entries2 = archive.list_archives("session-2")

        assert len(entries1) == 2
        assert len(entries2) == 1

    def test_list_archives_includes_metadata(
        self, archive: LocalColdArchive, session_id: str
    ) -> None:
        """Test list_archives includes metadata."""
        archive.archive(
            "beliefs_active",
            b"data",
            session_id,
            metadata={"reason": "eviction", "turn_id": "turn-5"},
        )

        entries = archive.list_archives(session_id)

        assert len(entries) == 1
        assert entries[0].metadata["reason"] == "eviction"
        assert entries[0].metadata["turn_id"] == "turn-5"

    def test_has_session_true(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test has_session returns True when data exists."""
        archive.archive("beliefs_active", b"data", session_id)
        assert archive.has_session(session_id) is True

    def test_has_session_false(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test has_session returns False when no data."""
        assert archive.has_session(session_id) is False


# =============================================================================
# TEST CLASS: Delete Operations
# =============================================================================


class TestDeleteOperations:
    """Test delete operations."""

    def test_delete_existing(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test deleting existing archive."""
        result = archive.archive("beliefs_active", b"data", session_id)
        archive_id = result.archive_id

        deleted = archive.delete(archive_id)

        assert deleted is True
        restore = archive.restore("beliefs_active", session_id)
        assert restore.success is False

    def test_delete_nonexistent(self, archive: LocalColdArchive) -> None:
        """Test deleting non-existent archive."""
        deleted = archive.delete("nonexistent-id")
        assert deleted is False

    def test_delete_session(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test deleting all archives for a session."""
        archive.archive("beliefs_active", b"data1", session_id)
        archive.archive("history_active", b"data2", session_id)
        archive.archive("narrative_active", b"data3", session_id)
        archive.checkpoint(session_id, b"checkpoint_data")

        deleted = archive.delete_session(session_id)

        assert deleted == 4
        assert archive.has_session(session_id) is False

    def test_delete_session_preserves_others(self, archive: LocalColdArchive) -> None:
        """Test delete_session only affects target session."""
        archive.archive("beliefs_active", b"data1", "session-1")
        archive.archive("beliefs_active", b"data2", "session-2")

        archive.delete_session("session-1")

        assert archive.has_session("session-1") is False
        assert archive.has_session("session-2") is True


# =============================================================================
# TEST CLASS: Checkpoint Operations
# =============================================================================


class TestCheckpointOperations:
    """Test checkpoint operations."""

    def test_checkpoint_and_restore(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test checkpoint creation and restore."""
        result = archive.checkpoint(
            session_id=session_id,
            data=sample_data,
            metadata={"version": 1},
        )

        assert result.success is True

        restore = archive.restore_checkpoint(session_id)

        assert restore.success is True
        assert restore.data == sample_data

    def test_restore_specific_checkpoint(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restoring specific checkpoint by ID."""
        first = archive.checkpoint(session_id, b"checkpoint1")
        archive.checkpoint(session_id, b"checkpoint2")

        restore = archive.restore_checkpoint(session_id, first.archive_id)

        assert restore.data == b"checkpoint1"

    def test_restore_latest_checkpoint(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restoring latest checkpoint."""
        archive.checkpoint(session_id, b"checkpoint1")
        time.sleep(0.01)
        archive.checkpoint(session_id, b"checkpoint2")
        time.sleep(0.01)
        archive.checkpoint(session_id, b"checkpoint3")

        restore = archive.restore_checkpoint(session_id)

        assert restore.data == b"checkpoint3"

    def test_list_checkpoints(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test listing checkpoints."""
        archive.checkpoint(session_id, b"cp1")
        archive.checkpoint(session_id, b"cp2")
        archive.checkpoint(session_id, b"cp3")

        entries = archive.list_checkpoints(session_id)

        assert len(entries) == 3
        for e in entries:
            assert e.section == "checkpoint"

    def test_prune_checkpoints(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test pruning old checkpoints."""
        for i in range(10):
            archive.checkpoint(session_id, f"checkpoint{i}".encode())
            time.sleep(0.005)  # Ensure different timestamps

        deleted = archive.prune_checkpoints(session_id, keep_count=3)

        assert deleted == 7
        remaining = archive.list_checkpoints(session_id)
        assert len(remaining) == 3

    def test_prune_checkpoints_no_action(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test prune does nothing when under keep_count."""
        archive.checkpoint(session_id, b"cp1")
        archive.checkpoint(session_id, b"cp2")

        deleted = archive.prune_checkpoints(session_id, keep_count=5)

        assert deleted == 0


# =============================================================================
# TEST CLASS: Size/Stats Operations
# =============================================================================


class TestSizeStats:
    """Test size and statistics operations."""

    def test_get_total_size_empty(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test total size on empty database."""
        assert archive.get_total_size() == 0
        assert archive.get_total_size(session_id) == 0

    def test_get_total_size(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test total size calculation."""
        archive.archive("beliefs_active", b"1234567890", session_id)  # 10 bytes
        archive.archive("history_active", b"12345", session_id)  # 5 bytes

        assert archive.get_total_size(session_id) == 15
        assert archive.get_total_size() == 15

    def test_get_archive_count(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test archive count."""
        archive.archive("beliefs_active", b"data1", session_id)
        archive.archive("beliefs_active", b"data2", session_id)
        archive.archive("history_active", b"data3", session_id)

        assert archive.get_archive_count(session_id) == 3
        assert archive.get_archive_count() == 3

    def test_get_stats(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test stats breakdown."""
        archive.archive("beliefs_active", b"data1", session_id)
        archive.archive("history_active", b"data2", session_id)
        archive.checkpoint(session_id, b"checkpoint")

        stats = archive.get_stats(session_id)

        assert stats["archive_count"] == 3
        assert stats["total_size_bytes"] > 0
        assert "st_beliefs_archive" in stats["tables"]
        assert "st_history_archive" in stats["tables"]
        assert "st_session_checkpoints" in stats["tables"]


# =============================================================================
# TEST CLASS: Maintenance Operations
# =============================================================================


class TestMaintenance:
    """Test maintenance operations."""

    def test_vacuum(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test vacuum operation."""
        # Add and delete data
        for i in range(100):
            archive.archive("beliefs_active", b"x" * 1000, session_id)
        archive.delete_session(session_id)

        # Vacuum should not raise
        archive.vacuum()


# =============================================================================
# TEST CLASS: Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling."""

    def test_archive_after_close(
        self, archive: LocalColdArchive, sample_data: bytes, session_id: str
    ) -> None:
        """Test archiving after close handles gracefully."""
        archive.close()

        # Should not raise, but will fail
        result = archive.archive("beliefs_active", sample_data, session_id)
        assert result.success is False

    def test_restore_after_close(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restoring after close handles gracefully."""
        archive.close()

        result = archive.restore("beliefs_active", session_id)
        assert result.success is False


# =============================================================================
# TEST CLASS: SLA Compliance
# =============================================================================


class TestSLACompliance:
    """Test SLA compliance for restore operations."""

    def test_restore_meets_sla(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test restore typically meets SLA."""
        # Archive some data
        archive.archive("beliefs_active", b"x" * 10000, session_id)

        # Restore should be fast
        result = archive.restore("beliefs_active", session_id)

        assert result.success is True
        assert result.duration_ms < SLA_RESTORE_MS

    def test_bulk_restore_performance(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test bulk restore performance."""
        # Archive 100 entries
        for i in range(100):
            archive.archive("beliefs_active", f"data{i}".encode() * 100, session_id)

        # Restore latest should still be fast
        start = time.perf_counter()
        result = archive.restore("beliefs_active", session_id)
        duration_ms = (time.perf_counter() - start) * 1000

        assert result.success is True
        assert duration_ms < SLA_RESTORE_MS * 2  # Allow some margin


# =============================================================================
# TEST CLASS: Section Table Mapping
# =============================================================================


class TestSectionTableMapping:
    """Test section to table mapping."""

    def test_beliefs_sections_map_correctly(self, archive: LocalColdArchive) -> None:
        """Test beliefs sections map to st_beliefs_archive."""
        assert archive._get_table_for_section("beliefs_active") == "st_beliefs_archive"
        assert archive._get_table_for_section("beliefs_history") == "st_beliefs_archive"

    def test_history_sections_map_correctly(self, archive: LocalColdArchive) -> None:
        """Test history sections map to st_history_archive."""
        assert archive._get_table_for_section("history_active") == "st_history_archive"
        assert archive._get_table_for_section("history_recent") == "st_history_archive"

    def test_narrative_sections_map_correctly(self, archive: LocalColdArchive) -> None:
        """Test narrative sections map to st_narrative_archive."""
        assert archive._get_table_for_section("narrative_active") == "st_narrative_archive"

    def test_checkpoint_maps_correctly(self, archive: LocalColdArchive) -> None:
        """Test checkpoint maps to st_session_checkpoints."""
        assert archive._get_table_for_section("checkpoint") == "st_session_checkpoints"

    def test_unknown_section_raises(self, archive: LocalColdArchive) -> None:
        """Test unknown section raises ValueError."""
        with pytest.raises(ValueError, match="Unknown section"):
            archive._get_table_for_section("unknown_xyz")


# =============================================================================
# TEST CLASS: Dataclass Validation
# =============================================================================


class TestDataclasses:
    """Test dataclass structures."""

    def test_archive_entry_dataclass(self) -> None:
        """Test ArchiveEntry dataclass."""
        entry = ArchiveEntry(
            archive_id="test-id",
            session_id="session-123",
            section="beliefs_active",
            size_bytes=1024,
            created_at_ms=1700000000000,
            metadata={"reason": "eviction"},
        )
        assert entry.archive_id == "test-id"
        assert entry.metadata["reason"] == "eviction"

    def test_archive_result_dataclass(self) -> None:
        """Test ArchiveResult dataclass."""
        result = ArchiveResult(
            success=True,
            archive_id="test-id",
            size_bytes=1024,
            duration_ms=5.5,
        )
        assert result.success is True
        assert result.error is None

    def test_restore_result_dataclass(self) -> None:
        """Test RestoreResult dataclass."""
        result = RestoreResult(
            success=True,
            data=b"test_data",
            archive_id="test-id",
            size_bytes=9,
            duration_ms=2.5,
        )
        assert result.success is True
        assert result.data == b"test_data"


# =============================================================================
# TEST CLASS: Concurrent Access
# =============================================================================


class TestConcurrentAccess:
    """Test concurrent access patterns."""

    def test_multiple_archives_same_session(
        self, archive: LocalColdArchive, session_id: str
    ) -> None:
        """Test multiple archives to same session work correctly."""
        # Simulate rapid archiving
        for i in range(50):
            result = archive.archive(
                "beliefs_active",
                f"data{i}".encode(),
                session_id,
            )
            assert result.success is True

        entries = archive.list_archives(session_id)
        assert len(entries) == 50

    def test_interleaved_archive_restore(self, archive: LocalColdArchive, session_id: str) -> None:
        """Test interleaved archive and restore operations."""
        import time

        archive.archive("beliefs_active", b"initial", session_id)

        for i in range(20):
            time.sleep(0.005)  # Ensure different timestamps
            # Archive new
            archive.archive("beliefs_active", f"data{i}".encode(), session_id)
            # Restore latest
            result = archive.restore("beliefs_active", session_id)
            assert result.data == f"data{i}".encode()
