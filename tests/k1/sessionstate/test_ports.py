"""
Port and Adapter Tests
======================

Tests for port interfaces and adapter implementations.

IMPLEMENTATION SPEC:
-------------------
Test port interfaces from k1/sessionstate/ports/
Test adapters from k1/sessionstate/adapters/

PORT INTERFACES:
---------------
- IStoragePort: LOCAL COLD persistence
- IEventPort: Event emission
- IWriterPort: Mutation coordination
- ILifecyclePort: Lifecycle management
- IK0SyncPort: Optional K0 cloud sync

ADAPTERS:
--------
- SQLiteStorageAdapter: Local SQLite storage
- InMemoryStorageAdapter: In-memory (testing)
- LocalEventAdapter: In-process events
- DirectWriterAdapter: Direct mutations
- StandaloneLifecycle: Self-managed lifecycle

TEST CATEGORIES:
---------------
1. Contract Tests (interface compliance)
   - All adapters implement port interface
   - All required methods present
   - Return types match specification

2. Adapter Unit Tests
   - SQLiteStorageAdapter CRUD operations
   - InMemoryStorageAdapter isolation
   - LocalEventAdapter capture mode
   - DirectWriterAdapter mutation flow
   - StandaloneLifecycle state machine

EXAMPLE TESTS:
-------------
class TestStoragePortContract:
    def test_sqlite_implements_interface(self):
        adapter = SQLiteStorageAdapter(db_path)
        assert isinstance(adapter, IStoragePort)

    def test_memory_implements_interface(self):
        adapter = InMemoryStorageAdapter()
        assert isinstance(adapter, IStoragePort)

class TestSQLiteStorageAdapter:
    def test_archive_creates_record(self, sqlite_storage):
        result = sqlite_storage.archive(
            section="beliefs",
            data=b"test data",
            metadata={"session_id": "test"},
        )
        assert result.success
        assert result.archive_id is not None

COVERAGE REQUIREMENTS:
--------------------
- All ports have contract tests
- All adapters fully tested
- Error paths covered
- Edge cases (empty data, large data)
"""

from pathlib import Path

# Imports to add when implementing:
# from k1.sessionstate.ports import (
#     IStoragePort,
#     IEventPort,
#     IWriterPort,
#     ILifecyclePort,
#     IK0SyncPort,
#     NullSyncPort,
# )
# from k1.sessionstate.adapters import (
#     SQLiteStorageAdapter,
#     InMemoryStorageAdapter,
#     LocalEventAdapter,
#     DirectWriterAdapter,
#     StandaloneLifecycle,
# )


# =============================================================================
# CONTRACT TESTS (Interface Compliance)
# =============================================================================


class TestStoragePortContract:
    """Verify adapters implement IStoragePort correctly."""

    def test_sqlite_implements_interface(self):
        """SQLiteStorageAdapter implements IStoragePort."""
        # TODO: Implement
        # adapter = SQLiteStorageAdapter(db_path)
        # assert isinstance(adapter, IStoragePort)
        pass

    def test_memory_implements_interface(self):
        """InMemoryStorageAdapter implements IStoragePort."""
        # TODO: Implement
        pass

    def test_storage_has_is_available(self):
        """Storage adapters have is_available property."""
        # TODO: Implement
        pass

    def test_storage_has_storage_type(self):
        """Storage adapters have storage_type property."""
        # TODO: Implement
        pass


