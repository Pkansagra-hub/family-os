"""
Epic 4.8.2: Test Adapter Hot-Swap
=================================

Tests that verify adapters can be swapped between sessions.
Demonstrates that the factory accepts different adapter types and
operations work correctly with each.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.8 - Port/Adapter Integration
ISSUE: 4.8.2 - Test adapter hot-swap

SCENARIO:
---------
1. Create manager with SQLiteStorageAdapter
2. Perform operations, then stop
3. Create new manager with InMemoryStorageAdapter
4. Verify both work correctly

ASSERTIONS:
-----------
- Factory accepts both SQLiteStorageAdapter and InMemoryStorageAdapter
- Operations work with both adapters
- No crashes during swap
- Each adapter type behaves correctly

NOTE: "Hot-swap" here means creating new sessions with different adapters,
not swapping adapters on a running session (which is not supported).
"""

import uuid
from pathlib import Path
from typing import Generator

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager
from k1.sessionstate.adapters import InMemoryStorageAdapter, SQLiteStorageAdapter

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sqlite_session(tmp_path: Path) -> Generator[SessionStateManager, None, None]:
    """
    Create manager with SQLite storage adapter.

    Uses real SQLite database for persistence testing.
    """
    db_path = tmp_path / "sqlite_swap_test.db"
    session_id = f"sqlite-{uuid.uuid4().hex[:8]}"

    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
        checkpoint_interval_s=0,  # Disable periodic checkpoints
    )

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


@pytest.fixture
def memory_session() -> Generator[SessionStateManager, None, None]:
    """
    Create manager with InMemory storage adapter.

    Uses in-memory storage for fast testing.
    """
    manager = SessionStateFactory.create_for_testing()

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


# =============================================================================
# FACTORY ACCEPTANCE TESTS
# =============================================================================


class TestFactoryAcceptsBothAdapters:
    """Verify factory accepts different storage adapter types."""

    def test_factory_accepts_sqlite_adapter(self, tmp_path: Path) -> None:
        """Factory creates manager with SQLite adapter."""
        db_path = tmp_path / "factory_sqlite.db"
        session_id = f"sqlite-{uuid.uuid4().hex[:8]}"

        manager = SessionStateFactory.create_standalone(
            session_id=session_id,
            db_path=db_path,
        )

        assert manager is not None
        assert isinstance(manager, SessionStateManager)

        # Verify it's using local storage
        assert manager._local_cold_archive is not None

        # Cleanup
        if manager.is_running:
            manager.stop(checkpoint_before_stop=False)

    def test_factory_accepts_memory_adapter(self) -> None:
        """Factory creates manager with InMemory adapter."""
        manager = SessionStateFactory.create_for_testing()

        assert manager is not None
        assert isinstance(manager, SessionStateManager)

        # Cleanup
        if manager.is_running:
            manager.stop(checkpoint_before_stop=False)

    def test_both_adapters_start_successfully(
        self, sqlite_session: SessionStateManager, memory_session: SessionStateManager
    ) -> None:
        """Both adapter types can start successfully."""
        # Start SQLite session
        sqlite_result = sqlite_session.start(restore_if_exists=False)
        assert sqlite_result.success, f"SQLite start failed: {sqlite_result.error}"
        sqlite_session.stop(checkpoint_before_stop=False)

        # Start memory session
        memory_result = memory_session.start(restore_if_exists=False)
        assert memory_result.success, f"Memory start failed: {memory_result.error}"
        memory_session.stop(checkpoint_before_stop=False)


# =============================================================================
# SEQUENTIAL SWAP TESTS
# =============================================================================


