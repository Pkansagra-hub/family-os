"""
SessionStateFactory Unit Tests
==============================

Tests for SessionStateFactory - creation factory for SessionStateManager.

IMPLEMENTATION: k1/sessionstate/factory.py
EPIC: 3.5 SessionStateFactory and Standalone Mode
ISSUE: 3.5.1 Create SessionStateFactory

TEST CATEGORIES:
---------------
1. create_standalone() - SQLite-backed offline operation
2. create_for_testing() - In-memory fast testing
3. create_with_ports() - Production wiring with validation
4. PortProtocolError - Validation exceptions
5. Convenience functions - Module-level helpers
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k1.sessionstate import (
    DirectWriterAdapter,
    InMemoryStorageAdapter,
    LocalEventAdapter,
    PortProtocolError,
    SessionStateFactory,
    SessionStateManager,
    SQLiteStorageAdapter,
    StandaloneLifecycle,
    create_for_testing,
    create_standalone,
)
from k1.sessionstate.ports import IEventPort, ILifecyclePort, IStoragePort, IWriterPort

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def storage_adapter():
    """In-memory storage adapter for testing."""
    return InMemoryStorageAdapter()


@pytest.fixture
def event_adapter():
    """Local event adapter with capture mode."""
    return LocalEventAdapter(capture_mode=True)


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Temporary database path for SQLite tests."""
    return tmp_path / "test_session.db"


# =============================================================================
# TEST: create_standalone()
# =============================================================================


class TestCreateStandalone:
    """Tests for SessionStateFactory.create_standalone()."""

    def test_returns_session_state_manager(self, test_db_path: Path):
        """create_standalone() returns SessionStateManager instance."""
        manager = SessionStateFactory.create_standalone(
            session_id="test-session",
            db_path=test_db_path,
        )

        assert isinstance(manager, SessionStateManager)
        assert manager.session_id == "test-session"

    def test_uses_sqlite_storage(self, test_db_path: Path):
        """Standalone mode uses SQLiteStorageAdapter."""
        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=test_db_path,
        )

        assert isinstance(manager._storage_port, SQLiteStorageAdapter)
        assert manager._storage_port.storage_type == "local"

    def test_uses_local_events(self, test_db_path: Path):
        """Standalone mode uses LocalEventAdapter."""
        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=test_db_path,
        )

        assert isinstance(manager._event_port, LocalEventAdapter)

    def test_uses_direct_writer(self, test_db_path: Path):
        """Standalone mode uses DirectWriterAdapter."""
        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=test_db_path,
        )

        assert isinstance(manager._writer_port, DirectWriterAdapter)
        assert manager._writer_port.writer_id == "direct"

    def test_uses_standalone_lifecycle(self, test_db_path: Path):
        """Standalone mode uses StandaloneLifecycle."""
        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=test_db_path,
        )

        assert isinstance(manager._lifecycle_port, StandaloneLifecycle)

    def test_manager_not_started_after_creation(self, test_db_path: Path):
        """Created manager is not yet started."""
        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=test_db_path,
        )

        assert not manager.is_running

    def test_auto_generates_session_id(self, test_db_path: Path):
        """Session ID is auto-generated if not provided."""
        manager = SessionStateFactory.create_standalone(db_path=test_db_path)

        assert manager.session_id is not None
        assert manager.session_id.startswith("session-")

    def test_creates_db_parent_directory(self, tmp_path: Path):
        """Creates parent directory if it doesn't exist."""
        db_path = tmp_path / "nested" / "dir" / "test.db"

        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=db_path,
        )

        assert db_path.parent.exists()

    def test_custom_checkpoint_interval(self, test_db_path: Path):
        """Custom checkpoint interval is passed to lifecycle."""
        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=test_db_path,
            checkpoint_interval_s=60.0,
        )

        lifecycle = manager._lifecycle_port
        assert isinstance(lifecycle, StandaloneLifecycle)
        # StandaloneLifecycle stores the interval in config as ms
        assert lifecycle._config.checkpoint_interval_ms == 60000


# =============================================================================
# TEST: create_for_testing()
# =============================================================================


