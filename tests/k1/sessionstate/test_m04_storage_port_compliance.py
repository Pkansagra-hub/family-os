"""
M4 E4.3 — SessionState Port Compliance Contract Tests
======================================================

Verifies that all 5 sessionstate port ABCs are properly defined
and that their adapters implement the required interfaces.

Ports:
    IStoragePort   - Storage operations (save, load, archive)
    IEventPort     - Event bus for sessionstate events
    IWriterPort    - Mutation write path
    ILifecyclePort - Lifecycle management (start, stop, checkpoint)
    IK0SyncPort    - K0 synchronization
"""

from abc import ABC

import pytest

from k1.sessionstate.ports import IEventPort, IK0SyncPort, ILifecyclePort, IStoragePort, IWriterPort

# =============================================================================
# Port ABC Compliance
# =============================================================================


class TestPortABCCompliance:
    """All 5 ports must be abstract base classes."""

    @pytest.mark.parametrize(
        "port",
        [IStoragePort, IEventPort, IWriterPort, ILifecyclePort, IK0SyncPort],
        ids=lambda p: p.__name__,
    )
    def test_port_is_abc(self, port):
        """Each port inherits from ABC."""
        assert issubclass(port, ABC), f"{port.__name__} must inherit from ABC"

    @pytest.mark.parametrize(
        "port",
        [IStoragePort, IEventPort, IWriterPort, ILifecyclePort, IK0SyncPort],
        ids=lambda p: p.__name__,
    )
    def test_port_has_abstract_methods(self, port):
        """Each port defines abstract methods."""
        assert hasattr(port, "__abstractmethods__")
        assert len(port.__abstractmethods__) > 0, f"{port.__name__} has no abstract methods"

    @pytest.mark.parametrize(
        "port",
        [IStoragePort, IEventPort, IWriterPort, ILifecyclePort, IK0SyncPort],
        ids=lambda p: p.__name__,
    )
    def test_port_cannot_be_instantiated(self, port):
        """ABC ports cannot be instantiated directly."""
        with pytest.raises(TypeError):
            port()


# =============================================================================
# Port Method Signatures
# =============================================================================


class TestIStoragePortContract:
    """IStoragePort defines storage operations."""

    def test_abstract_methods(self):
        methods = IStoragePort.__abstractmethods__
        assert "is_available" in methods
        assert "storage_type" in methods

    def test_has_archive_method(self):
        assert hasattr(IStoragePort, "archive")

    def test_has_restore_method(self):
        assert hasattr(IStoragePort, "restore")


class TestIEventPortContract:
    """IEventPort defines event bus operations."""

    def test_abstract_methods(self):
        methods = IEventPort.__abstractmethods__
        assert "emit" in methods
        assert "subscribe" in methods

    def test_has_unsubscribe_method(self):
        assert hasattr(IEventPort, "unsubscribe")

    def test_has_is_connected_method(self):
        assert "is_connected" in IEventPort.__abstractmethods__


class TestIWriterPortContract:
    """IWriterPort defines mutation write path."""

    def test_abstract_methods(self):
        methods = IWriterPort.__abstractmethods__
        assert "request_mutation" in methods
        assert "batch_mutations" in methods

    def test_has_writer_id(self):
        assert "writer_id" in IWriterPort.__abstractmethods__

    def test_has_validate_writer(self):
        assert "validate_writer" in IWriterPort.__abstractmethods__


class TestILifecyclePortContract:
    """ILifecyclePort defines lifecycle management."""

    def test_abstract_methods(self):
        methods = ILifecyclePort.__abstractmethods__
        assert "session_id" in methods
        assert "state" in methods
        assert "stop" in methods
        assert "checkpoint" in methods

    def test_has_config(self):
        assert "config" in ILifecyclePort.__abstractmethods__


class TestIK0SyncPortContract:
    """IK0SyncPort defines K0 synchronization."""

    def test_abstract_methods(self):
        methods = IK0SyncPort.__abstractmethods__
        assert "sync_to_k0" in methods
        assert "restore_from_k0" in methods
        assert "is_available" in methods

    def test_has_cancel_sync(self):
        assert "cancel_sync" in IK0SyncPort.__abstractmethods__


# =============================================================================
# Adapter isinstance Checks
# =============================================================================


class TestAdapterCompliance:
    """Adapters must implement their port interfaces."""

    def test_sqlite_storage_implements_istorageport(self):
        from k1.sessionstate.adapters.sqlite_storage import SQLiteStorageAdapter

        assert issubclass(SQLiteStorageAdapter, IStoragePort)

    def test_local_events_implements_ieventport(self):
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        assert issubclass(LocalEventAdapter, IEventPort)

    def test_direct_writer_implements_iwriterport(self):
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter

        assert issubclass(DirectWriterAdapter, IWriterPort)


# =============================================================================
# Port Count Verification
# =============================================================================


class TestPortInventory:
    """Verify all 5 ports are accounted for."""

    def test_five_ports_total(self):
        """M4 requires exactly 5 port ABCs."""
        ports = [IStoragePort, IEventPort, IWriterPort, ILifecyclePort, IK0SyncPort]
        assert len(ports) == 5

    def test_all_ports_in_ports_package(self):
        """All ports are importable from k1.sessionstate.ports."""
        import k1.sessionstate.ports as p

        assert hasattr(p, "IStoragePort")
        assert hasattr(p, "IEventPort")
        assert hasattr(p, "IWriterPort")
        assert hasattr(p, "ILifecyclePort")
        assert hasattr(p, "IK0SyncPort")