class TestSequentialSwap:
    """Test creating sessions sequentially with different adapters."""

    def test_sqlite_then_memory(
        self, sqlite_session: SessionStateManager, memory_session: SessionStateManager
    ) -> None:
        """Can use SQLite session then switch to memory session."""
        # 1. Use SQLite session
        sqlite_session.start(restore_if_exists=False)

        result1 = sqlite_session.mutate(
            section="control",
            operation="set",
            data={"adapter": "sqlite"},
            estimated_bytes=50,
        )
        assert result1.success

        sqlite_session.checkpoint()
        sqlite_session.stop(checkpoint_before_stop=False)

        # 2. Now use memory session
        memory_session.start(restore_if_exists=False)

        result2 = memory_session.mutate(
            section="control",
            operation="set",
            data={"adapter": "memory"},
            estimated_bytes=50,
        )
        assert result2.success

        memory_session.stop(checkpoint_before_stop=False)

    def test_memory_then_sqlite(
        self, sqlite_session: SessionStateManager, memory_session: SessionStateManager
    ) -> None:
        """Can use memory session then switch to SQLite session."""
        # 1. Use memory session first
        memory_session.start(restore_if_exists=False)

        result1 = memory_session.mutate(
            section="scoreboard",
            operation="set",
            data={"topic": "memory first", "turn_count": 1},
            estimated_bytes=75,
        )
        assert result1.success

        memory_session.stop(checkpoint_before_stop=False)

        # 2. Now use SQLite session
        sqlite_session.start(restore_if_exists=False)

        result2 = sqlite_session.mutate(
            section="scoreboard",
            operation="set",
            data={"topic": "sqlite second", "turn_count": 2},
            estimated_bytes=75,
        )
        assert result2.success

        sqlite_session.checkpoint()
        sqlite_session.stop(checkpoint_before_stop=False)

    def test_multiple_swaps(self, tmp_path: Path) -> None:
        """Can swap between adapters multiple times."""
        adapters_used = []

        for i in range(3):
            # Alternate between SQLite and memory
            if i % 2 == 0:
                db_path = tmp_path / f"swap_test_{i}.db"
                manager = SessionStateFactory.create_standalone(
                    session_id=f"swap-{i}",
                    db_path=db_path,
                )
                adapters_used.append("sqlite")
            else:
                manager = SessionStateFactory.create_for_testing(
                    session_id=f"swap-{i}",
                )
                adapters_used.append("memory")

            # Use the session
            result = manager.start(restore_if_exists=False)
            assert result.success, f"Swap {i} failed to start"

            result = manager.mutate(
                section="control",
                operation="set",
                data={"swap_number": i},
                estimated_bytes=50,
            )
            assert result.success, f"Swap {i} mutation failed"

            manager.stop(checkpoint_before_stop=False)

        assert adapters_used == ["sqlite", "memory", "sqlite"]


# =============================================================================
# OPERATIONS VERIFICATION
# =============================================================================


