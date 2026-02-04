"""
Epic 4.8.3: Test NullSyncPort Operation
========================================

Tests that verify NullSyncPort works correctly for standalone/offline mode.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.8 - Port/Adapter Integration
ISSUE: 4.8.3 - Test NullSyncPort operation

SCENARIO:
---------
1. Create manager with NullSyncPort (default for standalone)
2. Full session via manager APIs
3. Verify no K0 errors, LOCAL COLD only, sync status OFFLINE

ASSERTIONS:
-----------
- NullSyncPort is wired (or no sync port = standalone)
- Operations work without K0 connectivity
- Sync status is OFFLINE
- LOCAL COLD storage is used
- No K0-related errors during operations

NOTE: create_standalone() and create_for_testing() both use NullSyncPort
implicitly (no K0 sync configured).
"""

import uuid
from pathlib import Path
from typing import Generator

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager
from k1.sessionstate.ports.k0_sync import IK0SyncPort, NullSyncPort, SyncStatus

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def standalone_manager(tmp_path: Path) -> Generator[SessionStateManager, None, None]:
    """
    Create standalone manager (implicitly uses NullSyncPort).
    """
    db_path = tmp_path / "null_sync_test.db"
    session_id = f"nullsync-{uuid.uuid4().hex[:8]}"

    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
        checkpoint_interval_s=0,
    )

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


@pytest.fixture
def started_standalone(standalone_manager: SessionStateManager) -> SessionStateManager:
    """Standalone manager that is already started."""
    result = standalone_manager.start(restore_if_exists=False)
    assert result.success, f"Failed to start: {result.error}"
    return standalone_manager


@pytest.fixture
def null_sync_port() -> NullSyncPort:
    """Direct NullSyncPort instance for testing."""
    return NullSyncPort()


# =============================================================================
# NULLSYNCPORT UNIT TESTS
# =============================================================================