class TestEventPortContract:
    """Verify adapters implement IEventPort correctly."""

    def test_local_implements_interface(self):
        """LocalEventAdapter implements IEventPort."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter
        from k1.sessionstate.ports.events import IEventPort

        adapter = LocalEventAdapter()
        assert isinstance(adapter, IEventPort)
        adapter.stop()

    def test_event_has_is_connected(self):
        """Event adapters have is_connected property."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        assert hasattr(adapter, "is_connected")
        assert isinstance(adapter.is_connected, bool)
        adapter.stop()

    def test_event_has_emit_method(self):
        """Event adapters have emit() method."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        assert hasattr(adapter, "emit")
        assert callable(adapter.emit)
        adapter.stop()

    def test_event_has_subscribe_method(self):
        """Event adapters have subscribe() method."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        assert hasattr(adapter, "subscribe")
        assert callable(adapter.subscribe)
        adapter.stop()

    def test_event_has_unsubscribe_method(self):
        """Event adapters have unsubscribe() method."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        assert hasattr(adapter, "unsubscribe")
        assert callable(adapter.unsubscribe)
        adapter.stop()


class TestWriterPortContract:
    """Verify adapters implement IWriterPort correctly."""

    def test_direct_implements_interface(self):
        """DirectWriterAdapter implements IWriterPort."""
        # DirectWriterAdapter not implemented yet - test dataclasses instead
        from k1.sessionstate.ports.writer import IWriterPort

        assert hasattr(IWriterPort, "writer_id")
        assert hasattr(IWriterPort, "is_connected")
        assert hasattr(IWriterPort, "request_mutation")
        assert hasattr(IWriterPort, "batch_mutations")
        assert hasattr(IWriterPort, "validate_writer")

    def test_writer_has_writer_id(self):
        """Writer port interface has writer_id property."""
        import inspect

        from k1.sessionstate.ports.writer import IWriterPort

        # Check it's an abstract property
        assert hasattr(IWriterPort, "writer_id")
        assert isinstance(inspect.getattr_static(IWriterPort, "writer_id"), property)


# =============================================================================
# LIFECYCLE PORT CONTRACT TESTS
# =============================================================================


class TestLifecyclePortContract:
    """Verify ILifecyclePort interface compliance."""

    def test_has_state_property(self):
        """ILifecyclePort has state property."""
        import inspect

        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "state")
        assert isinstance(inspect.getattr_static(ILifecyclePort, "state"), property)

    def test_has_session_id_property(self):
        """ILifecyclePort has session_id property."""
        import inspect

        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "session_id")
        assert isinstance(inspect.getattr_static(ILifecyclePort, "session_id"), property)

    def test_has_config_property(self):
        """ILifecyclePort has config property."""
        import inspect

        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "config")
        assert isinstance(inspect.getattr_static(ILifecyclePort, "config"), property)

    def test_has_started_at_ms_property(self):
        """ILifecyclePort has started_at_ms property."""
        import inspect

        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "started_at_ms")
        assert isinstance(inspect.getattr_static(ILifecyclePort, "started_at_ms"), property)

    def test_has_checkpoint_count_property(self):
        """ILifecyclePort has checkpoint_count property."""
        import inspect

        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "checkpoint_count")
        assert isinstance(inspect.getattr_static(ILifecyclePort, "checkpoint_count"), property)

    def test_has_last_checkpoint_ms_property(self):
        """ILifecyclePort has last_checkpoint_ms property."""
        import inspect

        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "last_checkpoint_ms")
        assert isinstance(inspect.getattr_static(ILifecyclePort, "last_checkpoint_ms"), property)

    def test_has_start_method(self):
        """ILifecyclePort has start method."""
        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "start")
        assert callable(getattr(ILifecyclePort, "start"))

    def test_has_stop_method(self):
        """ILifecyclePort has stop method."""
        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "stop")
        assert callable(getattr(ILifecyclePort, "stop"))

    def test_has_health_method(self):
        """ILifecyclePort has health method."""
        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "health")
        assert callable(getattr(ILifecyclePort, "health"))

    def test_has_checkpoint_method(self):
        """ILifecyclePort has checkpoint method."""
        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "checkpoint")
        assert callable(getattr(ILifecyclePort, "checkpoint"))

    def test_has_request_shutdown_method(self):
        """ILifecyclePort has request_shutdown method."""
        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "request_shutdown")
        assert callable(getattr(ILifecyclePort, "request_shutdown"))

    def test_has_is_running_method(self):
        """ILifecyclePort has is_running method."""
        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "is_running")
        assert callable(getattr(ILifecyclePort, "is_running"))

    def test_has_can_checkpoint_method(self):
        """ILifecyclePort has can_checkpoint method."""
        from k1.sessionstate.ports.lifecycle import ILifecyclePort

        assert hasattr(ILifecyclePort, "can_checkpoint")
        assert callable(getattr(ILifecyclePort, "can_checkpoint"))


# =============================================================================
# LIFECYCLE STATE TESTS
# =============================================================================


class TestLifecycleState:
    """Tests for LifecycleState enum."""

    def test_all_states_defined(self):
        """All lifecycle states are defined."""
        from k1.sessionstate.ports.lifecycle import LifecycleState

        assert LifecycleState.CREATED == "created"
        assert LifecycleState.STARTING == "starting"
        assert LifecycleState.RUNNING == "running"
        assert LifecycleState.STOPPING == "stopping"
        assert LifecycleState.STOPPED == "stopped"
        assert LifecycleState.ERROR == "error"

    def test_can_start_from_created(self):
        """Can start from CREATED state."""
        from k1.sessionstate.ports.lifecycle import LifecycleState

        assert LifecycleState.CREATED.can_start() is True
        assert LifecycleState.STOPPED.can_start() is True
        assert LifecycleState.RUNNING.can_start() is False
        assert LifecycleState.STARTING.can_start() is False
        assert LifecycleState.ERROR.can_start() is False

    def test_can_stop_from_running(self):
        """Can stop from RUNNING state."""
        from k1.sessionstate.ports.lifecycle import LifecycleState

        assert LifecycleState.RUNNING.can_stop() is True
        assert LifecycleState.CREATED.can_stop() is False
        assert LifecycleState.STOPPED.can_stop() is False
        assert LifecycleState.STOPPING.can_stop() is False

    def test_can_checkpoint_from_running(self):
        """Can checkpoint from RUNNING state."""
        from k1.sessionstate.ports.lifecycle import LifecycleState

        assert LifecycleState.RUNNING.can_checkpoint() is True
        assert LifecycleState.CREATED.can_checkpoint() is False
        assert LifecycleState.STOPPED.can_checkpoint() is False

    def test_is_operational(self):
        """Only RUNNING is operational."""
        from k1.sessionstate.ports.lifecycle import LifecycleState

        assert LifecycleState.RUNNING.is_operational() is True
        assert LifecycleState.CREATED.is_operational() is False
        assert LifecycleState.STOPPED.is_operational() is False
        assert LifecycleState.ERROR.is_operational() is False

    def test_is_terminal(self):
        """STOPPED and ERROR are terminal states."""
        from k1.sessionstate.ports.lifecycle import LifecycleState

        assert LifecycleState.STOPPED.is_terminal() is True
        assert LifecycleState.ERROR.is_terminal() is True
        assert LifecycleState.RUNNING.is_terminal() is False
        assert LifecycleState.CREATED.is_terminal() is False


# =============================================================================
# LIFECYCLE DATACLASS TESTS
# =============================================================================


class TestStartResult:
    """Tests for StartResult dataclass."""

    def test_create_success_fresh(self):
        """StartResult.success_fresh() factory works."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, RestoreSource, StartResult

        result = StartResult.success_fresh("session-123", 15.5)

        assert result.success is True
        assert result.state == LifecycleState.RUNNING
        assert result.session_id == "session-123"
        assert result.restored is False
        assert result.restore_source == RestoreSource.FRESH
        assert result.duration_ms == 15.5
        assert result.error is None

    def test_create_success_restored(self):
        """StartResult.success_restored() factory works."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, RestoreSource, StartResult

        result = StartResult.success_restored(
            "session-123",
            RestoreSource.LOCAL_COLD,
            ["control", "meta", "beliefs_active"],
            25.0,
        )

        assert result.success is True
        assert result.state == LifecycleState.RUNNING
        assert result.restored is True
        assert result.restore_source == RestoreSource.LOCAL_COLD
        assert len(result.sections_restored) == 3
        assert "control" in result.sections_restored

    def test_create_failure(self):
        """StartResult.failure() factory works."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, StartResult

        result = StartResult.failure("Initialization failed", 100.0)

        assert result.success is False
        assert result.state == LifecycleState.ERROR
        assert result.error == "Initialization failed"
        assert result.duration_ms == 100.0

    def test_to_dict(self):
        """StartResult.to_dict() serializes correctly."""
        from k1.sessionstate.ports.lifecycle import StartResult

        result = StartResult.success_fresh("session-123", 15.5)
        data = result.to_dict()

        assert data["success"] is True
        assert data["state"] == "running"
        assert data["session_id"] == "session-123"
        assert data["restore_source"] == "fresh"

    def test_from_dict(self):
        """StartResult.from_dict() deserializes correctly."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, RestoreSource, StartResult

        data = {
            "success": True,
            "state": "running",
            "session_id": "test-123",
            "restored": True,
            "restore_source": "local_cold",
            "sections_restored": ["control"],
            "duration_ms": 20.0,
        }

        result = StartResult.from_dict(data)

        assert result.success is True
        assert result.state == LifecycleState.RUNNING
        assert result.restore_source == RestoreSource.LOCAL_COLD


class TestStopResult:
    """Tests for StopResult dataclass."""

    def test_create_success_with_checkpoint(self):
        """StopResult.success_with_checkpoint() factory works."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, StopResult

        result = StopResult.success_with_checkpoint("ckpt-123", 1024, 30.0)

        assert result.success is True
        assert result.state == LifecycleState.STOPPED
        assert result.checkpoint_id == "ckpt-123"
        assert result.checkpoint_size_bytes == 1024
        assert result.duration_ms == 30.0

    def test_create_success_no_checkpoint(self):
        """StopResult.success_no_checkpoint() factory works."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, StopResult

        result = StopResult.success_no_checkpoint(10.0)

        assert result.success is True
        assert result.state == LifecycleState.STOPPED
        assert result.checkpoint_id is None

    def test_create_failure(self):
        """StopResult.failure() factory works."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, StopResult

        result = StopResult.failure("Shutdown timeout", 5000.0)

        assert result.success is False
        assert result.state == LifecycleState.ERROR
        assert result.error == "Shutdown timeout"

    def test_to_dict(self):
        """StopResult.to_dict() serializes correctly."""
        from k1.sessionstate.ports.lifecycle import StopResult

        result = StopResult.success_with_checkpoint("ckpt-123", 1024, 30.0)
        data = result.to_dict()

        assert data["success"] is True
        assert data["state"] == "stopped"
        assert data["checkpoint_id"] == "ckpt-123"
        assert data["checkpoint_size_bytes"] == 1024

    def test_from_dict(self):
        """StopResult.from_dict() deserializes correctly."""
        from k1.sessionstate.ports.lifecycle import LifecycleState, StopResult

        data = {
            "success": True,
            "state": "stopped",
            "checkpoint_id": "ckpt-456",
            "checkpoint_size_bytes": 2048,
            "duration_ms": 50.0,
        }

        result = StopResult.from_dict(data)

        assert result.success is True
        assert result.state == LifecycleState.STOPPED
        assert result.checkpoint_id == "ckpt-456"


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_create_healthy_running(self):
        """HealthStatus.healthy_running() factory works."""
        from k1.sessionstate.ports.lifecycle import HealthStatus, LifecycleState, PressureLevel

        status = HealthStatus.healthy_running(
            pressure=PressureLevel.NORMAL,
            hot_pct=50.0,
            warm_pct=30.0,
            total_bytes=40000,
            last_checkpoint_ms=1000000,
            checkpoint_count=5,
            uptime_ms=60000,
            turn_count=10,
            mutation_count=50,
        )

        assert status.healthy is True
        assert status.state == LifecycleState.RUNNING
        assert status.pressure_level == PressureLevel.NORMAL
        assert status.hot_utilization_pct == 50.0
        assert status.warm_utilization_pct == 30.0
        assert status.total_size_bytes == 40000
        assert status.checkpoint_count == 5
        assert status.turn_count == 10

    def test_create_unhealthy(self):
        """HealthStatus.unhealthy() factory works."""
        from k1.sessionstate.ports.lifecycle import HealthStatus, LifecycleState, PressureLevel

        status = HealthStatus.unhealthy(
            state=LifecycleState.ERROR,
            error="Memory corruption detected",
            pressure=PressureLevel.CRITICAL,
        )

        assert status.healthy is False
        assert status.state == LifecycleState.ERROR
        assert status.error == "Memory corruption detected"
        assert status.pressure_level == PressureLevel.CRITICAL

    def test_to_dict(self):
        """HealthStatus.to_dict() serializes correctly."""
        from k1.sessionstate.ports.lifecycle import HealthStatus, PressureLevel

        status = HealthStatus.healthy_running(
            pressure=PressureLevel.ELEVATED,
            hot_pct=75.0,
            warm_pct=60.0,
            total_bytes=65000,
            last_checkpoint_ms=1234567,
            checkpoint_count=10,
            uptime_ms=120000,
        )
        data = status.to_dict()

        assert data["healthy"] is True
        assert data["state"] == "running"
        assert data["pressure_level"] == "elevated"
        assert data["hot_utilization_pct"] == 75.0

    def test_from_dict(self):
        """HealthStatus.from_dict() deserializes correctly."""
        from k1.sessionstate.ports.lifecycle import HealthStatus, LifecycleState, PressureLevel

        data = {
            "healthy": True,
            "state": "running",
            "pressure_level": "normal",
            "hot_utilization_pct": 50.0,
            "warm_utilization_pct": 30.0,
            "total_size_bytes": 40000,
            "last_checkpoint_ms": 1000,
            "checkpoint_count": 3,
            "uptime_ms": 60000,
        }

        status = HealthStatus.from_dict(data)

        assert status.healthy is True
        assert status.state == LifecycleState.RUNNING
        assert status.pressure_level == PressureLevel.NORMAL