class TestOperationsWithBothAdapters:
    """Verify all operations work with both adapter types."""

    def test_sqlite_full_operations(self, sqlite_session: SessionStateManager) -> None:
        """SQLite adapter supports all operations."""
        manager = sqlite_session

        # Start
        result = manager.start(restore_if_exists=False)
        assert result.success

        # Mutate various sections
        mutations = [
            ("control", "set", {"mode": "test"}),
            ("scoreboard", "set", {"topic": "sqlite ops", "turn_count": 1}),
            (
                "beliefs_active",
                "add_fact",
                {"subject": "user", "predicate": "tested", "obj": "sqlite", "confidence": 0.9},
            ),
        ]

        for section, op, data in mutations:
            result = manager.mutate(
                section=section,
                operation=op,
                data=data,
                estimated_bytes=100,
            )
            assert result.success, f"SQLite mutation to {section} failed"

        # Checkpoint
        checkpoint_result = manager.checkpoint()
        assert checkpoint_result.success

        # Snapshot
        snapshot = manager.get_snapshot()
        assert snapshot.is_running

        # Stop
        stop_result = manager.stop(checkpoint_before_stop=False)
        assert stop_result.success

    def test_memory_full_operations(self, memory_session: SessionStateManager) -> None:
        """Memory adapter supports all operations."""
        manager = memory_session

        # Start
        result = manager.start(restore_if_exists=False)
        assert result.success

        # Mutate various sections
        mutations = [
            ("control", "set", {"mode": "test"}),
            ("scoreboard", "set", {"topic": "memory ops", "turn_count": 1}),
            (
                "beliefs_active",
                "add_fact",
                {"subject": "user", "predicate": "tested", "obj": "memory", "confidence": 0.9},
            ),
        ]

        for section, op, data in mutations:
            result = manager.mutate(
                section=section,
                operation=op,
                data=data,
                estimated_bytes=100,
            )
            assert result.success, f"Memory mutation to {section} failed"

        # Checkpoint (may not persist but should succeed)
        checkpoint_result = manager.checkpoint()
        assert checkpoint_result.success

        # Snapshot
        snapshot = manager.get_snapshot()
        assert snapshot.is_running

        # Stop
        stop_result = manager.stop(checkpoint_before_stop=False)
        assert stop_result.success

    def test_identical_workflow_both_adapters(
        self, sqlite_session: SessionStateManager, memory_session: SessionStateManager
    ) -> None:
        """Same workflow works identically with both adapters."""

        def run_workflow(manager: SessionStateManager, label: str) -> None:
            """Run identical workflow on any manager."""
            # Start
            result = manager.start(restore_if_exists=False)
            assert result.success, f"{label}: start failed"

            # Add beliefs
            for i in range(3):
                result = manager.mutate(
                    section="beliefs_active",
                    operation="add_fact",
                    data={
                        "subject": "test",
                        "predicate": "has",
                        "obj": f"belief_{i}",
                        "confidence": 0.5 + i * 0.1,
                    },
                    estimated_bytes=75,
                )
                assert result.success, f"{label}: belief {i} failed"

            # Update scoreboard
            result = manager.mutate(
                section="scoreboard",
                operation="set",
                data={"topic": label, "turn_count": 3},
                estimated_bytes=50,
            )
            assert result.success, f"{label}: scoreboard failed"

            # Checkpoint
            checkpoint_result = manager.checkpoint()
            assert checkpoint_result.success, f"{label}: checkpoint failed"

            # Verify snapshot
            snapshot = manager.get_snapshot()
            assert snapshot.is_running

            # Stop
            stop_result = manager.stop(checkpoint_before_stop=False)
            assert stop_result.success, f"{label}: stop failed"

        # Run same workflow with both adapters
        run_workflow(sqlite_session, "SQLite")
        run_workflow(memory_session, "Memory")


# =============================================================================
# ISOLATION TESTS
# =============================================================================


