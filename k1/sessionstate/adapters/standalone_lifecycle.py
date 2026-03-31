"""
StandaloneLifecycle - Self-Managed Lifecycle for Standalone Mode
=================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.4 Define Lifecycle Port
ISSUE: 3.4.2

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Self-managed lifecycle for standalone operation.
    No Fabric coordination, direct state transitions.

FEATURES:
    - Automatic periodic checkpoint (configurable interval)
    - Graceful shutdown with final checkpoint
    - Health reporting with pressure monitoring
    - Context manager support (__enter__/__exit__)
    - Restart capability (STOPPED -> RUNNING)

CHECKPOINT BEHAVIOR:
    - Periodic timer (configurable, default 30s, 0 = disabled)
    - Checkpoint to LOCAL COLD via SessionStateManager
    - SLA tracking (<50ms target)

STATE MACHINE:
    CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
    STOPPED -> STARTING (restart)
    Any -> ERROR (on failure)

==============================================================================
CLASS: StandaloneLifecycle
==============================================================================
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Optional

from ..ports.lifecycle import (
    CheckpointResult,
    CheckpointTrigger,
    HealthStatus,
    ILifecyclePort,
    InvalidStateError,
    LifecycleConfig,
    LifecycleState,
    PressureLevel,
    RestoreSource,
    StartResult,
    StopResult,
)

if TYPE_CHECKING:
    from ..manager import SessionStateManager

logger = logging.getLogger(__name__)


class StandaloneLifecycle(ILifecyclePort):
    """
    Self-managed lifecycle adapter for standalone mode.

    Handles start/stop/checkpoint without Fabric.
    Runs periodic checkpoint timer (daemon thread).

    Attributes:
        _manager: SessionStateManager reference
        _config: Lifecycle configuration
        _state: Current lifecycle state
        _checkpoint_timer: Timer thread for periodic checkpoints
        _started_at_ms: Start timestamp
        _last_checkpoint_ms: Last checkpoint timestamp
        _checkpoint_count: Total checkpoints since start
        _lock: Threading lock for state transitions

    Thread Safety:
        - State transitions protected by RLock
        - Checkpoint timer runs on daemon thread
        - health() is safe from any thread

    Example:
        lifecycle = StandaloneLifecycle(manager)

        result = lifecycle.start()
        assert result.state == LifecycleState.RUNNING

        # ... use SessionState ...

        result = lifecycle.stop()
        assert result.checkpoint_id is not None

    Context Manager:
        with StandaloneLifecycle(manager) as lifecycle:
            # SessionState is running
            pass
        # SessionState is stopped with checkpoint
    """

    __slots__ = (
        "_manager",
        "_config",
        "_state",
        "_checkpoint_timer",
        "_started_at_ms",
        "_last_checkpoint_ms",
        "_checkpoint_count",
        "_lock",
        "_error_message",
    )

    def __init__(
        self,
        manager: SessionStateManager,
        config: Optional[LifecycleConfig] = None,
        checkpoint_interval_s: Optional[float] = None,
    ) -> None:
        """
        Initialize StandaloneLifecycle.

        Args:
            manager: SessionStateManager to manage
            config: Lifecycle configuration (optional)
            checkpoint_interval_s: Override checkpoint interval in seconds
                                   (for backward compatibility)

        Note:
            If both config and checkpoint_interval_s are provided,
            checkpoint_interval_s takes precedence.
        """
        self._manager = manager

        # Build config
        if config is not None:
            self._config = config
        else:
            self._config = LifecycleConfig.default()

        # Override interval if specified (backward compatibility)
        if checkpoint_interval_s is not None:
            self._config = LifecycleConfig(
                checkpoint_interval_ms=int(checkpoint_interval_s * 1000),
                restore_on_start=self._config.restore_on_start,
                checkpoint_on_stop=self._config.checkpoint_on_stop,
                max_start_duration_ms=self._config.max_start_duration_ms,
                max_stop_duration_ms=self._config.max_stop_duration_ms,
                health_check_interval_ms=self._config.health_check_interval_ms,
            )

        # State
        self._state = LifecycleState.CREATED
        self._checkpoint_timer: Optional[threading.Timer] = None
        self._started_at_ms: int = 0
        self._last_checkpoint_ms: int = 0
        self._checkpoint_count: int = 0
        self._lock = threading.RLock()
        self._error_message: Optional[str] = None

        logger.info(
            "StandaloneLifecycle initialized (session=%s, checkpoint_interval=%dms)",
            manager.session_id[:8] if manager.session_id else "none",
            self._config.checkpoint_interval_ms,
        )

    # =========================================================================
    # CONTEXT MANAGER
    # =========================================================================

    def __enter__(self) -> StandaloneLifecycle:
        """Start lifecycle on context enter."""
        result = self.start()
        if not result.success:
            raise RuntimeError(f"Failed to start lifecycle: {result.error}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Stop lifecycle on context exit."""
        self.stop()
        return False  # Don't suppress exceptions

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def state(self) -> LifecycleState:
        """
        Get current lifecycle state.

        Returns:
            LifecycleState: Current state

        Thread-safe: Yes (atomic read)
        """
        return self._state

    @property
    def session_id(self) -> str:
        """
        Get the session ID being managed.

        Returns:
            str: Session identifier
        """
        return self._manager.session_id

    @property
    def config(self) -> LifecycleConfig:
        """
        Get lifecycle configuration.

        Returns:
            LifecycleConfig: Current configuration
        """
        return self._config

    @property
    def started_at_ms(self) -> int:
        """
        Get timestamp when session was started.

        Returns:
            int: Start timestamp in ms (0 if not started)
        """
        return self._started_at_ms

    @property
    def checkpoint_count(self) -> int:
        """
        Get total checkpoint count since start.

        Returns:
            int: Number of checkpoints
        """
        return self._checkpoint_count

    @property
    def last_checkpoint_ms(self) -> int:
        """
        Get timestamp of last checkpoint.

        Returns:
            int: Checkpoint timestamp in ms (0 if none)
        """
        return self._last_checkpoint_ms

    # =========================================================================
    # LIFECYCLE METHODS
    # =========================================================================

    def start(self, restore_if_exists: bool = True) -> StartResult:
        """
        Start SessionState lifecycle.

        Actions:
            1. Validate current state (must be CREATED or STOPPED)
            2. Transition to STARTING
            3. Start the manager (with optional restore)
            4. Start checkpoint timer (if interval > 0)
            5. Transition to RUNNING
            6. Record start time

        Args:
            restore_if_exists: Whether to attempt restore from LOCAL COLD

        Returns:
            StartResult: Success/failure with timing

        Raises:
            InvalidStateError: If not in valid start state
        """
        start_time = time.perf_counter()

        with self._lock:
            # Validate state
            if not self._state.can_start():
                error = f"Cannot start from state {self._state.value}"
                logger.warning("Start failed: %s", error)
                return StartResult.failure(error)

            # Transition to STARTING
            self._state = LifecycleState.STARTING
            self._error_message = None

        try:
            # Use config setting unless explicitly overridden
            should_restore = restore_if_exists and self._config.restore_on_start

            # Start the manager
            manager_result = self._manager.start(restore_if_exists=should_restore)

            if not manager_result.success:
                with self._lock:
                    self._state = LifecycleState.ERROR
                    self._error_message = manager_result.error

                duration_ms = (time.perf_counter() - start_time) * 1000
                return StartResult.failure(
                    manager_result.error or "Manager start failed",
                    duration_ms,
                )

            # Start checkpoint timer if interval > 0
            if self._config.checkpoint_interval_ms > 0:
                self._start_checkpoint_timer()

            # Transition to RUNNING
            with self._lock:
                self._state = LifecycleState.RUNNING
                self._started_at_ms = int(time.time() * 1000)
                self._checkpoint_count = 0

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "StandaloneLifecycle started (session=%s, restored=%s, took=%.2fms)",
                self.session_id[:8] if self.session_id else "none",
                manager_result.restored,
                duration_ms,
            )

            # Build appropriate result
            if manager_result.restored:
                return StartResult.success_restored(
                    session_id=self.session_id,
                    source=RestoreSource(manager_result.restore_source),
                    sections=[],  # Manager doesn't provide this detail yet
                    duration_ms=duration_ms,
                )
            else:
                return StartResult.success_fresh(
                    session_id=self.session_id,
                    duration_ms=duration_ms,
                )

        except Exception as e:
            with self._lock:
                self._state = LifecycleState.ERROR
                self._error_message = str(e)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Start failed with exception: %s", str(e))
            return StartResult.failure(str(e), duration_ms)

    def stop(self, checkpoint_before_stop: bool = True) -> StopResult:
        """
        Stop SessionState lifecycle gracefully.

        Actions:
            1. Validate current state
            2. Transition to STOPPING
            3. Cancel checkpoint timer
            4. Final checkpoint to LOCAL COLD (if requested)
            5. Stop the manager
            6. Transition to STOPPED

        Args:
            checkpoint_before_stop: Whether to checkpoint before stopping
                                    (uses config default if not specified)

        Returns:
            StopResult: Success with checkpoint info
        """
        start_time = time.perf_counter()

        with self._lock:
            # Validate state
            if not self._state.can_stop():
                # Allow stopping from STARTING or ERROR too
                if self._state not in (LifecycleState.STARTING, LifecycleState.ERROR):
                    error = f"Cannot stop from state {self._state.value}"
                    logger.warning("Stop failed: %s", error)
                    return StopResult.failure(error)

            # Transition to STOPPING
            self._state = LifecycleState.STOPPING

        try:
            # Cancel checkpoint timer
            self._cancel_checkpoint_timer()

            checkpoint_id: Optional[str] = None
            checkpoint_size: int = 0

            # Final checkpoint (use config if not overridden)
            should_checkpoint = checkpoint_before_stop and self._config.checkpoint_on_stop
            if should_checkpoint and self._manager.is_running:
                checkpoint_result = self.checkpoint(CheckpointTrigger.STOP)
                if checkpoint_result.success:
                    checkpoint_id = checkpoint_result.checkpoint_id
                    checkpoint_size = checkpoint_result.size_bytes

            # Stop the manager
            self._manager.stop(checkpoint_before_stop=False)

            # Transition to STOPPED
            with self._lock:
                self._state = LifecycleState.STOPPED

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "StandaloneLifecycle stopped (session=%s, checkpoint=%s, took=%.2fms)",
                self.session_id[:8] if self.session_id else "none",
                checkpoint_id[:8] if checkpoint_id else "none",
                duration_ms,
            )

            if checkpoint_id:
                return StopResult.success_with_checkpoint(
                    checkpoint_id=checkpoint_id,
                    size_bytes=checkpoint_size,
                    duration_ms=duration_ms,
                )
            else:
                return StopResult.success_no_checkpoint(duration_ms)

        except Exception as e:
            with self._lock:
                self._state = LifecycleState.ERROR
                self._error_message = str(e)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Stop failed with exception: %s", str(e))
            return StopResult.failure(str(e), duration_ms)

    def health(self) -> HealthStatus:
        """
        Get health status.

        Returns:
            HealthStatus: Current health information

        Thread-safe: Yes (reads atomic values)

        Health Determination:
            - healthy=True if RUNNING and pressure != CRITICAL
            - healthy=False if ERROR or CRITICAL pressure
        """
        now = int(time.time() * 1000)

        # Calculate uptime
        uptime_ms = now - self._started_at_ms if self._started_at_ms > 0 else 0

        # Get pressure from size tracker
        try:
            size_snapshot = self._manager.size_tracker.get_snapshot()
            pressure_enum = size_snapshot.overall_pressure

            # Map to our PressureLevel enum
            pressure = PressureLevel(pressure_enum.value)

            # Calculate utilization percentages
            hot_pct = size_snapshot.hot_utilization_pct
            warm_pct = size_snapshot.warm_utilization_pct
            total_bytes = size_snapshot.total_bytes
        except Exception:
            # Fallback if manager is not available
            pressure = PressureLevel.NORMAL
            hot_pct = 0.0
            warm_pct = 0.0
            total_bytes = 0

        # Determine health
        is_running = self._state == LifecycleState.RUNNING
        is_critical = pressure == PressureLevel.CRITICAL
        healthy = is_running and not is_critical

        # Get turn and mutation counts if available
        try:
            turn_count = self._manager._mutation_count  # Approximation
            mutation_count = self._manager._mutation_count
        except Exception:
            turn_count = 0
            mutation_count = 0

        if self._state == LifecycleState.ERROR:
            return HealthStatus.unhealthy(
                state=self._state,
                error=self._error_message or "Unknown error",
                pressure=pressure,
            )

        return (
            HealthStatus.healthy_running(
                pressure=pressure,
                hot_pct=hot_pct,
                warm_pct=warm_pct,
                total_bytes=total_bytes,
                last_checkpoint_ms=self._last_checkpoint_ms,
                checkpoint_count=self._checkpoint_count,
                uptime_ms=uptime_ms,
                turn_count=turn_count,
                mutation_count=mutation_count,
            )
            if healthy
            else HealthStatus(
                healthy=False,
                state=self._state,
                pressure_level=pressure,
                hot_utilization_pct=hot_pct,
                warm_utilization_pct=warm_pct,
                total_size_bytes=total_bytes,
                last_checkpoint_ms=self._last_checkpoint_ms,
                checkpoint_count=self._checkpoint_count,
                uptime_ms=uptime_ms,
                turn_count=turn_count,
                mutation_count=mutation_count,
            )
        )

    def checkpoint(
        self,
        trigger: CheckpointTrigger = CheckpointTrigger.MANUAL,
    ) -> CheckpointResult:
        """
        Trigger immediate checkpoint to LOCAL COLD.

        Actions:
            1. Validate state (must be RUNNING)
            2. Call manager.checkpoint()
            3. Update metrics
            4. Reschedule timer if periodic

        Args:
            trigger: What triggered this checkpoint

        Returns:
            CheckpointResult: Success with size info

        SLA:
            Target <50ms for LOCAL COLD write
        """
        start_time = time.perf_counter()

        # Validate state
        if not self._state.can_checkpoint():
            return CheckpointResult.failure(
                error=f"Cannot checkpoint in state {self._state.value}",
                trigger=trigger,
            )

        try:
            # Delegate to manager
            manager_result = self._manager.checkpoint()

            duration_ms = (time.perf_counter() - start_time) * 1000

            if manager_result.success:
                # Update metrics
                with self._lock:
                    self._last_checkpoint_ms = int(time.time() * 1000)
                    self._checkpoint_count += 1

                logger.debug(
                    "Checkpoint complete (trigger=%s, id=%s, size=%d, took=%.2fms, sla=%s)",
                    trigger.value,
                    manager_result.checkpoint_id[:8] if manager_result.checkpoint_id else "none",
                    manager_result.size_bytes,
                    duration_ms,
                    manager_result.sla_met,
                )

                return CheckpointResult.success_checkpoint(
                    checkpoint_id=manager_result.checkpoint_id,
                    trigger=trigger,
                    size_bytes=manager_result.size_bytes,
                    sections=[],  # Could enumerate from manager if needed
                    duration_ms=duration_ms,
                )
            else:
                return CheckpointResult.failure(
                    error=manager_result.error or "Manager checkpoint failed",
                    trigger=trigger,
                    duration_ms=duration_ms,
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Checkpoint failed: %s", str(e))
            return CheckpointResult.failure(
                error=str(e),
                trigger=trigger,
                duration_ms=duration_ms,
            )

    # =========================================================================
    # TIMER MANAGEMENT
    # =========================================================================

    def _start_checkpoint_timer(self) -> None:
        """
        Start periodic checkpoint timer.

        Uses daemon thread so it doesn't block shutdown.
        Timer reschedules itself after each checkpoint.
        """
        if self._config.checkpoint_interval_ms <= 0:
            return  # Timer disabled

        interval_s = self._config.checkpoint_interval_ms / 1000.0

        def checkpoint_tick() -> None:
            """Timer callback - checkpoint and reschedule."""
            if self._state == LifecycleState.RUNNING:
                try:
                    self.checkpoint(CheckpointTrigger.PERIODIC)
                except Exception as e:
                    logger.warning("Periodic checkpoint failed: %s", str(e))

                # Reschedule if still running
                if self._state == LifecycleState.RUNNING:
                    self._start_checkpoint_timer()

        self._checkpoint_timer = threading.Timer(interval_s, checkpoint_tick)
        self._checkpoint_timer.daemon = True
        self._checkpoint_timer.name = f"checkpoint-timer-{self.session_id[:8]}"
        self._checkpoint_timer.start()

        logger.debug(
            "Checkpoint timer started (interval=%.1fs)",
            interval_s,
        )

    def _cancel_checkpoint_timer(self) -> None:
        """
        Cancel periodic checkpoint timer.

        Safe to call even if timer not running.
        """
        if self._checkpoint_timer is not None:
            self._checkpoint_timer.cancel()
            self._checkpoint_timer = None
            logger.debug("Checkpoint timer cancelled")

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def force_error(self, error: str) -> None:
        """
        Force transition to ERROR state.

        Used for testing or emergency situations.

        Args:
            error: Error message
        """
        with self._lock:
            self._state = LifecycleState.ERROR
            self._error_message = error

        self._cancel_checkpoint_timer()
        logger.error("Forced error state: %s", error)

    def reset(self) -> None:
        """
        Reset lifecycle to CREATED state.

        Only valid from STOPPED or ERROR state.
        Useful for testing.
        """
        with self._lock:
            if self._state not in (LifecycleState.STOPPED, LifecycleState.ERROR):
                raise InvalidStateError(
                    self._state,
                    "reset",
                    [LifecycleState.STOPPED, LifecycleState.ERROR],
                )

            self._state = LifecycleState.CREATED
            self._started_at_ms = 0
            self._last_checkpoint_ms = 0
            self._checkpoint_count = 0
            self._error_message = None

        logger.debug("Lifecycle reset to CREATED")


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. STATE MACHINE:
   CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
   STOPPED -> STARTING (restart supported)
   Any -> ERROR (on failure)

2. CHECKPOINT TIMER:
   Uses threading.Timer (daemon thread).
   Reschedules itself after each checkpoint.
   Cancelled on stop().
   Interval of 0 disables periodic checkpoints.

3. GRACEFUL SHUTDOWN:
   Always attempt final checkpoint (unless disabled).
   Cancel timer before checkpoint to avoid race.
   Don't lose data on stop.

4. HEALTH REPORTING:
   healthy = RUNNING and pressure != CRITICAL
   Returns uptime, pressure, last checkpoint time.
   Safe to call from any thread.

5. ERROR HANDLING:
   Checkpoint failures logged but don't break lifecycle.
   Return CheckpointResult with error.
   force_error() for testing emergency states.

6. CONTEXT MANAGER:
   with StandaloneLifecycle(manager) as lifecycle:
       # SessionState is running
       pass
   # SessionState is stopped with checkpoint

7. CONFIGURATION:
   Can use LifecycleConfig or simple interval.
   LifecycleConfig allows more control:
   - checkpoint_interval_ms
   - restore_on_start
   - checkpoint_on_stop
   - max_start/stop_duration_ms

8. TESTING:
   lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=1)
   lifecycle.start()
   time.sleep(3)
   assert lifecycle.checkpoint_count >= 2
   lifecycle.stop()
"""