class TestCheckpointResult:
    """Tests for CheckpointResult dataclass."""

    def test_create_success_checkpoint(self):
        """CheckpointResult.success_checkpoint() factory works."""
        from k1.sessionstate.ports.lifecycle import CheckpointResult, CheckpointTrigger

        result = CheckpointResult.success_checkpoint(
            checkpoint_id="ckpt-123",
            trigger=CheckpointTrigger.MANUAL,
            size_bytes=45000,
            sections=["control", "meta", "beliefs_active"],
            duration_ms=30.0,
        )

        assert result.success is True
        assert result.checkpoint_id == "ckpt-123"
        assert result.trigger == CheckpointTrigger.MANUAL
        assert result.size_bytes == 45000
        assert len(result.sections_checkpointed) == 3
        assert result.sla_met is True  # 30ms < 50ms threshold

    def test_sla_violation_detected(self):
        """CheckpointResult detects SLA violations."""
        from k1.sessionstate.ports.lifecycle import CheckpointResult, CheckpointTrigger

        result = CheckpointResult.success_checkpoint(
            checkpoint_id="ckpt-slow",
            trigger=CheckpointTrigger.PERIODIC,
            size_bytes=90000,
            sections=["all"],
            duration_ms=75.0,  # > 50ms threshold
        )

        assert result.success is True
        assert result.sla_met is False

    def test_create_failure(self):
        """CheckpointResult.failure() factory works."""
        from k1.sessionstate.ports.lifecycle import CheckpointResult, CheckpointTrigger

        result = CheckpointResult.failure(
            error="Disk full",
            trigger=CheckpointTrigger.STOP,
            duration_ms=15.0,
        )

        assert result.success is False
        assert result.checkpoint_id == ""
        assert result.trigger == CheckpointTrigger.STOP
        assert result.error == "Disk full"
        assert result.sla_met is False

    def test_to_dict(self):
        """CheckpointResult.to_dict() serializes correctly."""
        from k1.sessionstate.ports.lifecycle import CheckpointResult, CheckpointTrigger

        result = CheckpointResult.success_checkpoint(
            checkpoint_id="ckpt-123",
            trigger=CheckpointTrigger.PERIODIC,
            size_bytes=45000,
            sections=["control"],
            duration_ms=25.0,
        )
        data = result.to_dict()

        assert data["success"] is True
        assert data["checkpoint_id"] == "ckpt-123"
        assert data["trigger"] == "periodic"
        assert data["sla_met"] is True

    def test_from_dict(self):
        """CheckpointResult.from_dict() deserializes correctly."""
        from k1.sessionstate.ports.lifecycle import CheckpointResult, CheckpointTrigger

        data = {
            "success": True,
            "checkpoint_id": "ckpt-456",
            "trigger": "manual",
            "size_bytes": 50000,
            "sections_checkpointed": ["control", "meta"],
            "duration_ms": 40.0,
            "sla_met": True,
        }

        result = CheckpointResult.from_dict(data)

        assert result.success is True
        assert result.checkpoint_id == "ckpt-456"
        assert result.trigger == CheckpointTrigger.MANUAL


class TestCheckpointTrigger:
    """Tests for CheckpointTrigger enum."""

    def test_all_triggers_defined(self):
        """All checkpoint triggers are defined."""
        from k1.sessionstate.ports.lifecycle import CheckpointTrigger

        assert CheckpointTrigger.PERIODIC == "periodic"
        assert CheckpointTrigger.MANUAL == "manual"
        assert CheckpointTrigger.STOP == "stop"
        assert CheckpointTrigger.PRESSURE == "pressure"
        assert CheckpointTrigger.EMERGENCY == "emergency"
        assert CheckpointTrigger.MIGRATION == "migration"
        assert CheckpointTrigger.EVICTION == "eviction"


class TestRestoreSource:
    """Tests for RestoreSource enum."""

    def test_all_sources_defined(self):
        """All restore sources are defined."""
        from k1.sessionstate.ports.lifecycle import RestoreSource

        assert RestoreSource.FRESH == "fresh"
        assert RestoreSource.LOCAL_COLD == "local_cold"
        assert RestoreSource.K0 == "k0"
        assert RestoreSource.CHECKPOINT == "checkpoint"


