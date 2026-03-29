"""
LocalColdTier Unit Tests
========================

Tests for k1/sessionstate/tiers/local_cold.py

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.4 Implement Tier Managers
ISSUE: 2.4.3 (LocalColdTier)

Test Categories:
1. Initialization & Properties
2. Archive Operations
3. Restore Operations
4. Checkpoint Operations
5. List Operations
6. Delete Operations
7. Size & Stats Operations
8. Snapshot & Metrics
9. Factory Function
10. Edge Cases
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k1.sessionstate.tiers.local_cold import (
    ARCHIVABLE_SECTIONS,
    DEFAULT_MAX_AGE_DAYS,
    RESTORE_SLA_MS,
    ArchiveInfo,
    ArchiveResult,
    LocalColdSnapshot,
    LocalColdTier,
    RestoreResult,
    create_local_cold_tier,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_storage() -> MagicMock:
    """Create a mock LocalColdArchive."""
    storage = MagicMock()
    storage.is_closed = False
    return storage


@pytest.fixture
def tier(mock_storage: MagicMock) -> LocalColdTier:
    """Create a LocalColdTier with mock storage."""
    return LocalColdTier(storage=mock_storage, session_id="test-session-123")


@pytest.fixture
def tier_no_storage() -> LocalColdTier:
    """Create a LocalColdTier without storage."""
    return LocalColdTier(session_id="test-session-456")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Get a temporary database path."""
    return tmp_path / "test_local_cold.db"


@pytest.fixture
def sample_data() -> bytes:
    """Sample data for archiving."""
    return b"test_flatbuffer_serialized_data_0123456789" * 10


# =============================================================================
# INITIALIZATION & PROPERTIES TESTS
# =============================================================================


class TestInitialization:
    """Tests for LocalColdTier initialization."""

    def test_init_creates_tier(self, mock_storage: MagicMock):
        """LocalColdTier initializes successfully."""
        tier = LocalColdTier(storage=mock_storage, session_id="test-123")
        assert tier is not None

    def test_init_with_session_id(self, mock_storage: MagicMock):
        """LocalColdTier accepts session_id."""
        tier = LocalColdTier(storage=mock_storage, session_id="abc-123")
        assert tier.session_id == "abc-123"

    def test_init_without_storage(self):
        """LocalColdTier can initialize without storage."""
        tier = LocalColdTier(session_id="test-123")
        assert tier.is_available is False

    def test_init_without_session_id(self, mock_storage: MagicMock):
        """LocalColdTier can initialize without session_id."""
        tier = LocalColdTier(storage=mock_storage)
        assert tier.session_id == ""


class TestProperties:
    """Tests for LocalColdTier properties."""

    def test_tier_name(self, tier: LocalColdTier):
        """tier_name returns 'local_cold'."""
        assert tier.tier_name == "local_cold"

    def test_session_id_getter(self, tier: LocalColdTier):
        """session_id getter returns correct value."""
        assert tier.session_id == "test-session-123"

    def test_session_id_setter(self, tier: LocalColdTier):
        """session_id can be set."""
        tier.session_id = "new-session-456"
        assert tier.session_id == "new-session-456"

    def test_is_available_with_storage(self, tier: LocalColdTier):
        """is_available returns True when storage attached."""
        assert tier.is_available is True

    def test_is_available_without_storage(self, tier_no_storage: LocalColdTier):
        """is_available returns False without storage."""
        assert tier_no_storage.is_available is False

    def test_is_available_with_closed_storage(self, mock_storage: MagicMock):
        """is_available returns False when storage is closed."""
        mock_storage.is_closed = True
        tier = LocalColdTier(storage=mock_storage, session_id="test")
        assert tier.is_available is False

    def test_restore_sla_ms(self, tier: LocalColdTier):
        """restore_sla_ms returns correct value."""
        assert tier.restore_sla_ms == 50.0

    def test_sla_compliance_rate_initial(self, tier: LocalColdTier):
        """sla_compliance_rate is 1.0 initially."""
        assert tier.sla_compliance_rate == 1.0


# =============================================================================
# ARCHIVE OPERATIONS TESTS
# =============================================================================


