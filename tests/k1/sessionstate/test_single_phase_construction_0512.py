"""
E-0.5.12 — SessionState Single-Phase Construction Tests
========================================================

Verifies that the two-phase construction smell is eliminated:
- Manager never has None ports after construction
- Factory creates all ports FIRST, passes them to constructor
- bind_manager() correctly sets manager references on adapters
- Existing factory behavior is preserved (backward compatibility)

EPIC: E-0.5.12
ISSUE: I-0.5.12.2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager
from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
from k1.sessionstate.guard import MutationGuard
from k1.sessionstate.ports.events import IEventPort
from k1.sessionstate.ports.lifecycle import ILifecyclePort, LifecycleConfig
from k1.sessionstate.ports.storage import IStoragePort
from k1.sessionstate.ports.writer import IWriterPort

# =============================================================================
# TEST: Manager never has None ports after factory construction
# =============================================================================


class TestNoNonePorts:
    """Verify manager ports are never None after factory construction."""

    def test_create_standalone_no_none_ports(self, tmp_path: Path):
        """create_standalone() produces manager with all ports non-None."""
        db_path = tmp_path / "test.db"
        manager = SessionStateFactory.create_standalone(
            session_id="test-no-none",
            db_path=db_path,
        )

        assert manager._storage_port is not None
        assert manager._event_port is not None
        assert manager._writer_port is not None
        assert manager._lifecycle_port is not None

    def test_create_for_testing_no_none_ports(self):
        """create_for_testing() produces manager with all ports non-None."""
        manager = SessionStateFactory.create_for_testing(session_id="test-no-none")

        assert manager._storage_port is not None
        assert manager._event_port is not None
        assert manager._writer_port is not None
        assert manager._lifecycle_port is not None

    def test_create_standalone_ports_are_correct_type(self, tmp_path: Path):
        """create_standalone() wires correct adapter types."""
        db_path = tmp_path / "test.db"
        manager = SessionStateFactory.create_standalone(
            session_id="test-types",
            db_path=db_path,
        )

        assert isinstance(manager._storage_port, IStoragePort)
        assert isinstance(manager._event_port, IEventPort)
        assert isinstance(manager._writer_port, IWriterPort)
        assert isinstance(manager._lifecycle_port, ILifecyclePort)

    def test_create_for_testing_ports_are_correct_type(self):
        """create_for_testing() wires correct adapter types."""
        manager = SessionStateFactory.create_for_testing()

        assert isinstance(manager._storage_port, IStoragePort)
        assert isinstance(manager._event_port, IEventPort)
        assert isinstance(manager._writer_port, IWriterPort)
        assert isinstance(manager._lifecycle_port, ILifecyclePort)

    def test_k0_sync_port_slot_exists(self):
        """_k0_sync_port is in __slots__ (was a latent bug)."""
        assert "_k0_sync_port" in SessionStateManager.__slots__

    def test_k0_sync_port_defaults_none(self):
        """_k0_sync_port defaults to None when not provided."""
        manager = SessionStateFactory.create_for_testing()
        assert manager._k0_sync_port is None


# =============================================================================
# TEST: bind_manager on DirectWriterAdapter
# =============================================================================


class TestDirectWriterBindManager:
    """Verify DirectWriterAdapter.bind_manager() works correctly."""

    def test_bind_sets_manager(self):
        """bind_manager sets _manager reference."""
        adapter = DirectWriterAdapter(writer_id="test")
        assert adapter._manager is None

        mock_manager = MagicMock(spec=SessionStateManager)
        mock_manager.session_id = "bind-test"
        mock_guard = MagicMock(spec=MutationGuard)

        adapter.bind_manager(mock_manager, mock_guard)

        assert adapter._manager is mock_manager
        assert adapter._guard is mock_guard

    def test_bind_raises_if_already_bound(self):
        """bind_manager raises RuntimeError if already bound."""
        mock_manager = MagicMock(spec=SessionStateManager)
        mock_manager.session_id = "test"
        mock_guard = MagicMock(spec=MutationGuard)

        adapter = DirectWriterAdapter(manager=mock_manager, guard=mock_guard, writer_id="test")

        with pytest.raises(RuntimeError, match="already bound"):
            adapter.bind_manager(mock_manager, mock_guard)

    def test_unbound_adapter_is_writerport(self):
        """Unbound adapter is still an IWriterPort instance."""
        adapter = DirectWriterAdapter(writer_id="unbound")
        assert isinstance(adapter, IWriterPort)

    def test_positional_arg_backward_compat(self):
        """Existing positional arg calls still work."""
        mock_manager = MagicMock(spec=SessionStateManager)
        mock_manager.session_id = "test"
        mock_guard = MagicMock(spec=MutationGuard)

        # This is how existing code calls it: positional (manager, guard)
        adapter = DirectWriterAdapter(mock_manager, mock_guard)
        assert adapter._manager is mock_manager
        assert adapter._guard is mock_guard


# =============================================================================
# TEST: bind_manager on StandaloneLifecycle
# =============================================================================


class TestStandaloneLifecycleBindManager:
    """Verify StandaloneLifecycle.bind_manager() works correctly."""

    def test_bind_sets_manager(self):
        """bind_manager sets _manager reference."""
        lifecycle = StandaloneLifecycle(config=LifecycleConfig.testing())
        assert lifecycle._manager is None

        mock_manager = MagicMock(spec=SessionStateManager)
        mock_manager.session_id = "bind-test"

        lifecycle.bind_manager(mock_manager)

        assert lifecycle._manager is mock_manager

    def test_bind_raises_if_already_bound(self):
        """bind_manager raises RuntimeError if already bound."""
        mock_manager = MagicMock(spec=SessionStateManager)
        mock_manager.session_id = "test"

        lifecycle = StandaloneLifecycle(manager=mock_manager, checkpoint_interval_s=0)

        with pytest.raises(RuntimeError, match="already bound"):
            lifecycle.bind_manager(mock_manager)

    def test_unbound_lifecycle_is_lifecycleport(self):
        """Unbound lifecycle is still an ILifecyclePort instance."""
        lifecycle = StandaloneLifecycle()
        assert isinstance(lifecycle, ILifecyclePort)

    def test_positional_arg_backward_compat(self):
        """Existing positional arg calls still work."""
        mock_manager = MagicMock(spec=SessionStateManager)
        mock_manager.session_id = "test"

        # This is how existing code calls it: positional (manager)
        lifecycle = StandaloneLifecycle(mock_manager, checkpoint_interval_s=0)
        assert lifecycle._manager is mock_manager


# =============================================================================
# TEST: Single-phase factory flow end-to-end
# =============================================================================


class TestSinglePhaseFlow:
    """End-to-end tests for the single-phase construction pattern."""

    def test_standalone_writer_bound_to_correct_manager(self, tmp_path: Path):
        """Writer adapter is bound to the same manager it's a port of."""
        db_path = tmp_path / "test.db"
        manager = SessionStateFactory.create_standalone(
            session_id="e2e-test",
            db_path=db_path,
        )

        writer = manager._writer_port
        assert isinstance(writer, DirectWriterAdapter)
        assert writer._manager is manager

    def test_standalone_lifecycle_bound_to_correct_manager(self, tmp_path: Path):
        """Lifecycle adapter is bound to the same manager it's a port of."""
        db_path = tmp_path / "test.db"
        manager = SessionStateFactory.create_standalone(
            session_id="e2e-test",
            db_path=db_path,
        )

        lifecycle = manager._lifecycle_port
        assert isinstance(lifecycle, StandaloneLifecycle)
        assert lifecycle._manager is manager

    def test_testing_writer_bound_to_correct_manager(self):
        """Testing writer is bound to the correct manager."""
        manager = SessionStateFactory.create_for_testing()

        writer = manager._writer_port
        assert isinstance(writer, DirectWriterAdapter)
        assert writer._manager is manager

    def test_testing_lifecycle_bound_to_correct_manager(self):
        """Testing lifecycle is bound to the correct manager."""
        manager = SessionStateFactory.create_for_testing()

        lifecycle = manager._lifecycle_port
        assert isinstance(lifecycle, StandaloneLifecycle)
        assert lifecycle._manager is manager

    def test_writer_guard_is_manager_guard(self):
        """Writer's guard is the manager's mutation_guard."""
        manager = SessionStateFactory.create_for_testing()

        writer = manager._writer_port
        assert isinstance(writer, DirectWriterAdapter)
        assert writer._guard is manager.mutation_guard

    def test_standalone_start_stop_with_single_phase(self, tmp_path: Path):
        """Full start/stop cycle works with single-phase construction."""
        db_path = tmp_path / "test.db"
        manager = SessionStateFactory.create_standalone(
            session_id="lifecycle-test",
            db_path=db_path,
        )

        manager.start()
        assert manager.is_running

        manager.stop()
        assert not manager.is_running

    def test_testing_start_stop_with_single_phase(self):
        """Full start/stop cycle works with single-phase construction."""
        manager = SessionStateFactory.create_for_testing()

        manager.start()
        assert manager.is_running

        manager.stop()
        assert not manager.is_running

    def test_mutation_after_single_phase_construction(self):
        """Mutations work correctly after single-phase construction."""
        manager = SessionStateFactory.create_for_testing()
        manager.start()

        # Perform a mutation through the writer port
        result = manager.mutate(
            section="scoreboard",
            operation="set",
            data={"topic": "weather"},
        )

        assert result is not None
        manager.stop()