class TestPressureLevel:
    """Tests for PressureLevel enum."""

    def test_all_levels_defined(self):
        """All pressure levels are defined."""
        from k1.sessionstate.ports.lifecycle import PressureLevel

        assert PressureLevel.NORMAL == "normal"
        assert PressureLevel.ELEVATED == "elevated"
        assert PressureLevel.HIGH == "high"
        assert PressureLevel.CRITICAL == "critical"


class TestLifecycleConfig:
    """Tests for LifecycleConfig dataclass."""

    def test_default_config(self):
        """LifecycleConfig.default() has expected values."""
        from k1.sessionstate.ports.lifecycle import LifecycleConfig

        config = LifecycleConfig.default()

        assert config.checkpoint_interval_ms == 30000
        assert config.restore_on_start is True
        assert config.checkpoint_on_stop is True
        assert config.max_start_duration_ms == 5000
        assert config.max_stop_duration_ms == 5000

    def test_testing_config(self):
        """LifecycleConfig.testing() disables timers."""
        from k1.sessionstate.ports.lifecycle import LifecycleConfig

        config = LifecycleConfig.testing()

        assert config.checkpoint_interval_ms == 0
        assert config.restore_on_start is False
        assert config.health_check_interval_ms == 0

    def test_to_dict(self):
        """LifecycleConfig.to_dict() serializes correctly."""
        from k1.sessionstate.ports.lifecycle import LifecycleConfig

        config = LifecycleConfig.default()
        data = config.to_dict()

        assert data["checkpoint_interval_ms"] == 30000
        assert data["restore_on_start"] is True

    def test_from_dict(self):
        """LifecycleConfig.from_dict() deserializes correctly."""
        from k1.sessionstate.ports.lifecycle import LifecycleConfig

        data = {
            "checkpoint_interval_ms": 60000,
            "restore_on_start": False,
            "checkpoint_on_stop": True,
        }

        config = LifecycleConfig.from_dict(data)

        assert config.checkpoint_interval_ms == 60000
        assert config.restore_on_start is False


class TestInvalidStateError:
    """Tests for InvalidStateError exception."""

    def test_error_message_format(self):
        """InvalidStateError has correct message format."""
        from k1.sessionstate.ports.lifecycle import InvalidStateError, LifecycleState

        error = InvalidStateError(
            current_state=LifecycleState.STOPPED,
            operation="checkpoint",
            valid_states=[LifecycleState.RUNNING],
        )

        assert "checkpoint" in str(error)
        assert "stopped" in str(error)
        assert "running" in str(error)

    def test_error_attributes(self):
        """InvalidStateError has expected attributes."""
        from k1.sessionstate.ports.lifecycle import InvalidStateError, LifecycleState

        error = InvalidStateError(
            current_state=LifecycleState.CREATED,
            operation="stop",
            valid_states=[LifecycleState.RUNNING],
        )

        assert error.current_state == LifecycleState.CREATED
        assert error.operation == "stop"
        assert LifecycleState.RUNNING in error.valid_states


class TestMutationRequest:
    """Tests for MutationRequest dataclass."""

    def test_create_mutation_request(self):
        """MutationRequest can be created with all fields."""
        from k1.sessionstate.ports.writer import MutationPriority, MutationRequest

        request = MutationRequest(
            request_id="req-123",
            section="beliefs_active",
            operation="append",
            data={"fact": "test"},
            estimated_bytes=100,
            writer_id="concierge",
            cognitive_trace_id="trace-123",
        )

        assert request.request_id == "req-123"
        assert request.section == "beliefs_active"
        assert request.operation == "append"
        assert request.estimated_bytes == 100
        assert request.priority == MutationPriority.NORMAL

    def test_factory_create_method(self):
        """MutationRequest.create() factory works."""
        from k1.sessionstate.ports.writer import MutationPriority, MutationRequest

        request = MutationRequest.create(
            section="control",
            operation="update",
            data={"turn": 5},
            writer_id="test",
            cognitive_trace_id="trace-456",
            priority=MutationPriority.CRITICAL,
            delegated_from="sub_agent_1",
        )

        assert request.request_id is not None
        assert len(request.request_id) == 36  # UUID format
        assert request.section == "control"
        assert request.priority == MutationPriority.CRITICAL
        assert request.delegation_chain == ["sub_agent_1"]

    def test_to_dict_and_from_dict(self):
        """MutationRequest serialization roundtrip."""
        from k1.sessionstate.ports.writer import MutationPriority, MutationRequest

        original = MutationRequest.create(
            section="history_active",
            operation="append",
            data={"message": "Hello"},
            writer_id="concierge",
            cognitive_trace_id="trace-789",
            priority=MutationPriority.HIGH,
        )

        data = original.to_dict()
        restored = MutationRequest.from_dict(data)

        assert restored.request_id == original.request_id
        assert restored.section == original.section
        assert restored.priority == original.priority

    def test_is_expired(self):
        """MutationRequest.is_expired() detects expired requests."""
        import time

        from k1.sessionstate.ports.writer import MutationRequest

        # Non-expiring request
        request = MutationRequest.create(
            section="beliefs_active",
            operation="append",
            data={},
            writer_id="test",
            cognitive_trace_id="trace",
            estimated_bytes=0,
        )
        assert not request.is_expired()

        # Expired request (timeout in past)
        expired = MutationRequest(
            request_id="exp-123",
            section="beliefs_active",
            operation="append",
            data={},
            estimated_bytes=0,
            writer_id="test",
            cognitive_trace_id="trace",
            timeout_ms=1,
            created_at_ms=int(time.time() * 1000) - 1000,
        )
        assert expired.is_expired()


class TestMutationResponse:
    """Tests for MutationResponse dataclass."""

    def test_approved_factory(self):
        """MutationResponse.approved() factory works."""
        from k1.sessionstate.ports.writer import MutationResponse, MutationStatus

        response = MutationResponse.approved(
            request_id="req-123",
            section="beliefs_active",
            operation="append",
            new_size_bytes=1024,
            bytes_delta=100,
            available_bytes=47000,
            duration_ms=2.5,
        )

        assert response.approved is True
        assert response.status == MutationStatus.APPLIED
        assert response.new_size_bytes == 1024
        assert response.bytes_delta == 100

    def test_rejected_factory(self):
        """MutationResponse.rejected() factory works."""
        from k1.sessionstate.ports.writer import MutationResponse, MutationStatus, RejectionCategory

        response = MutationResponse.rejected(
            request_id="req-123",
            section="beliefs_active",
            operation="append",
            reason="Section capacity exceeded",
            category=RejectionCategory.CAPACITY,
            available_bytes=100,
        )

        assert response.approved is False
        assert response.status == MutationStatus.REJECTED
        assert response.reason == "Section capacity exceeded"
        assert response.rejection_category == RejectionCategory.CAPACITY

    def test_failed_factory(self):
        """MutationResponse.failed() factory works."""
        from k1.sessionstate.ports.writer import MutationResponse, MutationStatus

        response = MutationResponse.failed(
            request_id="req-123",
            section="beliefs_active",
            operation="append",
            error="Database connection error",
        )

        assert response.approved is False
        assert response.status == MutationStatus.FAILED
        assert response.error == "Database connection error"

    def test_cancelled_factory(self):
        """MutationResponse.cancelled() factory works."""
        from k1.sessionstate.ports.writer import MutationResponse, MutationStatus

        response = MutationResponse.cancelled("req-123", reason="User cancelled")

        assert response.approved is False
        assert response.status == MutationStatus.CANCELLED
        assert response.reason == "User cancelled"

    def test_to_dict_and_from_dict(self):
        """MutationResponse serialization roundtrip."""
        from k1.sessionstate.ports.writer import MutationResponse, RejectionCategory

        original = MutationResponse.rejected(
            request_id="req-456",
            section="control",
            operation="set",
            reason="Emergency mode",
            category=RejectionCategory.EMERGENCY,
        )

        data = original.to_dict()
        restored = MutationResponse.from_dict(data)

        assert restored.request_id == original.request_id
        assert restored.status == original.status
        assert restored.rejection_category == original.rejection_category


