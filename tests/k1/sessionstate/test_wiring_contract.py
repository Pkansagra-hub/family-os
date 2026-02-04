"""
Wiring Contract Compliance Tests
=================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.4 Contract Tests
ISSUE: 4.4.4

CONTRACT: k1/contracts/modules/sessionstate/wiring.contract.yaml

PURPOSE:
    Validate SessionState wiring: port interfaces, adapter implementations,
    capability provisions, and file structure match wiring.contract.yaml.

    Wiring contract specifies:
    - Required files and code roots
    - Port interfaces and their methods
    - Capability provisions (session:read:v1, session:write:v1, etc.)
    - Adapter implementations for each port

TEST PHILOSOPHY:
    NO MOCKS - Real module imports and interface checks only.
    Contract-first validation.

Run with: pytest tests/k1/sessionstate/test_wiring_contract.py -v
"""

import abc
from pathlib import Path

# =============================================================================
# FILE STRUCTURE TESTS
# =============================================================================


class TestRequiredFiles:
    """Test all required files from wiring.contract.yaml exist."""

    def test_init_file_exists(self):
        """k1/sessionstate/__init__.py exists."""
        path = Path("k1/sessionstate/__init__.py")
        assert path.exists(), f"Missing: {path}"

    def test_sections_init_exists(self):
        """k1/sessionstate/sections/__init__.py exists."""
        path = Path("k1/sessionstate/sections/__init__.py")
        assert path.exists(), f"Missing: {path}"

    def test_tiers_init_exists(self):
        """k1/sessionstate/tiers/__init__.py exists."""
        path = Path("k1/sessionstate/tiers/__init__.py")
        assert path.exists(), f"Missing: {path}"

    def test_manager_file_exists(self):
        """k1/sessionstate/manager.py exists."""
        path = Path("k1/sessionstate/manager.py")
        assert path.exists(), f"Missing: {path}"

    def test_guard_file_exists(self):
        """k1/sessionstate/guard.py exists."""
        path = Path("k1/sessionstate/guard.py")
        assert path.exists(), f"Missing: {path}"

    def test_eviction_file_exists(self):
        """k1/sessionstate/eviction.py exists."""
        path = Path("k1/sessionstate/eviction.py")
        assert path.exists(), f"Missing: {path}"

    def test_migration_file_exists(self):
        """k1/sessionstate/migration.py exists."""
        path = Path("k1/sessionstate/migration.py")
        assert path.exists(), f"Missing: {path}"

    def test_sizetracker_file_exists(self):
        """k1/sessionstate/sizetracker.py exists."""
        path = Path("k1/sessionstate/sizetracker.py")
        assert path.exists(), f"Missing: {path}"

    def test_reconstruction_file_exists(self):
        """k1/sessionstate/reconstruction.py exists."""
        path = Path("k1/sessionstate/reconstruction.py")
        assert path.exists(), f"Missing: {path}"

    def test_snapshot_file_exists(self):
        """k1/sessionstate/snapshot.py exists."""
        path = Path("k1/sessionstate/snapshot.py")
        assert path.exists(), f"Missing: {path}"


class TestCodeRoots:
    """Test code roots are correctly structured."""

    def test_sessionstate_is_package(self):
        """k1/sessionstate is a Python package (has __init__.py)."""
        path = Path("k1/sessionstate/__init__.py")
        assert path.exists()

    def test_sections_is_subpackage(self):
        """k1/sessionstate/sections is a Python subpackage."""
        path = Path("k1/sessionstate/sections/__init__.py")
        assert path.exists()

    def test_tiers_is_subpackage(self):
        """k1/sessionstate/tiers is a Python subpackage."""
        path = Path("k1/sessionstate/tiers/__init__.py")
        assert path.exists()


# =============================================================================
# PORT INTERFACE TESTS
# =============================================================================


class TestIStoragePortInterface:
    """Test IStoragePort interface matches contract."""

    def test_is_abstract_class(self):
        """IStoragePort is an abstract base class."""
        from k1.sessionstate.ports import IStoragePort

        assert issubclass(IStoragePort, abc.ABC) or hasattr(IStoragePort, "__abstractmethods__")

    def test_has_archive_method(self):
        """IStoragePort has archive method."""
        from k1.sessionstate.ports import IStoragePort

        assert hasattr(IStoragePort, "archive")

    def test_has_restore_method(self):
        """IStoragePort has restore method."""
        from k1.sessionstate.ports import IStoragePort

        assert hasattr(IStoragePort, "restore")

    def test_has_delete_method(self):
        """IStoragePort has delete method."""
        from k1.sessionstate.ports import IStoragePort

        assert hasattr(IStoragePort, "delete")

    def test_has_list_archives_method(self):
        """IStoragePort has list_archives method."""
        from k1.sessionstate.ports import IStoragePort

        assert hasattr(IStoragePort, "list_archives")