class TestCreateForTesting:
    """Tests for SessionStateFactory.create_for_testing()."""

    def test_returns_session_state_manager(self):
        """create_for_testing() returns SessionStateManager instance."""
        manager = SessionStateFactory.create_for_testing()

        assert isinstance(manager, SessionStateManager)

    def test_uses_in_memory_storage(self):
        """Testing mode uses InMemoryStorageAdapter."""
        manager = SessionStateFactory.create_for_testing()

        assert isinstance(manager._storage_port, InMemoryStorageAdapter)
        assert manager._storage_port.storage_type == "memory"

    def test_uses_local_events_with_capture(self):
        """Testing mode uses LocalEventAdapter with capture mode."""
        manager = SessionStateFactory.create_for_testing()

        assert isinstance(manager._event_port, LocalEventAdapter)
        assert manager._event_port._capture_mode is True

    def test_auto_generates_test_session_id(self):
        """Auto-generates session ID with 'test-' prefix."""
        manager = SessionStateFactory.create_for_testing()

        assert manager.session_id.startswith("test-")

    def test_custom_session_id(self):
        """Custom session ID is respected."""
        manager = SessionStateFactory.create_for_testing(session_id="my-test")

        assert manager.session_id == "my-test"

    def test_managers_are_isolated(self):
        """Each testing manager has its own isolated state."""
        manager1 = SessionStateFactory.create_for_testing()
        manager2 = SessionStateFactory.create_for_testing()

        # They should have different storage instances
        assert manager1._storage_port is not manager2._storage_port

    def test_no_periodic_checkpoints(self):
        """Testing mode disables periodic checkpoints."""
        manager = SessionStateFactory.create_for_testing()

        lifecycle = manager._lifecycle_port
        assert isinstance(lifecycle, StandaloneLifecycle)
        # Testing config should have no periodic checkpoints (0 ms)
        assert lifecycle._config.checkpoint_interval_ms == 0

    def test_fast_creation(self):
        """Testing mode creates manager quickly (< 50ms)."""
        import time

        start = time.perf_counter()
        _manager = SessionStateFactory.create_for_testing()
        duration = time.perf_counter() - start

        assert duration < 0.05  # 50ms


# =============================================================================
# TEST: create_with_ports()
# =============================================================================


class TestCreateWithPorts:
    """Tests for SessionStateFactory.create_with_ports()."""

    def test_uses_provided_storage(self, storage_adapter, event_adapter):
        """Uses the provided storage port."""
        # Need to create writer/lifecycle that work with manager
        manager_mock = MagicMock(spec=SessionStateManager)
        guard_mock = MagicMock()
        manager_mock.mutation_guard = guard_mock

        writer = DirectWriterAdapter(manager_mock, guard_mock)
        lifecycle = StandaloneLifecycle(manager_mock)

        manager = SessionStateFactory.create_with_ports(
            session_id="test",
            storage=storage_adapter,
            events=event_adapter,
            writer=writer,
            lifecycle=lifecycle,
        )

        assert manager._storage_port is storage_adapter

    def test_uses_provided_events(self, storage_adapter, event_adapter):
        """Uses the provided event port."""
        manager_mock = MagicMock(spec=SessionStateManager)
        guard_mock = MagicMock()
        manager_mock.mutation_guard = guard_mock

        writer = DirectWriterAdapter(manager_mock, guard_mock)
        lifecycle = StandaloneLifecycle(manager_mock)

        manager = SessionStateFactory.create_with_ports(
            session_id="test",
            storage=storage_adapter,
            events=event_adapter,
            writer=writer,
            lifecycle=lifecycle,
        )

        assert manager._event_port is event_adapter

    def test_validates_storage_port(self, event_adapter):
        """Raises PortProtocolError for invalid storage port."""
        manager_mock = MagicMock(spec=SessionStateManager)
        guard_mock = MagicMock()
        manager_mock.mutation_guard = guard_mock

        writer = DirectWriterAdapter(manager_mock, guard_mock)
        lifecycle = StandaloneLifecycle(manager_mock)

        with pytest.raises(PortProtocolError) as exc_info:
            SessionStateFactory.create_with_ports(
                session_id="test",
                storage="not_a_storage_port",  # Invalid
                events=event_adapter,
                writer=writer,
                lifecycle=lifecycle,
            )

        assert exc_info.value.port_name == "storage"
        assert exc_info.value.expected is IStoragePort

    def test_validates_event_port(self, storage_adapter):
        """Raises PortProtocolError for invalid event port."""
        manager_mock = MagicMock(spec=SessionStateManager)
        guard_mock = MagicMock()
        manager_mock.mutation_guard = guard_mock

        writer = DirectWriterAdapter(manager_mock, guard_mock)
        lifecycle = StandaloneLifecycle(manager_mock)

        with pytest.raises(PortProtocolError) as exc_info:
            SessionStateFactory.create_with_ports(
                session_id="test",
                storage=storage_adapter,
                events="not_an_event_port",  # Invalid
                writer=writer,
                lifecycle=lifecycle,
            )

        assert exc_info.value.port_name == "events"
        assert exc_info.value.expected is IEventPort

    def test_validates_writer_port(self, storage_adapter, event_adapter):
        """Raises PortProtocolError for invalid writer port."""
        manager_mock = MagicMock(spec=SessionStateManager)
        lifecycle = StandaloneLifecycle(manager_mock)

        with pytest.raises(PortProtocolError) as exc_info:
            SessionStateFactory.create_with_ports(
                session_id="test",
                storage=storage_adapter,
                events=event_adapter,
                writer="not_a_writer_port",  # Invalid
                lifecycle=lifecycle,
            )

        assert exc_info.value.port_name == "writer"
        assert exc_info.value.expected is IWriterPort

    def test_validates_lifecycle_port(self, storage_adapter, event_adapter):
        """Raises PortProtocolError for invalid lifecycle port."""
        manager_mock = MagicMock(spec=SessionStateManager)
        guard_mock = MagicMock()
        manager_mock.mutation_guard = guard_mock

        writer = DirectWriterAdapter(manager_mock, guard_mock)

        with pytest.raises(PortProtocolError) as exc_info:
            SessionStateFactory.create_with_ports(
                session_id="test",
                storage=storage_adapter,
                events=event_adapter,
                writer=writer,
                lifecycle="not_a_lifecycle_port",  # Invalid
            )

        assert exc_info.value.port_name == "lifecycle"
        assert exc_info.value.expected is ILifecyclePort