class TestBatchRequest:
    """Tests for BatchRequest dataclass."""

    def test_create_batch_request(self):
        """BatchRequest.create() factory works."""
        from k1.sessionstate.ports.writer import BatchRequest, MutationRequest

        requests = [
            MutationRequest.create(
                section="beliefs_active",
                operation="append",
                data={"fact": f"fact-{i}"},
                writer_id="test",
                cognitive_trace_id="trace-batch",
            )
            for i in range(3)
        ]

        batch = BatchRequest.create(
            requests=requests,
            writer_id="concierge",
            cognitive_trace_id="trace-batch",
            stop_on_rejection=True,
        )

        assert len(batch.batch_id) == 36  # UUID
        assert len(batch.requests) == 3
        assert batch.stop_on_rejection is True

    def test_to_dict_and_from_dict(self):
        """BatchRequest serialization roundtrip."""
        from k1.sessionstate.ports.writer import BatchRequest, MutationRequest

        requests = [
            MutationRequest.create(
                section="telemetry",
                operation="update",
                data={"tokens": 100},
                writer_id="test",
                cognitive_trace_id="trace",
            )
        ]
        original = BatchRequest.create(requests, "test", "trace")

        data = original.to_dict()
        restored = BatchRequest.from_dict(data)

        assert restored.batch_id == original.batch_id
        assert len(restored.requests) == 1


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_from_responses_factory(self):
        """BatchResult.from_responses() factory calculates correctly."""
        from k1.sessionstate.ports.writer import BatchResult, MutationResponse

        responses = [
            MutationResponse.approved("req-1", "beliefs_active", "append", 1000, 100, 47000),
            MutationResponse.approved("req-2", "history_active", "append", 2000, 200, 46800),
            MutationResponse.rejected(
                "req-3",
                "control",
                "set",
                "Locked",
                category=None,
            ),
        ]

        result = BatchResult.from_responses(
            batch_id="batch-123",
            responses=responses,
            duration_ms=15.5,
        )

        assert result.total_requests == 3
        assert result.applied_count == 2
        assert result.rejected_count == 1
        assert result.failed_count == 0
        assert result.total_bytes_delta == 300
        assert result.all_applied is False
        assert result.success_rate == 2 / 3

    def test_all_applied_property(self):
        """BatchResult.all_applied works correctly."""
        from k1.sessionstate.ports.writer import BatchResult, MutationResponse

        all_good = [MutationResponse.approved("r1", "s1", "op", 100, 10, 1000) for _ in range(5)]

        result = BatchResult.from_responses("batch", all_good)
        assert result.all_applied is True
        assert result.success_rate == 1.0


class TestWriterEnums:
    """Tests for writer port enums."""

    def test_mutation_priority_values(self):
        """MutationPriority has expected values."""
        from k1.sessionstate.ports.writer import MutationPriority

        assert MutationPriority.CRITICAL.value == "critical"
        assert MutationPriority.HIGH.value == "high"
        assert MutationPriority.NORMAL.value == "normal"
        assert MutationPriority.LOW.value == "low"
        assert MutationPriority.DEFERRED.value == "deferred"

    def test_mutation_status_values(self):
        """MutationStatus has expected values."""
        from k1.sessionstate.ports.writer import MutationStatus

        assert MutationStatus.PENDING.value == "pending"
        assert MutationStatus.APPLIED.value == "applied"
        assert MutationStatus.REJECTED.value == "rejected"
        assert MutationStatus.FAILED.value == "failed"
        assert MutationStatus.CANCELLED.value == "cancelled"

    def test_rejection_category_values(self):
        """RejectionCategory has expected values."""
        from k1.sessionstate.ports.writer import RejectionCategory

        assert RejectionCategory.CAPACITY.value == "capacity"
        assert RejectionCategory.AUTHORIZATION.value == "authorization"
        assert RejectionCategory.VALIDATION.value == "validation"
        assert RejectionCategory.LOCKED.value == "locked"
        assert RejectionCategory.EMERGENCY.value == "emergency"


class TestWriterAuthorization:
    """Tests for WriterAuthorization dataclass."""

    def test_authorization_creation(self):
        """WriterAuthorization can be created."""
        from k1.sessionstate.ports.writer import WriterAuthorization

        auth = WriterAuthorization(
            writer_id="concierge",
            authorized=True,
            permissions=["read", "write", "batch"],
        )

        assert auth.writer_id == "concierge"
        assert auth.authorized is True
        assert "write" in auth.permissions

    def test_authorization_to_dict(self):
        """WriterAuthorization serialization works."""
        from k1.sessionstate.ports.writer import WriterAuthorization

        auth = WriterAuthorization(
            writer_id="unknown",
            authorized=False,
            reason="Not a recognized writer",
        )

        data = auth.to_dict()
        assert data["writer_id"] == "unknown"
        assert data["authorized"] is False
        assert data["reason"] == "Not a recognized writer"

    def test_null_implements_interface(self):
        """NullSyncPort implements IK0SyncPort."""
        # TODO: Implement
        pass

    def test_sync_has_is_connected(self):
        """Sync adapters have is_connected property."""
        # TODO: Implement
        pass


# =============================================================================
# SQLITE STORAGE ADAPTER TESTS
# =============================================================================


class TestSQLiteStorageAdapter:
    """Tests for SQLiteStorageAdapter."""

    def test_creates_database_file(self, tmp_path: Path):
        """Adapter creates SQLite database file."""
        # TODO: Implement
        pass

    def test_archive_creates_record(self):
        """archive() creates record in database."""
        # TODO: Implement
        pass

    def test_restore_retrieves_record(self):
        """restore() retrieves archived record."""
        # TODO: Implement
        pass

    def test_list_archives_filters_by_session(self):
        """list_archives() filters by session_id."""
        # TODO: Implement
        pass

    def test_delete_removes_record(self):
        """delete() removes archive record."""
        # TODO: Implement
        pass

    def test_archive_large_data(self):
        """archive() handles large data (>1MB)."""
        # TODO: Implement
        pass

    def test_concurrent_access(self):
        """Concurrent access doesn't corrupt data."""
        # TODO: Implement with threading
        pass

    def test_wal_mode_enabled(self):
        """WAL mode is enabled for concurrency."""
        # TODO: Implement
        pass


# =============================================================================
# IN-MEMORY STORAGE ADAPTER TESTS
# =============================================================================


class TestInMemoryStorageAdapter:
    """Tests for InMemoryStorageAdapter."""

    def test_archive_stores_in_memory(self):
        """archive() stores in memory dict."""
        # TODO: Implement
        pass

    def test_clear_removes_all_data(self):
        """clear() removes all stored data."""
        # TODO: Implement
        pass

    def test_isolation_between_instances(self):
        """Different instances are isolated."""
        # TODO: Implement
        pass

    def test_storage_type_is_memory(self):
        """storage_type returns 'memory'."""
        # TODO: Implement
        pass