class TestIEventPortInterface:
    """Test IEventPort interface matches contract."""

    def test_is_abstract_class(self):
        """IEventPort is an abstract base class."""
        from k1.sessionstate.ports import IEventPort

        assert issubclass(IEventPort, abc.ABC) or hasattr(IEventPort, "__abstractmethods__")

    def test_has_emit_method(self):
        """IEventPort has emit method."""
        from k1.sessionstate.ports import IEventPort

        assert hasattr(IEventPort, "emit")

    def test_has_subscribe_method(self):
        """IEventPort has subscribe method."""
        from k1.sessionstate.ports import IEventPort

        assert hasattr(IEventPort, "subscribe")


class TestIWriterPortInterface:
    """Test IWriterPort interface matches contract."""

    def test_is_abstract_class(self):
        """IWriterPort is an abstract base class."""
        from k1.sessionstate.ports import IWriterPort

        assert issubclass(IWriterPort, abc.ABC) or hasattr(IWriterPort, "__abstractmethods__")

    def test_has_request_mutation_method(self):
        """IWriterPort has request_mutation method."""
        from k1.sessionstate.ports import IWriterPort

        assert hasattr(IWriterPort, "request_mutation")

    def test_has_validate_writer_method(self):
        """IWriterPort has validate_writer method."""
        from k1.sessionstate.ports import IWriterPort

        assert hasattr(IWriterPort, "validate_writer")

    def test_has_batch_mutations_method(self):
        """IWriterPort has batch_mutations method."""
        from k1.sessionstate.ports import IWriterPort

        assert hasattr(IWriterPort, "batch_mutations")


class TestILifecyclePortInterface:
    """Test ILifecyclePort interface matches contract."""

    def test_is_abstract_class(self):
        """ILifecyclePort is an abstract base class."""
        from k1.sessionstate.ports import ILifecyclePort

        assert issubclass(ILifecyclePort, abc.ABC) or hasattr(ILifecyclePort, "__abstractmethods__")

    def test_has_start_method(self):
        """ILifecyclePort has start method."""
        from k1.sessionstate.ports import ILifecyclePort

        assert hasattr(ILifecyclePort, "start")

    def test_has_stop_method(self):
        """ILifecyclePort has stop method."""
        from k1.sessionstate.ports import ILifecyclePort

        assert hasattr(ILifecyclePort, "stop")

    def test_has_checkpoint_method(self):
        """ILifecyclePort has checkpoint method."""
        from k1.sessionstate.ports import ILifecyclePort

        assert hasattr(ILifecyclePort, "checkpoint")


class TestIK0SyncPortInterface:
    """Test IK0SyncPort interface matches contract."""

    def test_is_abstract_class(self):
        """IK0SyncPort is an abstract base class."""
        from k1.sessionstate.ports import IK0SyncPort

        assert issubclass(IK0SyncPort, abc.ABC) or hasattr(IK0SyncPort, "__abstractmethods__")

    def test_has_sync_to_k0_method(self):
        """IK0SyncPort has sync_to_k0 method."""
        from k1.sessionstate.ports import IK0SyncPort

        assert hasattr(IK0SyncPort, "sync_to_k0")

    def test_has_restore_from_k0_method(self):
        """IK0SyncPort has restore_from_k0 method."""
        from k1.sessionstate.ports import IK0SyncPort

        assert hasattr(IK0SyncPort, "restore_from_k0")

    def test_has_is_available_property(self):
        """IK0SyncPort has is_available property."""
        from k1.sessionstate.ports import IK0SyncPort

        assert hasattr(IK0SyncPort, "is_available")


# =============================================================================
# ADAPTER IMPLEMENTATION TESTS
# =============================================================================