class TestArchiveOperations:
    """Tests for archive operations."""

    def test_archive_success(
        self, tier: LocalColdTier, mock_storage: MagicMock, sample_data: bytes
    ):
        """archive returns success result."""
        mock_storage.archive.return_value = MagicMock(
            success=True,
            archive_id="arch-123",
            size_bytes=len(sample_data),
            error=None,
        )

        result = tier.archive("beliefs_history", sample_data, {"reason": "eviction"})

        assert result.success is True
        assert result.archive_id == "arch-123"
        assert result.size_bytes == len(sample_data)
        assert result.duration_ms > 0

    def test_archive_without_storage(self, tier_no_storage: LocalColdTier, sample_data: bytes):
        """archive fails without storage."""
        result = tier_no_storage.archive("beliefs_history", sample_data)
        assert result.success is False
        assert "No storage attached" in result.error

    def test_archive_without_session_id(self, mock_storage: MagicMock, sample_data: bytes):
        """archive fails without session_id."""
        tier = LocalColdTier(storage=mock_storage, session_id="")
        result = tier.archive("beliefs_history", sample_data)
        assert result.success is False
        assert "No session_id" in result.error

    def test_archive_calls_storage(
        self, tier: LocalColdTier, mock_storage: MagicMock, sample_data: bytes
    ):
        """archive delegates to storage."""
        mock_storage.archive.return_value = MagicMock(
            success=True, archive_id="arch-123", size_bytes=100, error=None
        )

        tier.archive("beliefs_history", sample_data, {"reason": "test"})

        mock_storage.archive.assert_called_once()
        call_args = mock_storage.archive.call_args
        assert call_args.kwargs["section"] == "beliefs_history"
        assert call_args.kwargs["data"] == sample_data
        assert call_args.kwargs["session_id"] == "test-session-123"

    def test_can_archive_valid_sections(self, tier: LocalColdTier):
        """can_archive returns True for valid sections."""
        for section in ARCHIVABLE_SECTIONS:
            assert tier.can_archive(section) is True

    def test_can_archive_beliefs_prefix(self, tier: LocalColdTier):
        """can_archive returns True for beliefs_ prefix."""
        assert tier.can_archive("beliefs_custom") is True

    def test_can_archive_invalid_section(self, tier: LocalColdTier):
        """can_archive returns False for invalid sections."""
        assert tier.can_archive("control") is False
        assert tier.can_archive("meta") is False