# =============================================================================
# LOCAL EVENT ADAPTER TESTS
# =============================================================================


class TestLocalEventAdapter:
    """Tests for LocalEventAdapter."""

    def test_emit_dispatches_to_subscribers(self):
        """emit() dispatches to registered subscribers."""
        import time

        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        received = []

        def handler(event):
            received.append(event)

        adapter.subscribe("test.event", handler)
        adapter.emit("test.event", {"key": "value"})

        # Wait for async dispatch
        time.sleep(0.1)

        assert len(received) == 1
        assert received[0] == {"key": "value"}
        adapter.stop()

    def test_subscribe_returns_subscription_id(self):
        """subscribe() returns subscription ID."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        sub_id = adapter.subscribe("test.event", lambda x: None)

        assert sub_id is not None
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0
        adapter.stop()

    def test_unsubscribe_removes_handler(self):
        """unsubscribe() removes handler."""
        import time

        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        received = []

        def handler(event):
            received.append(event)

        sub_id = adapter.subscribe("test.event", handler)
        success = adapter.unsubscribe(sub_id)

        assert success is True

        adapter.emit("test.event", {"key": "value"})
        time.sleep(0.1)

        assert len(received) == 0
        adapter.stop()

    def test_capture_mode_stores_events(self):
        """Capture mode stores emitted events."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("test.event", {"key": "value"})

        events = adapter.get_captured_events()

        assert len(events) == 1
        assert events[0][0] == "test.event"
        assert events[0][1] == {"key": "value"}
        adapter.stop()

    def test_drain_returns_and_clears(self):
        """drain() returns events and clears buffer."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("test.event", {"first": 1})
        adapter.emit("test.event", {"second": 2})

        drained = adapter.drain()

        assert len(drained) == 2
        assert adapter.get_captured_events() == []
        adapter.stop()

    def test_assert_emitted_helper(self):
        """assert_emitted() validates event count."""
        import pytest

        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("test.event", {"key": "value"})
        adapter.emit("test.event", {"key": "value2"})

        # Should not raise
        adapter.assert_emitted("test.event", count=2)

        # Should raise
        with pytest.raises(AssertionError):
            adapter.assert_emitted("test.event", count=1)

        adapter.stop()

    def test_is_connected_always_true(self):
        """is_connected property is always True for local adapter."""
        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        assert adapter.is_connected is True
        adapter.stop()

    def test_multiple_subscribers_same_event(self):
        """Multiple handlers receive same event."""
        import time

        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        received1 = []
        received2 = []

        adapter.subscribe("test.event", lambda x: received1.append(x))
        adapter.subscribe("test.event", lambda x: received2.append(x))

        adapter.emit("test.event", {"data": 123})
        time.sleep(0.1)

        assert len(received1) == 1
        assert len(received2) == 1
        adapter.stop()

    def test_handler_exception_isolated(self):
        """Handler exception doesn't affect other handlers."""
        import threading

        from k1.sessionstate.adapters.local_events import LocalEventAdapter

        adapter = LocalEventAdapter()
        received = []
        event_processed = threading.Event()

        def bad_handler(event):
            raise ValueError("Intentional error")

        def good_handler(event):
            received.append(event)
            event_processed.set()

        adapter.subscribe("test.event", bad_handler)
        adapter.subscribe("test.event", good_handler)

        adapter.emit("test.event", {"data": 123})

        # Wait for event processing with timeout
        event_processed.wait(timeout=1.0)

        # Good handler still receives event
        assert len(received) == 1
        adapter.stop()


# =============================================================================
# DIRECT WRITER ADAPTER TESTS
# =============================================================================


class MockApproval:
    """Mock Approval result from MutationGuard."""

    def __init__(
        self,
        approved: bool = True,
        reason: str = "",
        reason_code: str = "",
        total_available_bytes: int = 10000,
    ):
        self.approved = approved
        self.reason = reason
        self.reason_code = reason_code
        self.total_available_bytes = total_available_bytes


class MockMutationResult:
    """Mock MutationResult from SessionStateManager."""

    def __init__(
        self,
        success: bool = True,
        new_size_bytes: int = 1000,
        bytes_delta: int = 100,
        available_bytes: int = 9000,
        reason: str = "",
        error: str = "",
    ):
        self.success = success
        self.new_size_bytes = new_size_bytes
        self.bytes_delta = bytes_delta
        self.available_bytes = available_bytes
        self.reason = reason
        self.error = error


class MockMutationGuard:
    """Mock MutationGuard for testing."""

    def __init__(self, approve: bool = True, reason: str = ""):
        self._approve = approve
        self._reason = reason
        self.preflight_calls = []

    def preflight(self, section: str, operation: str, estimated_bytes: int):
        self.preflight_calls.append((section, operation, estimated_bytes))
        return MockApproval(
            approved=self._approve,
            reason=self._reason,
            reason_code="capacity_exceeded" if not self._approve else "",
        )


class MockSessionStateManager:
    """Mock SessionStateManager for testing."""

    def __init__(self, success: bool = True, error: str = ""):
        self._success = success
        self._error = error
        self.mutate_calls = []
        self.session_id = "test-session"

    def mutate(self, section: str, operation: str, data, estimated_bytes: int = None):
        self.mutate_calls.append((section, operation, data, estimated_bytes))
        if self._error:
            raise RuntimeError(self._error)
        return MockMutationResult(success=self._success)