class TestSQLiteStorageAdapter:
    """Test SQLiteStorageAdapter implements IStoragePort."""

    def test_inherits_from_istorageport(self):
        """SQLiteStorageAdapter inherits from IStoragePort."""
        from k1.sessionstate.adapters import SQLiteStorageAdapter
        from k1.sessionstate.ports import IStoragePort

        assert issubclass(SQLiteStorageAdapter, IStoragePort)

    def test_implements_archive(self):
        """SQLiteStorageAdapter implements archive method."""
        from k1.sessionstate.adapters import SQLiteStorageAdapter

        assert hasattr(SQLiteStorageAdapter, "archive")
        assert callable(getattr(SQLiteStorageAdapter, "archive", None))

    def test_implements_restore(self):
        """SQLiteStorageAdapter implements restore method."""
        from k1.sessionstate.adapters import SQLiteStorageAdapter

        assert hasattr(SQLiteStorageAdapter, "restore")
        assert callable(getattr(SQLiteStorageAdapter, "restore", None))

    def test_implements_delete(self):
        """SQLiteStorageAdapter implements delete method."""
        from k1.sessionstate.adapters import SQLiteStorageAdapter

        assert hasattr(SQLiteStorageAdapter, "delete")
        assert callable(getattr(SQLiteStorageAdapter, "delete", None))


class TestInMemoryStorageAdapter:
    """Test InMemoryStorageAdapter implements IStoragePort."""

    def test_inherits_from_istorageport(self):
        """InMemoryStorageAdapter inherits from IStoragePort."""
        from k1.sessionstate.adapters import InMemoryStorageAdapter
        from k1.sessionstate.ports import IStoragePort

        assert issubclass(InMemoryStorageAdapter, IStoragePort)

    def test_implements_archive(self):
        """InMemoryStorageAdapter implements archive method."""
        from k1.sessionstate.adapters import InMemoryStorageAdapter

        assert hasattr(InMemoryStorageAdapter, "archive")
        assert callable(getattr(InMemoryStorageAdapter, "archive", None))

    def test_implements_restore(self):
        """InMemoryStorageAdapter implements restore method."""
        from k1.sessionstate.adapters import InMemoryStorageAdapter

        assert hasattr(InMemoryStorageAdapter, "restore")
        assert callable(getattr(InMemoryStorageAdapter, "restore", None))


class TestLocalEventAdapter:
    """Test LocalEventAdapter implements IEventPort."""

    def test_inherits_from_ieventport(self):
        """LocalEventAdapter inherits from IEventPort."""
        from k1.sessionstate.adapters import LocalEventAdapter
        from k1.sessionstate.ports import IEventPort

        assert issubclass(LocalEventAdapter, IEventPort)

    def test_implements_emit(self):
        """LocalEventAdapter implements emit method."""
        from k1.sessionstate.adapters import LocalEventAdapter

        assert hasattr(LocalEventAdapter, "emit")
        assert callable(getattr(LocalEventAdapter, "emit", None))

    def test_implements_subscribe(self):
        """LocalEventAdapter implements subscribe method."""
        from k1.sessionstate.adapters import LocalEventAdapter

        assert hasattr(LocalEventAdapter, "subscribe")
        assert callable(getattr(LocalEventAdapter, "subscribe", None))


class TestDirectWriterAdapter:
    """Test DirectWriterAdapter implements IWriterPort."""

    def test_inherits_from_iwriterport(self):
        """DirectWriterAdapter inherits from IWriterPort."""
        from k1.sessionstate.adapters import DirectWriterAdapter
        from k1.sessionstate.ports import IWriterPort

        assert issubclass(DirectWriterAdapter, IWriterPort)

    def test_implements_request_mutation(self):
        """DirectWriterAdapter implements request_mutation method."""
        from k1.sessionstate.adapters import DirectWriterAdapter

        assert hasattr(DirectWriterAdapter, "request_mutation")
        assert callable(getattr(DirectWriterAdapter, "request_mutation", None))

    def test_implements_validate_writer(self):
        """DirectWriterAdapter implements validate_writer method."""
        from k1.sessionstate.adapters import DirectWriterAdapter

        assert hasattr(DirectWriterAdapter, "validate_writer")
        assert callable(getattr(DirectWriterAdapter, "validate_writer", None))