class TestArchiveResult:
    """Tests for ArchiveResult dataclass."""

    def test_create_success(self):
        """ArchiveResult success can be created."""
        result = ArchiveResult(
            success=True,
            archive_id="arch-123",
            size_bytes=1000,
            duration_ms=5.5,
        )
        assert result.success is True
        assert result.archive_id == "arch-123"

    def test_failure_factory(self):
        """ArchiveResult.failure creates failure result."""
        result = ArchiveResult.failure("test error", duration_ms=10.5)
        assert result.success is False
        assert result.error == "test error"
        assert result.duration_ms == 10.5

    def test_to_dict(self):
        """ArchiveResult.to_dict returns dict."""
        result = ArchiveResult(
            success=True,
            archive_id="arch-123",
            size_bytes=1000,
            duration_ms=5.123,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["archive_id"] == "arch-123"
        assert d["size_bytes"] == 1000


# =============================================================================
# RESTORE OPERATIONS TESTS
# =============================================================================


class TestRestoreOperations:
    """Tests for restore operations."""

    def test_restore_success(
        self, tier: LocalColdTier, mock_storage: MagicMock, sample_data: bytes
    ):
        """restore returns success result."""
        mock_storage.restore.return_value = MagicMock(
            success=True,
            data=sample_data,
            archive_id="arch-123",
            size_bytes=len(sample_data),
            duration_ms=5.0,
            error=None,
        )

        result = tier.restore("beliefs_history")

        assert result.success is True
        assert result.data == sample_data
        assert result.archive_id == "arch-123"
        assert result.sla_met is True

    def test_restore_without_storage(self, tier_no_storage: LocalColdTier):
        """restore fails without storage."""
        result = tier_no_storage.restore("beliefs_history")
        assert result.success is False
        assert "No storage attached" in result.error

    def test_restore_without_session_id(self, mock_storage: MagicMock):
        """restore fails without session_id."""
        tier = LocalColdTier(storage=mock_storage, session_id="")
        result = tier.restore("beliefs_history")
        assert result.success is False
        assert "No session_id" in result.error

    def test_restore_calls_storage(self, tier: LocalColdTier, mock_storage: MagicMock):
        """restore delegates to storage."""
        mock_storage.restore.return_value = MagicMock(
            success=True,
            data=b"test",
            archive_id="arch-123",
            size_bytes=4,
            duration_ms=1.0,
            error=None,
        )

        tier.restore("beliefs_history", {"archive_id": "specific-id"})

        mock_storage.restore.assert_called_once()
        call_args = mock_storage.restore.call_args
        assert call_args.kwargs["section"] == "beliefs_history"
        assert call_args.kwargs["session_id"] == "test-session-123"
        assert call_args.kwargs["filters"] == {"archive_id": "specific-id"}

    def test_restore_increments_total_restores(self, tier: LocalColdTier, mock_storage: MagicMock):
        """restore increments total_restores counter."""
        mock_storage.restore.return_value = MagicMock(
            success=True,
            data=b"test",
            archive_id="arch-123",
            size_bytes=4,
            duration_ms=1.0,
            error=None,
        )

        initial = tier._total_restores
        tier.restore("beliefs_history")
        assert tier._total_restores == initial + 1

    def test_restore_all(self, tier: LocalColdTier, mock_storage: MagicMock):
        """restore_all returns list of results."""
        mock_storage.restore_all.return_value = [
            MagicMock(
                success=True,
                data=b"data1",
                archive_id="arch-1",
                size_bytes=5,
                duration_ms=1.0,
                error=None,
            ),
            MagicMock(
                success=True,
                data=b"data2",
                archive_id="arch-2",
                size_bytes=5,
                duration_ms=2.0,
                error=None,
            ),
        ]

        results = tier.restore_all("beliefs_history", limit=10)

        assert len(results) == 2
        assert results[0].archive_id == "arch-1"
        assert results[1].archive_id == "arch-2"


class TestRestoreResult:
    """Tests for RestoreResult dataclass."""

    def test_create_success(self):
        """RestoreResult success can be created."""
        result = RestoreResult(
            success=True,
            data=b"test_data",
            archive_id="arch-123",
            size_bytes=9,
            duration_ms=5.0,
            sla_met=True,
        )
        assert result.success is True
        assert result.data == b"test_data"
        assert result.sla_met is True

    def test_failure_factory(self):
        """RestoreResult.failure creates failure result."""
        result = RestoreResult.failure("test error", duration_ms=10.5)
        assert result.success is False
        assert result.error == "test error"

    def test_not_found_factory(self):
        """RestoreResult.not_found creates not-found result."""
        result = RestoreResult.not_found("beliefs_history", "session-123", duration_ms=5.0)
        assert result.success is False
        assert "No archive found" in result.error
        assert "beliefs_history" in result.error

    def test_to_dict(self):
        """RestoreResult.to_dict returns dict."""
        result = RestoreResult(
            success=True,
            data=b"test",
            archive_id="arch-123",
            size_bytes=4,
            duration_ms=5.123,
            sla_met=True,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["archive_id"] == "arch-123"
        assert d["sla_met"] is True


# =============================================================================
# CHECKPOINT OPERATIONS TESTS
# =============================================================================


class TestCheckpointOperations:
    """Tests for checkpoint operations."""

    def test_checkpoint_success(
        self, tier: LocalColdTier, mock_storage: MagicMock, sample_data: bytes
    ):
        """checkpoint returns success result."""
        mock_storage.archive.return_value = MagicMock(
            success=True,
            archive_id="chkpt-123",
            size_bytes=len(sample_data),
            error=None,
        )

        result = tier.checkpoint(sample_data, {"trigger": "periodic"})

        assert result.success is True
        assert result.archive_id == "chkpt-123"

    def test_checkpoint_calls_archive_with_checkpoint_section(
        self, tier: LocalColdTier, mock_storage: MagicMock, sample_data: bytes
    ):
        """checkpoint uses 'checkpoint' section."""
        mock_storage.archive.return_value = MagicMock(
            success=True, archive_id="chkpt-123", size_bytes=100, error=None
        )

        tier.checkpoint(sample_data)

        call_args = mock_storage.archive.call_args
        assert call_args.kwargs["section"] == "checkpoint"

    def test_restore_checkpoint_latest(
        self, tier: LocalColdTier, mock_storage: MagicMock, sample_data: bytes
    ):
        """restore_checkpoint restores latest checkpoint."""
        mock_storage.restore.return_value = MagicMock(
            success=True,
            data=sample_data,
            archive_id="chkpt-123",
            size_bytes=len(sample_data),
            duration_ms=5.0,
            error=None,
        )

        result = tier.restore_checkpoint()

        assert result.success is True
        mock_storage.restore.assert_called_once()
        call_args = mock_storage.restore.call_args
        assert call_args.kwargs["section"] == "checkpoint"

    def test_restore_checkpoint_specific(self, tier: LocalColdTier, mock_storage: MagicMock):
        """restore_checkpoint with specific ID."""
        mock_storage.restore.return_value = MagicMock(
            success=True,
            data=b"test",
            archive_id="chkpt-456",
            size_bytes=4,
            duration_ms=1.0,
            error=None,
        )

        tier.restore_checkpoint(checkpoint_id="chkpt-456")

        call_args = mock_storage.restore.call_args
        assert call_args.kwargs["filters"] == {"archive_id": "chkpt-456"}

    def test_list_checkpoints(self, tier: LocalColdTier, mock_storage: MagicMock):
        """list_checkpoints returns checkpoint list."""
        from k1.sessionstate.local_cold import ArchiveEntry

        mock_storage.list_archives.return_value = [
            ArchiveEntry(
                archive_id="chkpt-1",
                session_id="test-session-123",
                section="checkpoint",
                size_bytes=1000,
                created_at_ms=1000000,
                metadata={},
            )
        ]

        result = tier.list_checkpoints()

        assert len(result) == 1
        assert result[0].archive_id == "chkpt-1"
        mock_storage.list_archives.assert_called_with(
            session_id="test-session-123", section="checkpoint"
        )

    def test_prune_checkpoints(self, tier: LocalColdTier, mock_storage: MagicMock):
        """prune_checkpoints delegates to storage."""
        mock_storage.prune_checkpoints.return_value = 3

        deleted = tier.prune_checkpoints(keep_count=5)

        assert deleted == 3
        mock_storage.prune_checkpoints.assert_called_once_with(
            session_id="test-session-123", keep_count=5
        )


# =============================================================================
# LIST OPERATIONS TESTS
# =============================================================================


class TestListOperations:
    """Tests for list operations."""

    def test_list_archives_all(self, tier: LocalColdTier, mock_storage: MagicMock):
        """list_archives returns all archives."""
        from k1.sessionstate.local_cold import ArchiveEntry

        mock_storage.list_archives.return_value = [
            ArchiveEntry("arch-1", "test-session-123", "beliefs_history", 100, 1000, {}),
            ArchiveEntry("arch-2", "test-session-123", "history_recent", 200, 2000, {}),
        ]

        result = tier.list_archives()

        assert len(result) == 2
        mock_storage.list_archives.assert_called_with(session_id="test-session-123", section=None)

    def test_list_archives_by_section(self, tier: LocalColdTier, mock_storage: MagicMock):
        """list_archives filters by section."""
        from k1.sessionstate.local_cold import ArchiveEntry

        mock_storage.list_archives.return_value = [
            ArchiveEntry("arch-1", "test-session-123", "beliefs_history", 100, 1000, {}),
        ]

        tier.list_archives(section="beliefs_history")

        mock_storage.list_archives.assert_called_with(
            session_id="test-session-123", section="beliefs_history"
        )

    def test_list_archives_without_storage(self, tier_no_storage: LocalColdTier):
        """list_archives returns empty without storage."""
        result = tier_no_storage.list_archives()
        assert result == []

    def test_has_archives_true(self, tier: LocalColdTier, mock_storage: MagicMock):
        """has_archives returns True when archives exist."""
        mock_storage.has_session.return_value = True
        assert tier.has_archives() is True

    def test_has_archives_false(self, tier: LocalColdTier, mock_storage: MagicMock):
        """has_archives returns False when no archives."""
        mock_storage.has_session.return_value = False
        assert tier.has_archives() is False


class TestArchiveInfo:
    """Tests for ArchiveInfo dataclass."""

    def test_create_archive_info(self):
        """ArchiveInfo can be created."""
        info = ArchiveInfo(
            archive_id="arch-123",
            section="beliefs_history",
            session_id="session-456",
            size_bytes=1000,
            created_at_ms=1000000,
            metadata={"reason": "eviction"},
        )
        assert info.archive_id == "arch-123"
        assert info.section == "beliefs_history"
        assert info.metadata["reason"] == "eviction"

    def test_to_dict(self):
        """ArchiveInfo.to_dict returns dict."""
        info = ArchiveInfo(
            archive_id="arch-123",
            section="beliefs_history",
            session_id="session-456",
            size_bytes=1000,
            created_at_ms=1000000,
        )
        d = info.to_dict()
        assert d["archive_id"] == "arch-123"
        assert d["section"] == "beliefs_history"


# =============================================================================
# DELETE OPERATIONS TESTS
# =============================================================================


class TestDeleteOperations:
    """Tests for delete operations."""

    def test_delete_archive(self, tier: LocalColdTier, mock_storage: MagicMock):
        """delete_archive delegates to storage."""
        mock_storage.delete.return_value = True

        result = tier.delete_archive("arch-123")

        assert result is True
        mock_storage.delete.assert_called_once_with("arch-123")

    def test_delete_archive_without_storage(self, tier_no_storage: LocalColdTier):
        """delete_archive returns False without storage."""
        result = tier_no_storage.delete_archive("arch-123")
        assert result is False

    def test_delete_all_archives(self, tier: LocalColdTier, mock_storage: MagicMock):
        """delete_all_archives delegates to storage."""
        mock_storage.delete_session.return_value = 5

        result = tier.delete_all_archives()

        assert result == 5
        mock_storage.delete_session.assert_called_once_with("test-session-123")

    def test_delete_all_archives_without_session(self, mock_storage: MagicMock):
        """delete_all_archives returns 0 without session_id."""
        tier = LocalColdTier(storage=mock_storage, session_id="")
        result = tier.delete_all_archives()
        assert result == 0


# =============================================================================
# SIZE & STATS OPERATIONS TESTS
# =============================================================================


class TestSizeStatsOperations:
    """Tests for size and stats operations."""

    def test_get_storage_size(self, tier: LocalColdTier, mock_storage: MagicMock):
        """get_storage_size returns size for session."""
        mock_storage.get_total_size.return_value = 10000

        size = tier.get_storage_size()

        assert size == 10000
        mock_storage.get_total_size.assert_called_once_with("test-session-123")

    def test_get_storage_size_without_storage(self, tier_no_storage: LocalColdTier):
        """get_storage_size returns 0 without storage."""
        assert tier_no_storage.get_storage_size() == 0

    def test_get_archive_count(self, tier: LocalColdTier, mock_storage: MagicMock):
        """get_archive_count returns count for session."""
        mock_storage.get_archive_count.return_value = 25

        count = tier.get_archive_count()

        assert count == 25

    def test_get_stats(self, tier: LocalColdTier, mock_storage: MagicMock):
        """get_stats returns statistics."""
        mock_storage.get_stats.return_value = {
            "total_size_bytes": 10000,
            "archive_count": 25,
            "tables": {"st_beliefs_archive": {"count": 10, "size_bytes": 5000}},
        }

        stats = tier.get_stats()

        assert stats["total_size_bytes"] == 10000
        assert stats["archive_count"] == 25


# =============================================================================
# SNAPSHOT & METRICS TESTS
# =============================================================================


class TestSnapshotMetrics:
    """Tests for snapshot and metrics."""

    def test_get_snapshot(self, tier: LocalColdTier, mock_storage: MagicMock):
        """get_snapshot returns LocalColdSnapshot."""
        mock_storage.get_stats.return_value = {
            "total_size_bytes": 10000,
            "archive_count": 25,
            "tables": {
                "st_session_checkpoints": {"count": 3, "size_bytes": 3000},
                "st_beliefs_archive": {"count": 10, "size_bytes": 5000},
            },
        }
        from k1.sessionstate.local_cold import ArchiveEntry

        mock_storage.list_archives.return_value = [
            ArchiveEntry("chk-1", "test-session-123", "checkpoint", 1000, 1000, {}),
            ArchiveEntry("chk-2", "test-session-123", "checkpoint", 1000, 2000, {}),
        ]

        snapshot = tier.get_snapshot()

        assert isinstance(snapshot, LocalColdSnapshot)
        assert snapshot.session_id == "test-session-123"
        assert snapshot.total_size_bytes == 10000
        assert snapshot.archive_count == 25
        assert snapshot.is_available is True
        assert snapshot.timestamp_ms > 0

    def test_snapshot_to_dict(self):
        """LocalColdSnapshot.to_dict returns dict."""
        snapshot = LocalColdSnapshot(
            session_id="test-123",
            total_size_bytes=10000,
            archive_count=25,
            checkpoint_count=3,
            section_counts={"beliefs": 10, "history": 12},
            is_available=True,
            timestamp_ms=1000000,
        )
        d = snapshot.to_dict()
        assert d["session_id"] == "test-123"
        assert d["total_size_bytes"] == 10000
        assert d["checkpoint_count"] == 3

    def test_get_metrics(self, tier: LocalColdTier):
        """get_metrics returns operational metrics."""
        metrics = tier.get_metrics()

        assert metrics["tier"] == "local_cold"
        assert metrics["session_id"] == "test-session-123"
        assert metrics["is_available"] is True
        assert metrics["total_restores"] == 0
        assert metrics["total_archives"] == 0
        assert metrics["sla_compliance_rate"] == 1.0
        assert metrics["restore_sla_ms"] == 50.0

    def test_reset_metrics(self, tier: LocalColdTier, mock_storage: MagicMock):
        """reset_metrics clears counters."""
        # Simulate some activity
        mock_storage.archive.return_value = MagicMock(
            success=True, archive_id="arch-1", size_bytes=100, error=None
        )
        tier.archive("test", b"data")

        tier.reset_metrics()

        assert tier._total_restores == 0
        assert tier._total_archives == 0
        assert tier._bytes_archived == 0
        assert tier._restore_sla_violations == 0


# =============================================================================
# STORAGE MANAGEMENT TESTS
# =============================================================================


class TestStorageManagement:
    """Tests for storage management."""

    def test_set_storage(self, tier_no_storage: LocalColdTier, mock_storage: MagicMock):
        """set_storage attaches storage."""
        assert tier_no_storage.is_available is False

        tier_no_storage.set_storage(mock_storage)

        assert tier_no_storage.is_available is True

    def test_vacuum(self, tier: LocalColdTier, mock_storage: MagicMock):
        """vacuum calls storage vacuum."""
        tier.vacuum()
        mock_storage.vacuum.assert_called_once()

    def test_close(self, tier: LocalColdTier, mock_storage: MagicMock):
        """close calls storage close."""
        tier.close()
        mock_storage.close.assert_called_once()


# =============================================================================
# STRING REPRESENTATION TESTS
# =============================================================================


class TestStringRepresentation:
    """Tests for string representations."""

    def test_repr(self, tier: LocalColdTier):
        """__repr__ returns useful string."""
        repr_str = repr(tier)
        assert "LocalColdTier" in repr_str
        assert "test-ses" in repr_str  # First 8 chars
        assert "available=True" in repr_str

    def test_str(self, tier: LocalColdTier, mock_storage: MagicMock):
        """__str__ returns readable string."""
        mock_storage.get_total_size.return_value = 10240
        str_val = str(tier)
        assert "LocalColdTier" in str_val
        assert "10.0KB" in str_val


# =============================================================================
# FACTORY TESTS
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_local_cold_tier_with_storage(self, mock_storage: MagicMock):
        """create_local_cold_tier with existing storage."""
        tier = create_local_cold_tier(session_id="test-123", storage=mock_storage)

        assert isinstance(tier, LocalColdTier)
        assert tier.session_id == "test-123"
        assert tier.is_available is True

    def test_create_local_cold_tier_no_storage(self):
        """create_local_cold_tier without storage."""
        tier = create_local_cold_tier(session_id="test-123")

        assert isinstance(tier, LocalColdTier)
        assert tier.session_id == "test-123"
        assert tier.is_available is False

    def test_create_local_cold_tier_with_db_path(self, db_path: Path):
        """create_local_cold_tier creates storage from db_path."""
        tier = create_local_cold_tier(session_id="test-123", db_path=db_path)

        assert isinstance(tier, LocalColdTier)
        assert tier.is_available is True
        assert db_path.exists()

        tier.close()


# =============================================================================
# CONSTANTS TESTS
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_restore_sla_ms(self):
        """RESTORE_SLA_MS is 50ms."""
        assert RESTORE_SLA_MS == 50.0

    def test_default_max_age_days(self):
        """DEFAULT_MAX_AGE_DAYS is 30."""
        assert DEFAULT_MAX_AGE_DAYS == 30

    def test_archivable_sections(self):
        """ARCHIVABLE_SECTIONS contains expected sections."""
        assert "beliefs_history" in ARCHIVABLE_SECTIONS
        assert "history_recent" in ARCHIVABLE_SECTIONS
        assert "persona" in ARCHIVABLE_SECTIONS
        assert "telemetry" in ARCHIVABLE_SECTIONS
        assert "checkpoint" in ARCHIVABLE_SECTIONS


# =============================================================================
# EDGE CASES TESTS
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_multiple_tiers_independent(self, mock_storage: MagicMock):
        """Multiple tier instances are independent."""
        tier1 = LocalColdTier(storage=mock_storage, session_id="session-1")
        tier2 = LocalColdTier(storage=mock_storage, session_id="session-2")

        assert tier1.session_id == "session-1"
        assert tier2.session_id == "session-2"

    def test_empty_session_id(self, mock_storage: MagicMock):
        """Empty session_id is handled."""
        tier = LocalColdTier(storage=mock_storage, session_id="")
        assert tier.session_id == ""

    def test_prune_old_not_implemented(self, tier: LocalColdTier):
        """prune_old returns 0 (not fully implemented)."""
        result = tier.prune_old(max_age_days=7)
        assert result == 0

    def test_get_snapshot_timing(self, tier: LocalColdTier, mock_storage: MagicMock):
        """Snapshot timestamp is recent."""
        mock_storage.get_stats.return_value = {
            "total_size_bytes": 0,
            "archive_count": 0,
            "tables": {},
        }
        mock_storage.list_archives.return_value = []

        before = int(time.time() * 1000)
        snapshot = tier.get_snapshot()
        after = int(time.time() * 1000)

        assert before <= snapshot.timestamp_ms <= after


# =============================================================================
# INTEGRATION WITH REAL STORAGE TESTS
# =============================================================================


class TestRealStorageIntegration:
    """Integration tests with real LocalColdArchive."""

    def test_full_archive_restore_cycle(self, db_path: Path, sample_data: bytes):
        """Full archive/restore cycle with real storage."""
        tier = create_local_cold_tier(session_id="integration-test", db_path=db_path)

        try:
            # Archive data
            archive_result = tier.archive("beliefs_history", sample_data, {"reason": "test"})
            assert archive_result.success is True

            # Restore data
            restore_result = tier.restore("beliefs_history")
            assert restore_result.success is True
            assert restore_result.data == sample_data
            assert restore_result.sla_met is True

        finally:
            tier.close()

    def test_checkpoint_cycle(self, db_path: Path, sample_data: bytes):
        """Checkpoint and restore cycle."""
        tier = create_local_cold_tier(session_id="checkpoint-test", db_path=db_path)

        try:
            # Create checkpoint
            result = tier.checkpoint(sample_data, {"trigger": "test"})
            assert result.success is True

            # List checkpoints
            checkpoints = tier.list_checkpoints()
            assert len(checkpoints) == 1

            # Restore checkpoint
            restored = tier.restore_checkpoint()
            assert restored.success is True
            assert restored.data == sample_data

        finally:
            tier.close()

    def test_metrics_tracking(self, db_path: Path, sample_data: bytes):
        """Metrics are tracked correctly."""
        tier = create_local_cold_tier(session_id="metrics-test", db_path=db_path)

        try:
            # Archive
            tier.archive("beliefs_history", sample_data)

            # Restore
            tier.restore("beliefs_history")

            # Check metrics
            metrics = tier.get_metrics()
            assert metrics["total_archives"] == 1
            assert metrics["total_restores"] == 1
            assert metrics["bytes_archived"] > 0
            assert metrics["bytes_restored"] > 0

        finally:
            tier.close()