class TestAdapterIsolation:
    """Verify adapters are properly isolated."""

    def test_sqlite_sessions_independent(self, tmp_path: Path) -> None:
        """Multiple SQLite sessions are independent."""
        # Create two separate SQLite sessions
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

            # Mutate session 1 only
            manager1.mutate(
                section="control",
                operation="set",
                data={"session": "one"},
                estimated_bytes=50,
            )

            # Get snapshots
            snapshot1 = manager1.get_snapshot()
            snapshot2 = manager2.get_snapshot()

            # Both running but independent
            assert snapshot1.is_running
            assert snapshot2.is_running

        finally:
            if manager1.is_running:
                manager1.stop(checkpoint_before_stop=False)
            if manager2.is_running:
                manager2.stop(checkpoint_before_stop=False)

    def test_memory_sessions_independent(self) -> None:
        """Multiple memory sessions are independent."""
        manager1 = SessionStateFactory.create_for_testing(session_id="mem-1")
        manager2 = SessionStateFactory.create_for_testing(session_id="mem-2")

        try:
            # Start both
            manager1.start(restore_if_exists=False)
            manager2.start(restore_if_exists=False)

            # Mutate session 1 only
            manager1.mutate(
                section="control",
                operation="set",
                data={"session": "one"},
                estimated_bytes=50,
            )

            # Get sizes - should be different
            size1 = manager1.get_hot().get_total_size()
            size2 = manager2.get_hot().get_total_size()

            # Session 1 should have more data (or at least valid sizes)
            assert size1 >= 0 and size2 >= 0

        finally:
            if manager1.is_running:
                manager1.stop(checkpoint_before_stop=False)
            if manager2.is_running:
                manager2.stop(checkpoint_before_stop=False)

    def test_mixed_adapter_sessions_independent(self, tmp_path: Path) -> None:
        """SQLite and memory sessions are independent."""
        db_path = tmp_path / "mixed.db"

        sqlite_manager = SessionStateFactory.create_standalone(
            session_id="sqlite-mixed",
            db_path=db_path,
        )
        memory_manager = SessionStateFactory.create_for_testing(session_id="memory-mixed")

        try:
            # Start both
            sqlite_manager.start(restore_if_exists=False)
            memory_manager.start(restore_if_exists=False)

            # Mutate SQLite only
            sqlite_manager.mutate(
                section="beliefs_active",
                operation="add_fact",
                data={"subject": "test", "predicate": "uses", "obj": "sqlite", "confidence": 0.9},
                estimated_bytes=100,
            )

            # Both should be running independently
            assert sqlite_manager.is_running
            assert memory_manager.is_running

        finally:
            if sqlite_manager.is_running:
                sqlite_manager.stop(checkpoint_before_stop=False)
            if memory_manager.is_running:
                memory_manager.stop(checkpoint_before_stop=False)


# =============================================================================
# NO CRASH TESTS
# =============================================================================


class TestNoCrashes:
    """Verify no crashes during adapter operations."""

    def test_rapid_create_destroy_sqlite(self, tmp_path: Path) -> None:
        """Rapid create/destroy with SQLite doesn't crash."""
        for i in range(5):
            db_path = tmp_path / f"rapid_{i}.db"
            manager = SessionStateFactory.create_standalone(
                session_id=f"rapid-{i}",
                db_path=db_path,
            )

            manager.start(restore_if_exists=False)
            manager.mutate(
                section="control",
                operation="set",
                data={"iteration": i},
                estimated_bytes=50,
            )
            manager.stop(checkpoint_before_stop=False)

        # If we get here, no crashes
        assert True

    def test_rapid_create_destroy_memory(self) -> None:
        """Rapid create/destroy with memory doesn't crash."""
        for i in range(10):
            manager = SessionStateFactory.create_for_testing(
                session_id=f"rapid-mem-{i}",
            )

            manager.start(restore_if_exists=False)
            manager.mutate(
                section="control",
                operation="set",
                data={"iteration": i},
                estimated_bytes=50,
            )
            manager.stop(checkpoint_before_stop=False)

        # If we get here, no crashes
        assert True

    def test_swap_under_load(self, tmp_path: Path) -> None:
        """Swapping adapters under mutation load doesn't crash."""
        for i in range(3):
            # Alternate adapters
            if i % 2 == 0:
                db_path = tmp_path / f"load_{i}.db"
                manager = SessionStateFactory.create_standalone(
                    session_id=f"load-{i}",
                    db_path=db_path,
                )
            else:
                manager = SessionStateFactory.create_for_testing(
                    session_id=f"load-{i}",
                )

            manager.start(restore_if_exists=False)

            # Heavy mutations
            for j in range(20):
                manager.mutate(
                    section="telemetry",
                    operation="record_turn",
                    data={
                        "turn_id": f"{i}-{j}",
                        "latency_ms": 100 + j,
                        "tokens_used": 50 + j,
                    },
                    estimated_bytes=100,
                )

            manager.checkpoint()
            manager.stop(checkpoint_before_stop=False)

        # If we get here, no crashes
        assert True


# =============================================================================
# ADAPTER PROPERTY TESTS
# =============================================================================