class TestDirectWriterAdapter:
    """Tests for DirectWriterAdapter."""

    def test_request_mutation_applies_directly(self):
        """request_mutation() applies mutations via manager."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import MutationRequest

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        request = MutationRequest.create(
            section="beliefs_active",
            operation="append",
            data={"fact": "test"},
            writer_id="test",
            cognitive_trace_id="trace-123",
            estimated_bytes=100,
        )

        response = adapter.request_mutation(request)

        assert response.approved is True
        assert len(guard.preflight_calls) == 1
        assert len(manager.mutate_calls) == 1
        assert manager.mutate_calls[0][0] == "beliefs_active"

    def test_writer_id_is_direct(self):
        """writer_id returns configured ID."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard, writer_id="custom")

        assert adapter.writer_id == "custom"

    def test_default_writer_id_is_direct(self):
        """Default writer_id is 'direct'."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        assert adapter.writer_id == "direct"

    def test_is_connected_always_true(self):
        """is_connected is always True for direct adapter."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        assert adapter.is_connected is True

    def test_batch_mutations_processes_all(self):
        """batch_mutations() processes all requests."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import BatchRequest, MutationRequest

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        requests = [
            MutationRequest.create(
                section="beliefs_active",
                operation="append",
                data={"fact": f"test{i}"},
                writer_id="test",
                cognitive_trace_id="trace-123",
                estimated_bytes=100,
            )
            for i in range(3)
        ]

        batch = BatchRequest.create(
            requests=requests,
            writer_id="test",
            cognitive_trace_id="trace-123",
        )

        result = adapter.batch_mutations(batch)

        assert result.total_requests == 3
        assert result.applied_count == 3
        assert result.rejected_count == 0
        assert len(result.responses) == 3

    def test_batch_stop_on_rejection(self):
        """batch_mutations() stops on first rejection if configured."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import BatchRequest, MutationRequest

        manager = MockSessionStateManager()
        guard = MockMutationGuard(approve=False, reason="No capacity")
        adapter = DirectWriterAdapter(manager, guard)

        requests = [
            MutationRequest.create(
                section="beliefs_active",
                operation="append",
                data={"fact": f"test{i}"},
                writer_id="test",
                cognitive_trace_id="trace-123",
            )
            for i in range(3)
        ]

        batch = BatchRequest.create(
            requests=requests,
            writer_id="test",
            cognitive_trace_id="trace-123",
            stop_on_rejection=True,
        )

        result = adapter.batch_mutations(batch)

        assert result.total_requests == 3
        assert result.rejected_count == 1
        assert result.cancelled_count == 2
        assert result.stopped_early is True

    def test_validate_writer_all_authorized_by_default(self):
        """validate_writer() authorizes all writers by default."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        auth = adapter.validate_writer("any_writer")

        assert auth.authorized is True
        assert "write" in auth.permissions

    def test_validate_writer_with_restrictions(self):
        """validate_writer() enforces restrictions when configured."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard, authorized_writers={"concierge", "test"})

        # Authorized
        auth1 = adapter.validate_writer("concierge")
        assert auth1.authorized is True

        # Not authorized
        auth2 = adapter.validate_writer("unknown")
        assert auth2.authorized is False
        assert "unknown" in auth2.reason

    def test_preflight_rejection_returns_rejection_response(self):
        """Preflight rejection returns proper rejection response."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import MutationRequest, RejectionCategory

        manager = MockSessionStateManager()
        guard = MockMutationGuard(approve=False, reason="Section over budget")
        adapter = DirectWriterAdapter(manager, guard)

        request = MutationRequest.create(
            section="beliefs_active",
            operation="append",
            data={"fact": "test"},
            writer_id="test",
            cognitive_trace_id="trace-123",
        )

        response = adapter.request_mutation(request)

        assert response.approved is False
        assert "budget" in response.reason.lower()
        assert response.rejection_category == RejectionCategory.CAPACITY

    def test_manager_exception_returns_failed_response(self):
        """Manager exception returns failed response."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import MutationRequest, MutationStatus

        manager = MockSessionStateManager(error="Database error")
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        request = MutationRequest.create(
            section="beliefs_active",
            operation="append",
            data={"fact": "test"},
            writer_id="test",
            cognitive_trace_id="trace-123",
        )

        response = adapter.request_mutation(request)

        assert response.approved is False
        assert response.status == MutationStatus.FAILED
        assert "Database error" in response.error

    def test_get_stats_returns_statistics(self):
        """get_stats() returns correct statistics."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import MutationRequest

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        # Make some requests
        for i in range(3):
            request = MutationRequest.create(
                section="beliefs_active",
                operation="append",
                data={"fact": f"test{i}"},
                writer_id="test",
                cognitive_trace_id="trace-123",
            )
            adapter.request_mutation(request)

        stats = adapter.get_stats()

        assert stats["total_requests"] == 3
        assert stats["applied_count"] == 3
        assert stats["rejected_count"] == 0
        assert stats["pending_count"] == 0

    def test_reset_stats_clears_counters(self):
        """reset_stats() clears all counters."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import MutationRequest

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        # Make a request
        request = MutationRequest.create(
            section="beliefs_active",
            operation="append",
            data={"fact": "test"},
            writer_id="test",
            cognitive_trace_id="trace-123",
        )
        adapter.request_mutation(request)

        assert adapter.get_stats()["total_requests"] == 1

        adapter.reset_stats()

        assert adapter.get_stats()["total_requests"] == 0

    def test_implements_iwriterport(self):
        """DirectWriterAdapter implements IWriterPort."""
        from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
        from k1.sessionstate.ports.writer import IWriterPort

        manager = MockSessionStateManager()
        guard = MockMutationGuard()
        adapter = DirectWriterAdapter(manager, guard)

        assert isinstance(adapter, IWriterPort)


# =============================================================================
# STANDALONE LIFECYCLE TESTS
# =============================================================================


class MockLifecycleManager:
    """Mock SessionStateManager for lifecycle testing."""

    def __init__(
        self,
        session_id: str = "test-session-123",
        start_success: bool = True,
        checkpoint_success: bool = True,
        restored: bool = False,
        restore_source: str = "local_cold",
    ):
        self.session_id = session_id
        self._start_success = start_success
        self._checkpoint_success = checkpoint_success
        self._restored = restored
        self._restore_source = restore_source
        self._mutation_count = 0
        self._is_running = False
        self.start_calls = []
        self.stop_calls = []
        self.checkpoint_calls = []

        # Mock size_tracker
        self.size_tracker = MockSizeTracker()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, restore_if_exists: bool = True):
        self.start_calls.append(restore_if_exists)
        self._is_running = True
        return MockStartResult(
            success=self._start_success,
            restored=self._restored and restore_if_exists,
            restore_source=self._restore_source,
        )

    def stop(self, checkpoint_before_stop: bool = True):
        self.stop_calls.append(checkpoint_before_stop)
        self._is_running = False
        return MockStopResult(success=True)

    def checkpoint(self):
        self.checkpoint_calls.append(True)
        return MockCheckpointResult(
            success=self._checkpoint_success,
            checkpoint_id="chk-" + str(len(self.checkpoint_calls)),
            size_bytes=1024,
            sla_met=True,
        )


class MockSizeTracker:
    """Mock size tracker for health tests."""

    def get_snapshot(self):
        return MockSizeSnapshot()


class MockSizeSnapshot:
    """Mock size snapshot."""

    def __init__(self):
        from k1.sessionstate.ports.lifecycle import PressureLevel

        self.overall_pressure = PressureLevel.NORMAL
        self.hot_utilization_pct = 0.5
        self.warm_utilization_pct = 0.3
        self.total_bytes = 1024


class MockStartResult:
    """Mock start result."""

    def __init__(
        self,
        success: bool = True,
        restored: bool = False,
        restore_source: str = "local_cold",
        error: str = "",
    ):
        self.success = success
        self.restored = restored
        self.restore_source = restore_source
        self.error = error


class MockStopResult:
    """Mock stop result."""

    def __init__(self, success: bool = True):
        self.success = success


class MockCheckpointResult:
    """Mock checkpoint result."""

    def __init__(
        self,
        success: bool = True,
        checkpoint_id: str = "chk-1",
        size_bytes: int = 1024,
        sla_met: bool = True,
        error: str = "",
    ):
        self.success = success
        self.checkpoint_id = checkpoint_id
        self.size_bytes = size_bytes
        self.sla_met = sla_met
        self.error = error