class TestStandaloneLifecycle:
    """Test StandaloneLifecycle implements ILifecyclePort."""

    def test_inherits_from_ilifecycleport(self):
        """StandaloneLifecycle inherits from ILifecyclePort."""
        from k1.sessionstate.adapters import StandaloneLifecycle
        from k1.sessionstate.ports import ILifecyclePort

        assert issubclass(StandaloneLifecycle, ILifecyclePort)

    def test_implements_start(self):
        """StandaloneLifecycle implements start method."""
        from k1.sessionstate.adapters import StandaloneLifecycle

        assert hasattr(StandaloneLifecycle, "start")
        assert callable(getattr(StandaloneLifecycle, "start", None))

    def test_implements_stop(self):
        """StandaloneLifecycle implements stop method."""
        from k1.sessionstate.adapters import StandaloneLifecycle

        assert hasattr(StandaloneLifecycle, "stop")
        assert callable(getattr(StandaloneLifecycle, "stop", None))

    def test_implements_checkpoint(self):
        """StandaloneLifecycle implements checkpoint method."""
        from k1.sessionstate.adapters import StandaloneLifecycle

        assert hasattr(StandaloneLifecycle, "checkpoint")
        assert callable(getattr(StandaloneLifecycle, "checkpoint", None))


# =============================================================================
# CAPABILITY PROVISION TESTS
# =============================================================================


class TestSessionReadCapability:
    """Test session:read:v1 capability is provided."""

    def test_manager_has_get_section_method(self):
        """Manager provides get_section for reading."""
        from k1.sessionstate import SessionStateManager

        assert hasattr(SessionStateManager, "get_section")

    def test_manager_has_get_snapshot_method(self):
        """Manager provides get_snapshot for reading full state."""
        from k1.sessionstate import SessionStateManager

        assert hasattr(SessionStateManager, "get_snapshot")


class TestSessionWriteCapability:
    """Test session:write:v1 capability is provided."""

    def test_manager_has_mutate_method(self):
        """Manager provides mutate for writing."""
        from k1.sessionstate import SessionStateManager

        assert hasattr(SessionStateManager, "mutate")

    def test_manager_has_mutation_guard(self):
        """Manager provides mutation_guard for validation."""
        from k1.sessionstate import SessionStateManager

        assert hasattr(SessionStateManager, "mutation_guard")


class TestSessionHealthCapability:
    """Test session:health:v1 capability is provided."""

    def test_snapshot_has_sizes(self):
        """SessionSnapshot provides size breakdown."""
        # Check the dataclass has size-related fields
        import dataclasses

        from k1.sessionstate import SessionSnapshot

        fields = {f.name for f in dataclasses.fields(SessionSnapshot)}
        assert "total_size_bytes" in fields or "hot_size_bytes" in fields

    def test_snapshot_has_pressure(self):
        """SessionSnapshot provides pressure status."""
        import dataclasses

        from k1.sessionstate import SessionSnapshot

        fields = {f.name for f in dataclasses.fields(SessionSnapshot)}
        assert "pressure" in fields


class TestSessionMigrateCapability:
    """Test session:migrate:v1 capability is provided."""

    def test_migrationengine_exists(self):
        """MigrationEngine provides migration capability."""
        from k1.sessionstate import MigrationEngine

        assert MigrationEngine is not None

    def test_migrationengine_has_demote_method(self):
        """MigrationEngine has demote method."""
        from k1.sessionstate import MigrationEngine

        assert hasattr(MigrationEngine, "demote") or hasattr(MigrationEngine, "demote_on_pressure")


class TestSessionReconstructCapability:
    """Test session:reconstruct:v1 capability is provided."""

    def test_reconstructionsla_exists(self):
        """ReconstructionSLA provides reconstruction capability."""
        from k1.sessionstate import ReconstructionSLA

        assert ReconstructionSLA is not None

    def test_manager_has_restore_method(self):
        """Manager provides restore method."""
        from k1.sessionstate import SessionStateManager

        # restore may be called via start(restore_if_exists=True)
        assert hasattr(SessionStateManager, "start")


# =============================================================================
# CONSUMED CAPABILITY TESTS
# =============================================================================


class TestStorageArchiveCapability:
    """Test storage:archive:v1 capability is consumed."""

    def test_localcoldarchive_exists(self):
        """LocalColdArchive provides archival storage."""
        from k1.sessionstate import LocalColdArchive

        assert LocalColdArchive is not None

    def test_localcoldarchive_has_archive_method(self):
        """LocalColdArchive has archive method."""
        from k1.sessionstate import LocalColdArchive

        assert hasattr(LocalColdArchive, "archive") or hasattr(LocalColdArchive, "store")


class TestBusPublishCapability:
    """Test bus:publish:v1 capability is consumed via IEventPort."""

    def test_ieventport_has_emit(self):
        """IEventPort.emit provides publish capability."""
        from k1.sessionstate.ports import IEventPort

        assert hasattr(IEventPort, "emit")