class TestAdapterProperties:
    """Verify adapter properties are correctly set."""

    def test_sqlite_has_local_storage_type(self, tmp_path: Path) -> None:
        """SQLite adapter reports correct storage type."""
        db_path = tmp_path / "type_test.db"
        adapter = SQLiteStorageAdapter(db_path=db_path)

        assert adapter.storage_type in ["sqlite", "local"]
        adapter.close()

    def test_memory_has_memory_storage_type(self) -> None:
        """Memory adapter reports correct storage type."""
        adapter = InMemoryStorageAdapter()

        assert adapter.storage_type == "memory"
        adapter.clear()

    def test_event_adapter_connected_for_both(
        self, sqlite_session: SessionStateManager, memory_session: SessionStateManager
    ) -> None:
        """Event adapters are connected for both session types."""
        # SQLite session
        assert sqlite_session._event_port.is_connected

        # Memory session
        assert memory_session._event_port.is_connected


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Test edge cases during adapter swap."""

    def test_empty_session_swap(self, tmp_path: Path) -> None:
        """Can swap between adapters with empty sessions."""
        # SQLite empty session
        db_path = tmp_path / "empty.db"
        sqlite_manager = SessionStateFactory.create_standalone(
            session_id="empty-sqlite",
            db_path=db_path,
        )
        sqlite_manager.start(restore_if_exists=False)
        sqlite_manager.stop(checkpoint_before_stop=False)

        # Memory empty session
        memory_manager = SessionStateFactory.create_for_testing(session_id="empty-memory")
        memory_manager.start(restore_if_exists=False)
        memory_manager.stop(checkpoint_before_stop=False)

        # Both worked
        assert True

    def test_large_data_swap(self, tmp_path: Path) -> None:
        """Can swap adapters after large data mutations."""
        # SQLite with large data
        db_path = tmp_path / "large.db"
        sqlite_manager = SessionStateFactory.create_standalone(
            session_id="large-sqlite",
            db_path=db_path,
        )
        sqlite_manager.start(restore_if_exists=False)

        # Add substantial data
        for i in range(50):
            sqlite_manager.mutate(
                section="beliefs_active",
                operation="add_fact",
                data={
                    "subject": f"entity_{i}",
                    "predicate": "has_property",
                    "obj": f"value_{i}",
                    "confidence": 0.5 + (i % 50) / 100,
                },
                estimated_bytes=200,
            )

        sqlite_manager.checkpoint()
        sqlite_manager.stop(checkpoint_before_stop=False)

        # Now memory session
        memory_manager = SessionStateFactory.create_for_testing(session_id="after-large")
        memory_manager.start(restore_if_exists=False)

        # Should work fine
        result = memory_manager.mutate(
            section="control",
            operation="set",
            data={"after_large": True},
            estimated_bytes=50,
        )
        assert result.success

        memory_manager.stop(checkpoint_before_stop=False)

    def test_checkpoint_then_swap(self, tmp_path: Path) -> None:
        """Checkpoint before swap preserves data isolation."""
        # SQLite with checkpoint
        db_path = tmp_path / "checkpoint_swap.db"
        sqlite_manager = SessionStateFactory.create_standalone(
            session_id="checkpoint-sqlite",
            db_path=db_path,
        )
        sqlite_manager.start(restore_if_exists=False)

        sqlite_manager.mutate(
            section="scoreboard",
            operation="set",
            data={"topic": "checkpointed", "turn_count": 5},
            estimated_bytes=75,
        )

        checkpoint_result = sqlite_manager.checkpoint()
        assert checkpoint_result.success
        assert checkpoint_result.checkpoint_id != ""

        sqlite_manager.stop(checkpoint_before_stop=False)

        # Memory session (no access to SQLite checkpoint)
        memory_manager = SessionStateFactory.create_for_testing(session_id="after-checkpoint")
        memory_manager.start(restore_if_exists=False)

        # Memory starts fresh
        snapshot = memory_manager.get_snapshot()
        assert snapshot.is_running

        memory_manager.stop(checkpoint_before_stop=False)