# =============================================================================
# TEST: PortProtocolError
# =============================================================================


class TestPortProtocolError:
    """Tests for PortProtocolError exception."""

    def test_stores_port_name(self):
        """Stores the port name."""
        error = PortProtocolError(
            port_name="storage",
            expected=IStoragePort,
            got=str,
        )

        assert error.port_name == "storage"

    def test_stores_expected_type(self):
        """Stores the expected type."""
        error = PortProtocolError(
            port_name="storage",
            expected=IStoragePort,
            got=str,
        )

        assert error.expected is IStoragePort

    def test_stores_actual_type(self):
        """Stores the actual type."""
        error = PortProtocolError(
            port_name="storage",
            expected=IStoragePort,
            got=str,
        )

        assert error.got is str

    def test_message_format(self):
        """Error message includes port name and types."""
        error = PortProtocolError(
            port_name="events",
            expected=IEventPort,
            got=dict,
        )

        message = str(error)
        assert "events" in message
        assert "IEventPort" in message
        assert "dict" in message


# =============================================================================
# TEST: Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_create_standalone_function(self, test_db_path: Path):
        """create_standalone() function works."""
        manager = create_standalone(
            session_id="test",
            db_path=test_db_path,
        )

        assert isinstance(manager, SessionStateManager)

    def test_create_for_testing_function(self):
        """create_for_testing() function works."""
        manager = create_for_testing()

        assert isinstance(manager, SessionStateManager)
        assert manager._storage_port.storage_type == "memory"


# =============================================================================
# TEST: Validate Port Helper
# =============================================================================


class TestValidatePort:
    """Tests for _validate_port() helper method."""

    def test_valid_storage_port(self, storage_adapter):
        """Valid storage port passes validation."""
        # Should not raise
        SessionStateFactory._validate_port(
            storage_adapter,
            IStoragePort,
            "storage",
        )

    def test_valid_event_port(self, event_adapter):
        """Valid event port passes validation."""
        # Should not raise
        SessionStateFactory._validate_port(
            event_adapter,
            IEventPort,
            "events",
        )

    def test_invalid_port_raises(self):
        """Invalid port raises PortProtocolError."""
        with pytest.raises(PortProtocolError):
            SessionStateFactory._validate_port(
                "not_a_port",
                IStoragePort,
                "storage",
            )


# =============================================================================
# TEST: Integration (Full Workflow)
# =============================================================================


class TestFactoryIntegration:
    """Integration tests for complete factory workflows."""

    def test_standalone_start_stop(self, test_db_path: Path):
        """Standalone manager can start and stop."""
        manager = SessionStateFactory.create_standalone(
            session_id="test",
            db_path=test_db_path,
        )

        manager.start()
        assert manager.is_running

        manager.stop()
        assert not manager.is_running

    def test_testing_manager_start_stop(self):
        """Testing manager can start and stop."""
        manager = SessionStateFactory.create_for_testing()

        manager.start()
        assert manager.is_running

        manager.stop()
        assert not manager.is_running

    def test_standalone_persists_across_restarts(self, test_db_path: Path):
        """Standalone manager persists state across restarts."""
        # First session - write checkpoint
        manager1 = SessionStateFactory.create_standalone(
            session_id="persist-test",
            db_path=test_db_path,
        )
        manager1.start()

        # Stop with checkpoint (creates persistence data)
        manager1.stop()

        # Verify DB file exists
        assert test_db_path.exists()

        # Second session with same DB - should be able to restore
        manager2 = SessionStateFactory.create_standalone(
            session_id="persist-test",
            db_path=test_db_path,
        )
        manager2.start()

        # Session should be running (restore didn't fail)
        assert manager2.is_running

        manager2.stop()