class TestStandaloneLifecycle:
    """Tests for StandaloneLifecycle."""

    def test_initial_state_is_created(self):
        """Initial state is CREATED."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager)

        assert lifecycle.state == LifecycleState.CREATED

    def test_start_transitions_to_running(self):
        """start() transitions to RUNNING."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)  # Disable timer

        result = lifecycle.start()

        assert result.success is True
        assert lifecycle.state == LifecycleState.RUNNING
        assert len(manager.start_calls) == 1
        lifecycle.stop()

    def test_stop_transitions_to_stopped(self):
        """stop() transitions to STOPPED."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        result = lifecycle.stop()

        assert result.success is True
        assert lifecycle.state == LifecycleState.STOPPED
        assert len(manager.stop_calls) == 1

    def test_checkpoint_returns_result(self):
        """checkpoint() returns CheckpointResult."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import CheckpointTrigger

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        result = lifecycle.checkpoint(CheckpointTrigger.MANUAL)

        assert result.success is True
        assert result.checkpoint_id is not None
        assert lifecycle.checkpoint_count == 1
        lifecycle.stop()

    def test_health_returns_status(self):
        """health() returns HealthStatus."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        health = lifecycle.health()

        assert health.healthy is True
        assert health.state == LifecycleState.RUNNING
        lifecycle.stop()

    def test_restart_after_stop(self):
        """Can restart after stop."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        # First start/stop
        lifecycle.start()
        lifecycle.stop()
        assert lifecycle.state == LifecycleState.STOPPED

        # Reset and restart
        lifecycle.reset()
        result = lifecycle.start()

        assert result.success is True
        assert lifecycle.state == LifecycleState.RUNNING
        lifecycle.stop()

    def test_start_fails_from_running(self):
        """Cannot start from RUNNING state."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        result = lifecycle.start()  # Try to start again

        assert result.success is False
        assert "Cannot start from state" in result.error
        lifecycle.stop()

    def test_checkpoint_fails_when_not_running(self):
        """checkpoint() fails when not in RUNNING state."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import CheckpointTrigger

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        result = lifecycle.checkpoint(CheckpointTrigger.MANUAL)

        assert result.success is False
        assert "Cannot checkpoint in state" in result.error

    def test_session_id_from_manager(self):
        """session_id comes from manager."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager(session_id="custom-session")
        lifecycle = StandaloneLifecycle(manager)

        assert lifecycle.session_id == "custom-session"

    def test_config_defaults(self):
        """Default config values are set."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager)

        assert lifecycle.config is not None
        assert lifecycle.config.checkpoint_interval_ms == 30000  # 30s default

    def test_config_override_interval(self):
        """checkpoint_interval_s overrides config."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=60)

        assert lifecycle.config.checkpoint_interval_ms == 60000

    def test_context_manager(self):
        """Context manager starts and stops lifecycle."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()

        with StandaloneLifecycle(manager, checkpoint_interval_s=0) as lifecycle:
            assert lifecycle.state == LifecycleState.RUNNING

        # After exiting context, should be stopped
        assert lifecycle.state == LifecycleState.STOPPED

    def test_force_error(self):
        """force_error() transitions to ERROR state."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        lifecycle.force_error("Test error")

        assert lifecycle.state == LifecycleState.ERROR

    def test_health_shows_unhealthy_on_error(self):
        """health() shows unhealthy when in ERROR state."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        lifecycle.force_error("Test error")
        health = lifecycle.health()

        assert health.healthy is False
        assert health.error == "Test error"

    def test_stop_with_checkpoint(self):
        """stop() performs checkpoint by default."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        result = lifecycle.stop()

        assert result.success is True
        assert result.checkpoint_id is not None
        assert len(manager.checkpoint_calls) == 1

    def test_stop_without_checkpoint(self):
        """stop(checkpoint_before_stop=False) skips checkpoint."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        result = lifecycle.stop(checkpoint_before_stop=False)

        assert result.success is True
        assert result.checkpoint_id is None
        assert len(manager.checkpoint_calls) == 0

    def test_uptime_ms_after_start(self):
        """started_at_ms is set after start."""
        import time

        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        before_start = int(time.time() * 1000)
        lifecycle.start()
        after_start = int(time.time() * 1000)

        assert lifecycle.started_at_ms >= before_start
        assert lifecycle.started_at_ms <= after_start
        lifecycle.stop()

    def test_checkpoint_count_increments(self):
        """checkpoint_count increments with each checkpoint."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import CheckpointTrigger

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        assert lifecycle.checkpoint_count == 0

        lifecycle.checkpoint(CheckpointTrigger.MANUAL)
        assert lifecycle.checkpoint_count == 1

        lifecycle.checkpoint(CheckpointTrigger.MANUAL)
        assert lifecycle.checkpoint_count == 2

        lifecycle.stop()

    def test_last_checkpoint_ms_updated(self):
        """last_checkpoint_ms is updated after checkpoint."""
        import time

        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import CheckpointTrigger

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        assert lifecycle.last_checkpoint_ms == 0

        before_checkpoint = int(time.time() * 1000)
        lifecycle.checkpoint(CheckpointTrigger.MANUAL)
        after_checkpoint = int(time.time() * 1000)

        assert lifecycle.last_checkpoint_ms >= before_checkpoint
        assert lifecycle.last_checkpoint_ms <= after_checkpoint
        lifecycle.stop()

    def test_start_failure_from_manager(self):
        """Start failure from manager is reported."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager(start_success=False)
        manager._start_success = False

        # Override start to return failure
        def failing_start(restore_if_exists=True):
            return MockStartResult(success=False, error="Manager failed")

        manager.start = failing_start
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        result = lifecycle.start()

        assert result.success is False
        assert "Manager failed" in result.error
        assert lifecycle.state == LifecycleState.ERROR

    def test_reset_from_stopped(self):
        """reset() works from STOPPED state."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        lifecycle.stop()
        lifecycle.reset()

        assert lifecycle.state == LifecycleState.CREATED
        assert lifecycle.started_at_ms == 0
        assert lifecycle.checkpoint_count == 0

    def test_reset_from_error(self):
        """reset() works from ERROR state."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import LifecycleState

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()
        lifecycle.force_error("Test error")
        lifecycle.reset()

        assert lifecycle.state == LifecycleState.CREATED

    def test_reset_fails_from_running(self):
        """reset() fails from RUNNING state."""
        from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
        from k1.sessionstate.ports.lifecycle import InvalidStateError

        manager = MockLifecycleManager()
        lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=0)

        lifecycle.start()

        import pytest

        with pytest.raises(InvalidStateError):
            lifecycle.reset()

        lifecycle.stop()


# =============================================================================
# NULL SYNC PORT TESTS
# =============================================================================


class TestNullSyncPort:
    """Tests for NullSyncPort (no-op K0 sync)."""

    def test_is_connected_always_false(self):
        """is_connected is always False."""
        # TODO: Implement
        pass

    def test_sync_checkpoint_is_noop(self):
        """sync_checkpoint() does nothing."""
        # TODO: Implement
        pass

    def test_sync_status_is_offline(self):
        """sync_status is OFFLINE."""
        # TODO: Implement
        pass

    def test_sync_status_is_offline(self):
        """sync_status is OFFLINE."""
        # TODO: Implement
        pass
        # TODO: Implement
        pass
        # TODO: Implement
        pass
        # TODO: Implement
        pass


class TestNullSyncPort:
    """Tests for NullSyncPort (no-op K0 sync)."""

    def test_is_connected_always_false(self):
        """is_connected is always False."""
        # TODO: Implement
        pass

    def test_sync_checkpoint_is_noop(self):
        """sync_checkpoint() does nothing."""
        # TODO: Implement
        pass

    def test_sync_status_is_offline(self):
        """sync_status is OFFLINE."""
        # TODO: Implement
        pass

    def test_sync_status_is_offline(self):
        """sync_status is OFFLINE."""
        # TODO: Implement
        pass
        # TODO: Implement
        pass
        # TODO: Implement
        pass
        # TODO: Implement
        pass
