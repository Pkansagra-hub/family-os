"""
ILifecyclePort - Lifecycle Management Interface
================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.4 Define Lifecycle Port
ISSUE: 3.4.1

ADRs:
- ADR-0017: SessionState 6-Section Design
- ADR-0018: 3-Tier Eviction Strategy

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Define the interface for SessionState lifecycle management.
    Allows SessionState to be managed by Fabric (future) or standalone.

STATE MACHINE:
    CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
                               |
                               v
                            ERROR

    Valid transitions:
    - CREATED -> STARTING (on start())
    - STARTING -> RUNNING (on successful init)
    - STARTING -> ERROR (on init failure)
    - RUNNING -> STOPPING (on stop())
    - STOPPING -> STOPPED (on successful cleanup)
    - STOPPING -> ERROR (on cleanup failure)
    - STOPPED -> STARTING (on restart)
    - Any -> ERROR (on unrecoverable failure)

CHECKPOINT TRIGGERS:
    - PERIODIC: Timer-based (e.g., every 30s)
    - MANUAL: Explicit checkpoint() call
    - STOP: Final checkpoint before stop
    - PRESSURE: Memory pressure triggers checkpoint + eviction
    - EMERGENCY: Emergency mode checkpoint

IMPLEMENTATIONS:
    - StandaloneLifecycle: Self-managed (standalone mode)
    - FabricLifecycle: Fabric integration (future)

==============================================================================
INTERFACE: ILifecyclePort
==============================================================================
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# =============================================================================
# ENUMS
# =============================================================================


class LifecycleState(str, Enum):
    """
    SessionState lifecycle states.

    Represents the current operational state of SessionState.
    State transitions are controlled by ILifecyclePort implementation.
    """

    CREATED = "created"  # Initialized but not started
    STARTING = "starting"  # Start in progress (init, restore)
    RUNNING = "running"  # Normal operation
    STOPPING = "stopping"  # Stop in progress (checkpoint, cleanup)
    STOPPED = "stopped"  # Fully stopped, resources released
    ERROR = "error"  # Error state, requires intervention

    def can_start(self) -> bool:
        """Check if start() is valid from this state."""
        return self in (LifecycleState.CREATED, LifecycleState.STOPPED)

    def can_stop(self) -> bool:
        """Check if stop() is valid from this state."""
        return self == LifecycleState.RUNNING

    def can_checkpoint(self) -> bool:
        """
        Check if checkpoint() is valid from this state.

        Returns True for RUNNING and STOPPING (final checkpoint).
        """
        return self in (LifecycleState.RUNNING, LifecycleState.STOPPING)

    def is_operational(self) -> bool:
        """Check if SessionState is operational."""
        return self == LifecycleState.RUNNING

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (LifecycleState.STOPPED, LifecycleState.ERROR)


class CheckpointTrigger(str, Enum):
    """
    Reason for checkpoint operation.

    Used for logging, metrics, and potentially different checkpoint strategies.
    """

    PERIODIC = "periodic"  # Timer-based checkpoint
    MANUAL = "manual"  # Explicit checkpoint() call
    STOP = "stop"  # Final checkpoint before stop
    PRESSURE = "pressure"  # Memory pressure triggered
    EMERGENCY = "emergency"  # Emergency mode checkpoint
    MIGRATION = "migration"  # Before tier migration
    EVICTION = "eviction"  # Before eviction to LOCAL COLD


class RestoreSource(str, Enum):
    """
    Source of session restoration.

    Indicates where the restored data came from.
    """

    FRESH = "fresh"  # No restore, fresh session
    LOCAL_COLD = "local_cold"  # Restored from K1 SQLite
    K0 = "k0"  # Restored from K0 cloud (future)
    CHECKPOINT = "checkpoint"  # Restored from specific checkpoint


class PressureLevel(str, Enum):
    """
    Memory pressure levels for health reporting.

    Maps to SizeTracker.PressureLevel but as string for portability.
    """

    NORMAL = "normal"  # < 70% utilization
    ELEVATED = "elevated"  # 70-85% utilization
    HIGH = "high"  # 85-95% utilization
    CRITICAL = "critical"  # > 95% utilization


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class StartResult:
    """
    Result of start operation.

    Attributes:
        success: Whether start succeeded
        state: Final state after operation
        session_id: Session that was started
        restored: Whether session was restored from storage
        restore_source: Where data was restored from
        sections_restored: List of sections that were restored
        duration_ms: Time taken to start
        error: Error message if failed
    """

    success: bool
    state: LifecycleState
    session_id: str = ""
    restored: bool = False
    restore_source: RestoreSource = RestoreSource.FRESH
    sections_restored: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "state": self.state.value,
            "session_id": self.session_id,
            "restored": self.restored,
            "restore_source": self.restore_source.value,
            "sections_restored": self.sections_restored,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StartResult:
        """Create from dictionary."""
        return cls(
            success=data["success"],
            state=LifecycleState(data["state"]),
            session_id=data.get("session_id", ""),
            restored=data.get("restored", False),
            restore_source=RestoreSource(data.get("restore_source", "fresh")),
            sections_restored=data.get("sections_restored", []),
            duration_ms=data.get("duration_ms", 0.0),
            error=data.get("error"),
        )

    @classmethod
    def success_fresh(
        cls,
        session_id: str,
        duration_ms: float,
    ) -> StartResult:
        """Create a successful fresh start result."""
        return cls(
            success=True,
            state=LifecycleState.RUNNING,
            session_id=session_id,
            restored=False,
            restore_source=RestoreSource.FRESH,
            duration_ms=duration_ms,
        )

    @classmethod
    def success_restored(
        cls,
        session_id: str,
        source: RestoreSource,
        sections: List[str],
        duration_ms: float,
    ) -> StartResult:
        """Create a successful restored start result."""
        return cls(
            success=True,
            state=LifecycleState.RUNNING,
            session_id=session_id,
            restored=True,
            restore_source=source,
            sections_restored=sections,
            duration_ms=duration_ms,
        )

    @classmethod
    def failure(
        cls,
        error: str,
        duration_ms: float = 0.0,
    ) -> StartResult:
        """Create a failed start result."""
        return cls(
            success=False,
            state=LifecycleState.ERROR,
            error=error,
            duration_ms=duration_ms,
        )


@dataclass
class StopResult:
    """
    Result of stop operation.

    Attributes:
        success: Whether stop succeeded
        state: Final state after operation
        checkpoint_id: ID of final checkpoint (if any)
        checkpoint_size_bytes: Size of final checkpoint
        duration_ms: Time taken to stop
        error: Error message if failed
    """

    success: bool
    state: LifecycleState
    checkpoint_id: Optional[str] = None
    checkpoint_size_bytes: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "state": self.state.value,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_size_bytes": self.checkpoint_size_bytes,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StopResult:
        """Create from dictionary."""
        return cls(
            success=data["success"],
            state=LifecycleState(data["state"]),
            checkpoint_id=data.get("checkpoint_id"),
            checkpoint_size_bytes=data.get("checkpoint_size_bytes", 0),
            duration_ms=data.get("duration_ms", 0.0),
            error=data.get("error"),
        )

    @classmethod
    def success_with_checkpoint(
        cls,
        checkpoint_id: str,
        size_bytes: int,
        duration_ms: float,
    ) -> StopResult:
        """Create a successful stop with checkpoint."""
        return cls(
            success=True,
            state=LifecycleState.STOPPED,
            checkpoint_id=checkpoint_id,
            checkpoint_size_bytes=size_bytes,
            duration_ms=duration_ms,
        )

    @classmethod
    def success_no_checkpoint(
        cls,
        duration_ms: float,
    ) -> StopResult:
        """Create a successful stop without checkpoint."""
        return cls(
            success=True,
            state=LifecycleState.STOPPED,
            duration_ms=duration_ms,
        )

    @classmethod
    def failure(
        cls,
        error: str,
        duration_ms: float = 0.0,
    ) -> StopResult:
        """Create a failed stop result."""
        return cls(
            success=False,
            state=LifecycleState.ERROR,
            error=error,
            duration_ms=duration_ms,
        )


@dataclass
class HealthStatus:
    """
    Health status of SessionState.

    Used by:
    - Fabric health checks
    - CLI status command
    - Monitoring systems

    Attributes:
        healthy: Overall health (True if RUNNING and pressure < CRITICAL)
        state: Current lifecycle state
        pressure_level: Memory pressure level
        hot_utilization_pct: HOT tier utilization percentage
        warm_utilization_pct: WARM tier utilization percentage
        total_size_bytes: Total bytes used across tiers
        last_checkpoint_ms: Timestamp of last checkpoint (0 if none)
        checkpoint_count: Total checkpoints since start
        uptime_ms: Time since start (0 if not running)
        turn_count: Turns processed since start
        mutation_count: Mutations applied since start
        error: Error message if in ERROR state
    """

    healthy: bool
    state: LifecycleState
    pressure_level: PressureLevel
    hot_utilization_pct: float = 0.0
    warm_utilization_pct: float = 0.0
    total_size_bytes: int = 0
    last_checkpoint_ms: int = 0
    checkpoint_count: int = 0
    uptime_ms: int = 0
    turn_count: int = 0
    mutation_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "healthy": self.healthy,
            "state": self.state.value,
            "pressure_level": self.pressure_level.value,
            "hot_utilization_pct": round(self.hot_utilization_pct, 4),
            "warm_utilization_pct": round(self.warm_utilization_pct, 4),
            "total_size_bytes": self.total_size_bytes,
            "last_checkpoint_ms": self.last_checkpoint_ms,
            "checkpoint_count": self.checkpoint_count,
            "uptime_ms": self.uptime_ms,
            "turn_count": self.turn_count,
            "mutation_count": self.mutation_count,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HealthStatus:
        """Create from dictionary."""
        return cls(
            healthy=data["healthy"],
            state=LifecycleState(data["state"]),
            pressure_level=PressureLevel(data["pressure_level"]),
            hot_utilization_pct=data.get("hot_utilization_pct", 0.0),
            warm_utilization_pct=data.get("warm_utilization_pct", 0.0),
            total_size_bytes=data.get("total_size_bytes", 0),
            last_checkpoint_ms=data.get("last_checkpoint_ms", 0),
            checkpoint_count=data.get("checkpoint_count", 0),
            uptime_ms=data.get("uptime_ms", 0),
            turn_count=data.get("turn_count", 0),
            mutation_count=data.get("mutation_count", 0),
            error=data.get("error"),
        )

    @classmethod
    def healthy_running(
        cls,
        pressure: PressureLevel,
        hot_pct: float,
        warm_pct: float,
        total_bytes: int,
        last_checkpoint_ms: int,
        checkpoint_count: int,
        uptime_ms: int,
        turn_count: int = 0,
        mutation_count: int = 0,
    ) -> HealthStatus:
        """Create a healthy running status."""
        return cls(
            healthy=True,
            state=LifecycleState.RUNNING,
            pressure_level=pressure,
            hot_utilization_pct=hot_pct,
            warm_utilization_pct=warm_pct,
            total_size_bytes=total_bytes,
            last_checkpoint_ms=last_checkpoint_ms,
            checkpoint_count=checkpoint_count,
            uptime_ms=uptime_ms,
            turn_count=turn_count,
            mutation_count=mutation_count,
        )

    @classmethod
    def unhealthy(
        cls,
        state: LifecycleState,
        error: str,
        pressure: PressureLevel = PressureLevel.NORMAL,
    ) -> HealthStatus:
        """Create an unhealthy status."""
        return cls(
            healthy=False,
            state=state,
            pressure_level=pressure,
            error=error,
        )


@dataclass
class CheckpointResult:
    """
    Result of checkpoint operation.

    Attributes:
        success: Whether checkpoint succeeded
        checkpoint_id: Unique checkpoint identifier
        trigger: What triggered this checkpoint
        size_bytes: Total bytes checkpointed
        sections_checkpointed: List of sections included
        duration_ms: Time taken
        sla_met: Whether <50ms SLA was met
        error: Error message if failed
    """

    success: bool
    checkpoint_id: str
    trigger: CheckpointTrigger = CheckpointTrigger.MANUAL
    size_bytes: int = 0
    sections_checkpointed: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    sla_met: bool = True
    error: Optional[str] = None

    # SLA threshold in milliseconds
    SLA_THRESHOLD_MS: float = 50.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "checkpoint_id": self.checkpoint_id,
            "trigger": self.trigger.value,
            "size_bytes": self.size_bytes,
            "sections_checkpointed": self.sections_checkpointed,
            "duration_ms": round(self.duration_ms, 3),
            "sla_met": self.sla_met,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CheckpointResult:
        """Create from dictionary."""
        return cls(
            success=data["success"],
            checkpoint_id=data.get("checkpoint_id", ""),
            trigger=CheckpointTrigger(data.get("trigger", "manual")),
            size_bytes=data.get("size_bytes", 0),
            sections_checkpointed=data.get("sections_checkpointed", []),
            duration_ms=data.get("duration_ms", 0.0),
            sla_met=data.get("sla_met", True),
            error=data.get("error"),
        )

    @classmethod
    def success_checkpoint(
        cls,
        checkpoint_id: str,
        trigger: CheckpointTrigger,
        size_bytes: int,
        sections: List[str],
        duration_ms: float,
    ) -> CheckpointResult:
        """Create a successful checkpoint result."""
        sla_met = duration_ms <= cls.SLA_THRESHOLD_MS
        return cls(
            success=True,
            checkpoint_id=checkpoint_id,
            trigger=trigger,
            size_bytes=size_bytes,
            sections_checkpointed=sections,
            duration_ms=duration_ms,
            sla_met=sla_met,
        )

    @classmethod
    def failure(
        cls,
        error: str,
        trigger: CheckpointTrigger = CheckpointTrigger.MANUAL,
        duration_ms: float = 0.0,
    ) -> CheckpointResult:
        """Create a failed checkpoint result."""
        return cls(
            success=False,
            checkpoint_id="",
            trigger=trigger,
            error=error,
            duration_ms=duration_ms,
            sla_met=False,
        )


@dataclass
class LifecycleConfig:
    """
    Configuration for lifecycle management.

    Attributes:
        checkpoint_interval_ms: Periodic checkpoint interval (0 = disabled)
        restore_on_start: Whether to restore from storage on start
        checkpoint_on_stop: Whether to checkpoint before stop
        max_start_duration_ms: Maximum time allowed for start
        max_stop_duration_ms: Maximum time allowed for stop
        health_check_interval_ms: Health check frequency (0 = on-demand only)
    """

    checkpoint_interval_ms: int = 30000  # 30 seconds default
    restore_on_start: bool = True
    checkpoint_on_stop: bool = True
    max_start_duration_ms: int = 5000  # 5 seconds max
    max_stop_duration_ms: int = 5000  # 5 seconds max
    health_check_interval_ms: int = 0  # On-demand only by default

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checkpoint_interval_ms": self.checkpoint_interval_ms,
            "restore_on_start": self.restore_on_start,
            "checkpoint_on_stop": self.checkpoint_on_stop,
            "max_start_duration_ms": self.max_start_duration_ms,
            "max_stop_duration_ms": self.max_stop_duration_ms,
            "health_check_interval_ms": self.health_check_interval_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LifecycleConfig:
        """Create from dictionary."""
        return cls(
            checkpoint_interval_ms=data.get("checkpoint_interval_ms", 30000),
            restore_on_start=data.get("restore_on_start", True),
            checkpoint_on_stop=data.get("checkpoint_on_stop", True),
            max_start_duration_ms=data.get("max_start_duration_ms", 5000),
            max_stop_duration_ms=data.get("max_stop_duration_ms", 5000),
            health_check_interval_ms=data.get("health_check_interval_ms", 0),
        )

    @classmethod
    def default(cls) -> LifecycleConfig:
        """Create default configuration."""
        return cls()

    @classmethod
    def testing(cls) -> LifecycleConfig:
        """Create configuration for testing (no timers)."""
        return cls(
            checkpoint_interval_ms=0,  # Disable periodic checkpoint
            restore_on_start=False,  # Fresh session
            health_check_interval_ms=0,
        )


# =============================================================================
# INTERFACE
# =============================================================================


class ILifecyclePort(ABC):
    """
    Interface for SessionState lifecycle management.

    SessionState uses this port to:
    - Start/stop the session
    - Report health status
    - Trigger checkpoints

    State Machine:
        CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED

    Implementations:
        - StandaloneLifecycle: Self-managed (standalone mode)
        - FabricLifecycle: Fabric integration (future)

    Properties:
        state: Current lifecycle state
        config: Lifecycle configuration
        session_id: Managed session ID
        started_at_ms: Timestamp when started (0 if not started)
        checkpoint_count: Total checkpoints since start
        last_checkpoint_ms: Timestamp of last checkpoint

    Example:
        class StandaloneLifecycle(ILifecyclePort):
            def start(self) -> StartResult:
                self._state = LifecycleState.STARTING
                # Initialize sections
                self._state = LifecycleState.RUNNING
                return StartResult.success_fresh(self._session_id, duration)
    """

    @property
    @abstractmethod
    def state(self) -> LifecycleState:
        """
        Get current lifecycle state.

        Returns:
            LifecycleState: Current state
        """
        pass

    @property
    @abstractmethod
    def session_id(self) -> str:
        """
        Get the session ID being managed.

        Returns:
            str: Session identifier
        """
        pass

    @property
    @abstractmethod
    def config(self) -> LifecycleConfig:
        """
        Get lifecycle configuration.

        Returns:
            LifecycleConfig: Current configuration
        """
        pass

    @property
    @abstractmethod
    def started_at_ms(self) -> int:
        """
        Get timestamp when session was started.

        Returns:
            int: Start timestamp in ms (0 if not started)
        """
        pass

    @property
    @abstractmethod
    def checkpoint_count(self) -> int:
        """
        Get total checkpoint count since start.

        Returns:
            int: Number of checkpoints
        """
        pass

    @property
    @abstractmethod
    def last_checkpoint_ms(self) -> int:
        """
        Get timestamp of last checkpoint.

        Returns:
            int: Checkpoint timestamp in ms (0 if none)
        """
        pass

    @abstractmethod
    def start(self, restore_if_exists: bool = True) -> StartResult:
        """
        Start the SessionState lifecycle.

        Args:
            restore_if_exists: Whether to attempt restore from LOCAL COLD

        Actions:
            1. Validate current state allows start
            2. Transition CREATED -> STARTING
            3. Initialize all sections (fresh or restore)
            4. Start checkpoint timer (if configured)
            5. Transition STARTING -> RUNNING

        Returns:
            StartResult: Success/failure with timing and restore info

        Raises:
            InvalidStateError: If not in CREATED or STOPPED state

        Example:
            result = lifecycle.start()
            if result.success:
                print(f"Started in {result.duration_ms}ms")
                if result.restored:
                    print(f"Restored from {result.restore_source}")
        """
        pass

    @abstractmethod
    def stop(self, checkpoint_before_stop: bool = True) -> StopResult:
        """
        Stop the SessionState lifecycle gracefully.

        Args:
            checkpoint_before_stop: Whether to checkpoint before stopping

        Actions:
            1. Validate current state allows stop
            2. Transition RUNNING -> STOPPING
            3. Stop checkpoint timer
            4. Final checkpoint to LOCAL COLD (if requested)
            5. Release resources
            6. Transition STOPPING -> STOPPED

        Returns:
            StopResult: Success/failure with checkpoint info

        Behavior:
            - Graceful shutdown (complete pending operations)
            - Always attempt final checkpoint unless explicitly skipped
            - Never lose data

        Example:
            result = lifecycle.stop()
            if result.checkpoint_id:
                print(f"Final checkpoint: {result.checkpoint_id}")
        """
        pass

    @abstractmethod
    def health(self) -> HealthStatus:
        """
        Get health status.

        Returns:
            HealthStatus: Current health information

        Used by:
            - Fabric health checks
            - CLI status command
            - Monitoring systems

        Health Determination:
            - healthy=True if RUNNING and pressure < CRITICAL
            - healthy=False if ERROR or CRITICAL pressure

        Example:
            status = lifecycle.health()
            if not status.healthy:
                logger.warning(f"Unhealthy: {status.error}")
        """
        pass

    @abstractmethod
    def checkpoint(
        self,
        trigger: CheckpointTrigger = CheckpointTrigger.MANUAL,
    ) -> CheckpointResult:
        """
        Trigger immediate checkpoint to LOCAL COLD.

        Args:
            trigger: What triggered this checkpoint

        Returns:
            CheckpointResult: Success/failure with size info

        Behavior:
            - Serialize all sections via FlatBuffers
            - Write to LOCAL COLD (K1 SQLite)
            - Optional: Queue K0 sync (non-blocking)
            - Track checkpoint in metrics

        Performance:
            Target: <50ms for full checkpoint

        Example:
            result = lifecycle.checkpoint(CheckpointTrigger.MANUAL)
            if result.success:
                print(f"Checkpoint {result.checkpoint_id}: {result.size_bytes} bytes")
            if not result.sla_met:
                logger.warning(f"SLA violation: {result.duration_ms}ms")
        """
        pass

    def request_shutdown(self) -> None:
        """
        Request graceful shutdown.

        Non-blocking. Stop will be performed asynchronously.

        Default implementation calls stop() directly.
        Fabric implementation may coordinate shutdown.
        """
        self.stop()

    def get_uptime_ms(self) -> int:
        """
        Get uptime in milliseconds.

        Returns:
            int: Milliseconds since start (0 if not started)

        Default implementation calculates from started_at_ms.
        """
        if self.started_at_ms == 0:
            return 0
        return int(time.time() * 1000) - self.started_at_ms

    def is_running(self) -> bool:
        """
        Check if lifecycle is in RUNNING state.

        Returns:
            bool: True if state is RUNNING
        """
        return self.state == LifecycleState.RUNNING

    def can_checkpoint(self) -> bool:
        """
        Check if checkpoint is allowed.

        Returns:
            bool: True if state allows checkpoint
        """
        return self.state.can_checkpoint()


# =============================================================================
# INVALID STATE ERROR
# =============================================================================


class InvalidStateError(Exception):
    """
    Raised when operation is invalid for current lifecycle state.

    Attributes:
        current_state: State when operation was attempted
        operation: Operation that was attempted
        valid_states: States where operation would be valid
    """

    def __init__(
        self,
        current_state: LifecycleState,
        operation: str,
        valid_states: List[LifecycleState],
    ):
        self.current_state = current_state
        self.operation = operation
        self.valid_states = valid_states
        valid_str = ", ".join(s.value for s in valid_states)
        super().__init__(
            f"Cannot {operation} in state {current_state.value}. " f"Valid states: {valid_str}"
        )


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. STATE MACHINE:
   Valid transitions:
   CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
   Any state -> ERROR (on failure)
   STOPPED -> STARTING (restart)

   Invalid transitions raise InvalidStateError.

2. CHECKPOINT TIMER:
   - Standalone: Periodic timer (e.g., every 30s)
   - Fabric: May be triggered by Fabric
   - Timer should be stoppable and restartable
   - Use LifecycleConfig.checkpoint_interval_ms

3. GRACEFUL SHUTDOWN:
   - Complete pending mutations before checkpoint
   - Final checkpoint (unless checkpoint_before_stop=False)
   - Release resources (close timers, clear state)
   - Never lose data - checkpoint or log failure

4. HEALTH CHECK CONTENTS:
   - healthy: Overall health (True if RUNNING and pressure < CRITICAL)
   - state: Current lifecycle state
   - pressure_level: Memory pressure from SizeTracker
   - hot_utilization_pct: HOT tier usage
   - warm_utilization_pct: WARM tier usage
   - last_checkpoint_ms: When last checkpoint occurred
   - checkpoint_count: Total checkpoints since start
   - uptime_ms: Time since start
   - turn_count: Turns processed (from Meta section)
   - mutation_count: Mutations applied (from manager)

5. IMPLEMENTATIONS TO CREATE:
   - StandaloneLifecycle (k1/sessionstate/adapters/standalone_lifecycle.py)
     Features:
       - Self-managed state transitions
       - Optional periodic checkpoint timer
       - Restore from LOCAL COLD on start
       - Context manager support (__enter__, __exit__)

   - FabricLifecycle (k1/fabric/adapters/sessionstate.py) - FUTURE
     Features:
       - Fabric-coordinated state transitions
       - Health reporting to Fabric
       - Coordinated shutdown across services

6. TESTING:
   - Test all state transitions
   - Test invalid transition raises InvalidStateError
   - Test checkpoint on stop
   - Test health reporting in all states
   - Test restart after stop
   - Test restore on start
   - Test SLA tracking

7. THREAD SAFETY:
   - State transitions should be atomic
   - Use RLock for state changes
   - health() should be safe from any thread
   - checkpoint() should serialize with mutations

8. CONFIGURATION:
   Use LifecycleConfig for all configurable parameters:
   - checkpoint_interval_ms: Periodic checkpoint (0 = disabled)
   - restore_on_start: Auto-restore behavior
   - checkpoint_on_stop: Final checkpoint behavior
   - max_start_duration_ms: Timeout for start
   - max_stop_duration_ms: Timeout for stop

9. OBSERVABILITY:
   - Log all state transitions
   - Log checkpoint results with timing
   - Emit events for state changes (via IEventPort if available)
   - Track metrics: checkpoint_count, checkpoint_duration_avg

10. ERROR HANDLING:
    - start() failure -> ERROR state
    - stop() failure -> ERROR state (with best-effort cleanup)
    - checkpoint() failure -> remain RUNNING, return error in result
    - Never panic - always return result with error field
"""