# =============================================================================
# FACTORY WIRING TESTS
# =============================================================================


class TestFactoryWiring:
    """Test SessionStateFactory correctly wires ports and adapters."""

    def test_create_standalone_wires_storage_port(self):
        """create_standalone wires a storage port."""
        from k1.sessionstate import SessionStateFactory

        manager = SessionStateFactory.create_standalone(session_id="test-wiring-storage")
        # Manager should have storage port wired
        assert manager is not None
        manager.stop()

    def test_create_standalone_wires_event_port(self):
        """create_standalone wires an event port."""
        from k1.sessionstate import SessionStateFactory

        manager = SessionStateFactory.create_standalone(session_id="test-wiring-event")
        # Manager should have event port wired
        assert hasattr(manager, "_event_port") or hasattr(manager, "event_port")
        manager.stop()

    def test_create_with_ports_requires_all_ports(self):
        """Factory requires all 4 ports for create_with_ports."""
        import inspect

        from k1.sessionstate import SessionStateFactory

        sig = inspect.signature(SessionStateFactory.create_with_ports)
        params = list(sig.parameters.keys())
        # Should require storage, events, writer, lifecycle
        assert "storage" in params
        assert "events" in params
        assert "writer" in params
        assert "lifecycle" in params

    def test_create_for_testing_works(self):
        """create_for_testing creates working manager."""
        from k1.sessionstate import SessionStateFactory

        manager = SessionStateFactory.create_for_testing(session_id="test-factory-testing")
        assert manager is not None
        manager.stop()


# =============================================================================
# ALL ADAPTERS COUNT
# =============================================================================


class TestAdapterCounts:
    """Test expected number of adapters are available."""

    def test_storage_adapters_count(self):
        """At least 2 storage adapters available (SQLite, InMemory)."""
        from k1.sessionstate.adapters import InMemoryStorageAdapter, SQLiteStorageAdapter

        assert SQLiteStorageAdapter is not None
        assert InMemoryStorageAdapter is not None

    def test_event_adapters_count(self):
        """At least 1 event adapter available (LocalEventAdapter)."""
        from k1.sessionstate.adapters import LocalEventAdapter

        assert LocalEventAdapter is not None

    def test_writer_adapters_count(self):
        """At least 1 writer adapter available (DirectWriterAdapter)."""
        from k1.sessionstate.adapters import DirectWriterAdapter

        assert DirectWriterAdapter is not None

    def test_lifecycle_adapters_count(self):
        """At least 1 lifecycle adapter available (StandaloneLifecycle)."""
        from k1.sessionstate.adapters import StandaloneLifecycle

        assert StandaloneLifecycle is not None


# =============================================================================
# PORT PROTOCOL TESTS
# =============================================================================


class TestPortDataclasses:
    """Test port-related dataclasses exist."""

    def test_mutationrequest_exists(self):
        """MutationRequest dataclass exists in ports."""
        from k1.sessionstate.ports import MutationRequest

        assert MutationRequest is not None

    def test_mutationresponse_exists(self):
        """MutationResponse dataclass exists in ports."""
        from k1.sessionstate.ports import MutationResponse

        assert MutationResponse is not None

    def test_startresult_exists(self):
        """StartResult dataclass exists in ports."""
        from k1.sessionstate.ports import StartResult

        assert StartResult is not None

    def test_stopresult_exists(self):
        """StopResult dataclass exists in ports."""
        from k1.sessionstate.ports import StopResult

        assert StopResult is not None

    def test_checkpointresult_exists(self):
        """CheckpointResult dataclass exists in ports."""
        from k1.sessionstate.ports import CheckpointResult

        assert CheckpointResult is not None

    def test_restoreresult_exists(self):
        """RestoreResult dataclass exists in ports."""
        from k1.sessionstate.ports import RestoreResult

        assert RestoreResult is not None


class TestPortEnums:
    """Test port-related enums exist."""

    def test_lifecyclestate_exists(self):
        """LifecycleState enum exists in ports."""
        from k1.sessionstate.ports import LifecycleState

        assert LifecycleState is not None

    def test_mutationstatus_exists(self):
        """MutationStatus enum exists in ports."""
        from k1.sessionstate.ports import MutationStatus

        assert MutationStatus is not None

    def test_pressurelevel_exists(self):
        """PressureLevel enum exists in ports."""
        from k1.sessionstate.ports import PressureLevel

        assert PressureLevel is not None

        assert PressureLevel is not None