class TestNullSyncPortInterface:
    """Test NullSyncPort implements IK0SyncPort correctly."""

    def test_null_sync_implements_interface(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort implements IK0SyncPort."""
        assert isinstance(null_sync_port, IK0SyncPort)

    def test_null_sync_has_is_available(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort has is_available property."""
        assert hasattr(null_sync_port, "is_available")
        assert isinstance(null_sync_port.is_available, bool)

    def test_null_sync_has_sync_to_k0(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort has sync_to_k0 method."""
        assert hasattr(null_sync_port, "sync_to_k0")
        assert callable(null_sync_port.sync_to_k0)

    def test_null_sync_has_restore_from_k0(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort has restore_from_k0 method."""
        assert hasattr(null_sync_port, "restore_from_k0")
        assert callable(null_sync_port.restore_from_k0)

    def test_null_sync_has_get_sync_status(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort has get_sync_status method."""
        assert hasattr(null_sync_port, "get_sync_status")
        assert callable(null_sync_port.get_sync_status)

    def test_null_sync_has_cancel_sync(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort has cancel_sync method."""
        assert hasattr(null_sync_port, "cancel_sync")
        assert callable(null_sync_port.cancel_sync)


class TestNullSyncPortBehavior:
    """Test NullSyncPort returns correct values."""

    def test_is_available_returns_false(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort always returns is_available=False."""
        assert null_sync_port.is_available is False

    def test_sync_to_k0_returns_offline_status(self, null_sync_port: NullSyncPort) -> None:
        """sync_to_k0 returns OFFLINE status."""
        result = null_sync_port.sync_to_k0("test-session")

        assert result.success is False
        assert result.status == SyncStatus.OFFLINE
        assert result.session_id == "test-session"
        assert result.sections_synced == []
        assert result.bytes_synced == 0
        assert result.error is not None

    def test_restore_from_k0_returns_failure(self, null_sync_port: NullSyncPort) -> None:
        """restore_from_k0 returns failure (no K0 available)."""
        result = null_sync_port.restore_from_k0("test-session")

        assert result.success is False
        assert result.session_id == "test-session"
        assert result.sections_restored == []
        assert result.bytes_restored == 0
        assert result.error is not None

    def test_get_sync_status_returns_offline(self, null_sync_port: NullSyncPort) -> None:
        """get_sync_status always returns OFFLINE."""
        status = null_sync_port.get_sync_status("test-session")
        assert status == SyncStatus.OFFLINE

    def test_cancel_sync_returns_false(self, null_sync_port: NullSyncPort) -> None:
        """cancel_sync returns False (nothing to cancel)."""
        result = null_sync_port.cancel_sync("test-session")
        assert result is False


# =============================================================================
# STANDALONE MANAGER WITH NULLSYNCPORT
# =============================================================================


class TestStandaloneManagerNoK0:
    """Test standalone manager works without K0."""

    def test_standalone_starts_without_k0(self, standalone_manager: SessionStateManager) -> None:
        """Standalone manager starts without K0 errors."""
        result = standalone_manager.start(restore_if_exists=False)
        assert result.success, f"Start failed: {result.error}"
        assert standalone_manager.is_running

    def test_standalone_stops_without_k0(self, started_standalone: SessionStateManager) -> None:
        """Standalone manager stops without K0 errors."""
        result = started_standalone.stop(checkpoint_before_stop=False)
        assert result.success, f"Stop failed: {result.error}"
        assert not started_standalone.is_running

    def test_mutations_work_without_k0(self, started_standalone: SessionStateManager) -> None:
        """Mutations work without K0 connectivity."""
        result = started_standalone.mutate(
            section="control",
            operation="set",
            data={"mode": "offline"},
            estimated_bytes=50,
        )
        assert result.success, f"Mutation failed: {result.error}"

    def test_checkpoint_works_without_k0(self, started_standalone: SessionStateManager) -> None:
        """Checkpoint works without K0 (uses LOCAL COLD only)."""
        # Add some data
        started_standalone.mutate(
            section="scoreboard",
            operation="set",
            data={"topic": "offline test", "turn_count": 1},
            estimated_bytes=75,
        )

        # Checkpoint to LOCAL COLD
        result = started_standalone.checkpoint()
        assert result.success, f"Checkpoint failed: {result.error}"
        assert result.checkpoint_id != ""

    def test_restore_works_without_k0(self, tmp_path: Path) -> None:
        """Restore from LOCAL COLD works without K0."""
        db_path = tmp_path / "restore_test.db"
        session_id = f"restore-{uuid.uuid4().hex[:8]}"

        # Create first session, add data, checkpoint
        manager1 = SessionStateFactory.create_standalone(
            session_id=session_id,
            db_path=db_path,
        )
        manager1.start(restore_if_exists=False)
        manager1.mutate(
            section="control",
            operation="set",
            data={"restored": "test"},
            estimated_bytes=50,
        )
        manager1.checkpoint()
        manager1.stop(checkpoint_before_stop=False)

        # Create second session, restore from LOCAL COLD
        manager2 = SessionStateFactory.create_standalone(
            session_id=session_id,
            db_path=db_path,
        )
        result = manager2.start(restore_if_exists=True)

        assert result.success, f"Restore failed: {result.error}"
        assert result.restored is True

        manager2.stop(checkpoint_before_stop=False)


# =============================================================================
# LOCAL COLD ONLY TESTS
# =============================================================================


class TestLocalColdOnly:
    """Verify LOCAL COLD is used without K0."""

    def test_checkpoint_uses_local_cold(self, started_standalone: SessionStateManager) -> None:
        """Checkpoint writes to LOCAL COLD."""
        # Add data
        started_standalone.mutate(
            section="beliefs_active",
            operation="add_fact",
            data={
                "subject": "user",
                "predicate": "prefers",
                "obj": "offline",
                "confidence": 0.9,
            },
            estimated_bytes=100,
        )

        # Checkpoint
        result = started_standalone.checkpoint()
        assert result.success
        assert result.size_bytes > 0

        # Verify LOCAL COLD is accessible
        local_cold = started_standalone.get_local_cold()
        assert local_cold is not None

    def test_local_cold_archive_accessible(self, started_standalone: SessionStateManager) -> None:
        """LOCAL COLD archive is accessible."""
        archive = started_standalone._local_cold_archive
        assert archive is not None

    def test_no_k0_sync_port_on_standalone(self, standalone_manager: SessionStateManager) -> None:
        """Standalone manager has no K0 sync port or uses NullSyncPort."""
        # Manager may or may not have _k0_sync_port
        # If it exists, it should be NullSyncPort or None
        if hasattr(standalone_manager, "_k0_sync_port"):
            port = standalone_manager._k0_sync_port
            assert port is None or isinstance(port, NullSyncPort)


# =============================================================================
# SYNC STATUS OFFLINE TESTS
# =============================================================================


class TestSyncStatusOffline:
    """Verify sync status is OFFLINE in standalone mode."""

    def test_null_sync_always_offline(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort reports OFFLINE for any session."""
        sessions = ["session-1", "session-2", "test-123"]

        for session_id in sessions:
            status = null_sync_port.get_sync_status(session_id)
            assert status == SyncStatus.OFFLINE

    def test_sync_attempt_returns_offline(self, null_sync_port: NullSyncPort) -> None:
        """Sync attempt returns OFFLINE status, not error."""
        result = null_sync_port.sync_to_k0("test-session")

        # Should not raise, just return OFFLINE
        assert result.status == SyncStatus.OFFLINE
        # Error message is informational, not a crash
        assert "not configured" in result.error.lower()


# =============================================================================
# NO K0 ERRORS TESTS
# =============================================================================


class TestNoK0Errors:
    """Verify no K0-related errors during standalone operation."""

    def test_full_lifecycle_no_k0_errors(self, standalone_manager: SessionStateManager) -> None:
        """Full lifecycle completes without K0 errors."""
        # Start
        start_result = standalone_manager.start(restore_if_exists=False)
        assert start_result.success
        assert start_result.error is None or start_result.error == ""

        # Mutate
        for i in range(5):
            result = standalone_manager.mutate(
                section="control",
                operation="set",
                data={"iteration": i},
                estimated_bytes=50,
            )
            assert result.success, f"Iteration {i} failed: {result.error}"

        # Checkpoint
        checkpoint_result = standalone_manager.checkpoint()
        assert checkpoint_result.success
        assert checkpoint_result.error is None or checkpoint_result.error == ""

        # Stop
        stop_result = standalone_manager.stop(checkpoint_before_stop=False)
        assert stop_result.success
        assert stop_result.error is None or stop_result.error == ""

    def test_heavy_mutations_no_k0_errors(self, started_standalone: SessionStateManager) -> None:
        """Heavy mutations complete without K0 errors."""
        # Many mutations
        for i in range(50):
            result = started_standalone.mutate(
                section="scoreboard",
                operation="set",
                data={"turn_count": i, "topic": f"topic-{i}"},
                estimated_bytes=100,
            )
            # Should not fail due to K0 issues
            assert result.success or result.error is None or "K0" not in str(result.error)

    def test_snapshot_no_k0_errors(self, started_standalone: SessionStateManager) -> None:
        """Snapshot works without K0 errors."""
        snapshot = started_standalone.get_snapshot()

        assert snapshot is not None
        assert snapshot.is_running
        # No K0-related fields should cause issues
        assert hasattr(snapshot, "session_id")


# =============================================================================
# MULTIPLE SESSIONS WITHOUT K0
# =============================================================================


class TestMultipleSessionsNoK0:
    """Test multiple standalone sessions work independently."""

    def test_two_sessions_independent(self, tmp_path: Path) -> None:
        """Two standalone sessions work independently."""
        db_path1 = tmp_path / "session1.db"
        db_path2 = tmp_path / "session2.db"

        manager1 = SessionStateFactory.create_standalone(
            session_id="session-1",
            db_path=db_path1,
        )
        manager2 = SessionStateFactory.create_standalone(
            session_id="session-2",
            db_path=db_path2,
        )

        try:
            # Start both
            manager1.start(restore_if_exists=False)
            manager2.start(restore_if_exists=False)

            # Mutate independently
            manager1.mutate(
                section="control",
                operation="set",
                data={"session": "one"},
                estimated_bytes=50,
            )
            manager2.mutate(
                section="control",
                operation="set",
                data={"session": "two"},
                estimated_bytes=50,
            )

            # Both should work
            assert manager1.is_running
            assert manager2.is_running

        finally:
            if manager1.is_running:
                manager1.stop(checkpoint_before_stop=False)
            if manager2.is_running:
                manager2.stop(checkpoint_before_stop=False)

    def test_many_sessions_no_k0(self, tmp_path: Path) -> None:
        """Many standalone sessions work without K0."""
        managers = []

        try:
            for i in range(5):
                db_path = tmp_path / f"multi_session_{i}.db"
                manager = SessionStateFactory.create_standalone(
                    session_id=f"multi-{i}",
                    db_path=db_path,
                )
                manager.start(restore_if_exists=False)
                managers.append(manager)

            # All should be running
            for i, manager in enumerate(managers):
                assert manager.is_running, f"Manager {i} not running"

        finally:
            for manager in managers:
                if manager.is_running:
                    manager.stop(checkpoint_before_stop=False)


# =============================================================================
# EDGE CASES
# =============================================================================


class TestNullSyncEdgeCases:
    """Test edge cases with NullSyncPort."""

    def test_empty_session_id(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort handles empty session ID."""
        result = null_sync_port.sync_to_k0("")
        assert result.status == SyncStatus.OFFLINE
        assert result.session_id == ""

    def test_long_session_id(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort handles long session ID."""
        long_id = "x" * 1000
        result = null_sync_port.sync_to_k0(long_id)
        assert result.status == SyncStatus.OFFLINE
        assert result.session_id == long_id

    def test_special_characters_session_id(self, null_sync_port: NullSyncPort) -> None:
        """NullSyncPort handles special characters in session ID."""
        special_id = "session-!@#$%^&*()_+-=[]{}|;':\",./<>?"
        result = null_sync_port.sync_to_k0(special_id)
        assert result.status == SyncStatus.OFFLINE

    def test_rapid_sync_attempts(self, null_sync_port: NullSyncPort) -> None:
        """Rapid sync attempts don't cause issues."""
        for i in range(100):
            result = null_sync_port.sync_to_k0(f"session-{i}")
            assert result.status == SyncStatus.OFFLINE

    def test_rapid_cancel_attempts(self, null_sync_port: NullSyncPort) -> None:
        """Rapid cancel attempts don't cause issues."""
        for i in range(100):
            result = null_sync_port.cancel_sync(f"session-{i}")
            assert result is False
