"""
Trigger Engines - Implementations for each trigger type.

Each trigger type has its own engine that evaluates whether the trigger
condition is met and fires callbacks when appropriate.

Architecture (ADR-K004):
    Layer 3 of Capability Mesh - PipelineScheduler uses these engines
    to implement declarative trigger-based pipeline activation.

Trigger Types (Phase 1):
    - INTERVAL: Fire at fixed time intervals
    - THRESHOLD: Fire when table row count exceeds threshold
    - MANUAL: Fire only on explicit request (API call)

Trigger Types (Phase 2):
    - CRON: Fire on cron schedule (requires croniter)
    - IDLE: Fire after idle period with pending items (requires ActivityTracker)

Related:
- k0/runtime/schemas.py: TriggerSpec, TriggerType
- k0/scheduler/scheduler.py: PipelineScheduler
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from k0.kernel.syscalls import Syscalls
    from k0.runtime.schemas import TriggerSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TriggerEvent:
    """
    Event emitted when a trigger fires.

    Attributes:
        trigger_id: ID of the trigger that fired
        pipeline_id: Pipeline this trigger belongs to
        fired_at: Monotonic timestamp when trigger fired
        context: Optional context data (e.g., count for threshold triggers)
    """

    trigger_id: str
    pipeline_id: str
    fired_at: float
    context: dict[str, Any] = field(default_factory=dict)


# Type alias for trigger callbacks
TriggerCallback = Callable[[TriggerEvent], None]


class TriggerEngine(ABC):
    """
    Abstract base class for trigger engines.

    Each trigger type has a concrete engine that:
    1. Monitors for trigger conditions
    2. Fires callbacks when conditions are met
    3. Can be started/stopped independently
    """

    def __init__(self, spec: "TriggerSpec", pipeline_id: str):
        """
        Initialize trigger engine.

        Args:
            spec: TriggerSpec from pipeline YAML
            pipeline_id: Pipeline this trigger belongs to
        """
        self.spec = spec
        self.pipeline_id = pipeline_id
        self._running = False
        self._last_fired: float | None = None
        self._fire_count = 0

    @abstractmethod
    async def start(self, callback: TriggerCallback) -> None:
        """
        Start the trigger engine.

        Args:
            callback: Function to call when trigger fires
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the trigger engine."""
        pass

    @property
    def is_running(self) -> bool:
        """Check if engine is currently running."""
        return self._running

    @property
    def last_fired(self) -> float | None:
        """Timestamp of last trigger fire."""
        return self._last_fired

    @property
    def fire_count(self) -> int:
        """Number of times trigger has fired."""
        return self._fire_count

    def _create_event(self, context: dict[str, Any] | None = None) -> TriggerEvent:
        """Create a trigger event with current timestamp."""
        return TriggerEvent(
            trigger_id=self.spec.id,
            pipeline_id=self.pipeline_id,
            fired_at=time.monotonic(),
            context=context or {},
        )

    def _record_fire(self, event: TriggerEvent) -> None:
        """Record that the trigger fired."""
        self._last_fired = event.fired_at
        self._fire_count += 1


class IntervalTriggerEngine(TriggerEngine):
    """
    Trigger that fires at fixed time intervals.

    Example spec:
        - id: periodic_cleanup
          type: interval
          interval_seconds: 300
    """

    def __init__(self, spec: "TriggerSpec", pipeline_id: str):
        super().__init__(spec, pipeline_id)
        self._task: asyncio.Task | None = None
        self._callback: TriggerCallback | None = None

    async def start(self, callback: TriggerCallback) -> None:
        """Start interval trigger."""
        if self._running:
            return

        self._running = True
        self._callback = callback
        self._task = asyncio.create_task(self._run_loop())

        logger.info(
            "Started interval trigger %s for %s (every %ds)",
            self.spec.id,
            self.pipeline_id,
            self.spec.interval_seconds,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "interval_seconds": self.spec.interval_seconds,
            },
        )

    async def _run_loop(self) -> None:
        """Run the interval loop."""
        interval = self.spec.interval_seconds or 60

        while self._running:
            try:
                await asyncio.sleep(interval)

                if not self._running:
                    break

                event = self._create_event()
                self._record_fire(event)

                if self._callback:
                    self._callback(event)

                logger.debug(
                    "Interval trigger %s fired (count=%d)",
                    self.spec.id,
                    self._fire_count,
                    extra={
                        "trigger_id": self.spec.id,
                        "pipeline_id": self.pipeline_id,
                        "fire_count": self._fire_count,
                    },
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Interval trigger %s error: %s",
                    self.spec.id,
                    e,
                    exc_info=True,
                    extra={
                        "trigger_id": self.spec.id,
                        "pipeline_id": self.pipeline_id,
                        "error": str(e),
                    },
                )

    async def stop(self) -> None:
        """Stop interval trigger."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(
            "Stopped interval trigger %s (fired %d times)",
            self.spec.id,
            self._fire_count,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
            },
        )


class ThresholdTriggerEngine(TriggerEngine):
    """
    Trigger that fires when a table row count exceeds threshold.

    Uses syscalls.query_count() to check table counts.

    Example spec:
        - id: batch_processor
          type: threshold
          table: st_vec
          condition: "status = 'READY'"
          threshold_count: 50
          check_interval_seconds: 30
    """

    def __init__(
        self,
        spec: "TriggerSpec",
        pipeline_id: str,
        syscalls: "Syscalls",
    ):
        super().__init__(spec, pipeline_id)
        self._syscalls = syscalls
        self._task: asyncio.Task | None = None
        self._callback: TriggerCallback | None = None

    async def start(self, callback: TriggerCallback) -> None:
        """Start threshold trigger."""
        if self._running:
            return

        self._running = True
        self._callback = callback
        self._task = asyncio.create_task(self._run_loop())

        logger.info(
            "Started threshold trigger %s for %s (table=%s, threshold=%d)",
            self.spec.id,
            self.pipeline_id,
            self.spec.table,
            self.spec.threshold_count,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "table": self.spec.table,
                "threshold_count": self.spec.threshold_count,
                "check_interval_seconds": self.spec.check_interval_seconds,
            },
        )

    async def _run_loop(self) -> None:
        """Run the threshold check loop."""
        check_interval = self.spec.check_interval_seconds or 60

        while self._running:
            try:
                await asyncio.sleep(check_interval)

                if not self._running:
                    break

                # Check threshold
                count = await self._check_count()
                threshold = self.spec.threshold_count or 1

                if count >= threshold:
                    event = self._create_event({"count": count, "threshold": threshold})
                    self._record_fire(event)

                    if self._callback:
                        self._callback(event)

                    logger.info(
                        "Threshold trigger %s fired: count=%d >= threshold=%d",
                        self.spec.id,
                        count,
                        threshold,
                        extra={
                            "trigger_id": self.spec.id,
                            "pipeline_id": self.pipeline_id,
                            "count": count,
                            "threshold": threshold,
                            "fire_count": self._fire_count,
                        },
                    )
                else:
                    logger.debug(
                        "Threshold trigger %s check: count=%d < threshold=%d",
                        self.spec.id,
                        count,
                        threshold,
                        extra={
                            "trigger_id": self.spec.id,
                            "count": count,
                            "threshold": threshold,
                        },
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Threshold trigger %s error: %s",
                    self.spec.id,
                    e,
                    exc_info=True,
                    extra={
                        "trigger_id": self.spec.id,
                        "pipeline_id": self.pipeline_id,
                        "error": str(e),
                    },
                )

    async def _check_count(self) -> int:
        """Check current count from table."""
        table = self.spec.table
        condition = self.spec.condition or "1=1"

        if not table:
            return 0

        try:
            count = await self._syscalls.query_count(
                table=table,
                where=condition,
            )
            return count
        except Exception as e:
            logger.warning(
                "Threshold check failed for %s: %s",
                self.spec.id,
                e,
                extra={
                    "trigger_id": self.spec.id,
                    "table": table,
                    "condition": condition,
                    "error": str(e),
                },
            )
            return 0

    async def stop(self) -> None:
        """Stop threshold trigger."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(
            "Stopped threshold trigger %s (fired %d times)",
            self.spec.id,
            self._fire_count,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
            },
        )


class ManualTriggerEngine(TriggerEngine):
    """
    Trigger that only fires on explicit request.

    Useful for pipelines that should be triggered via API call
    or administrative action rather than automatically.

    Example spec:
        - id: manual_reindex
          type: manual
    """

    def __init__(self, spec: "TriggerSpec", pipeline_id: str):
        super().__init__(spec, pipeline_id)
        self._callback: TriggerCallback | None = None

    async def start(self, callback: TriggerCallback) -> None:
        """Start manual trigger (just stores callback)."""
        self._running = True
        self._callback = callback

        logger.info(
            "Registered manual trigger %s for %s",
            self.spec.id,
            self.pipeline_id,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
            },
        )

    async def stop(self) -> None:
        """Stop manual trigger."""
        self._running = False
        self._callback = None

        logger.info(
            "Unregistered manual trigger %s (fired %d times)",
            self.spec.id,
            self._fire_count,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
            },
        )

    def fire(self) -> bool:
        """
        Manually fire the trigger.

        Returns:
            True if trigger was fired, False if not running
        """
        if not self._running or not self._callback:
            logger.warning(
                "Cannot fire manual trigger %s: not running",
                self.spec.id,
                extra={"trigger_id": self.spec.id},
            )
            return False

        event = self._create_event()
        self._record_fire(event)
        self._callback(event)

        logger.info(
            "Manual trigger %s fired (count=%d)",
            self.spec.id,
            self._fire_count,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
            },
        )

        return True


class CronTriggerEngine(TriggerEngine):
    """
    Trigger based on cron expression.

    Supports standard 5-field cron expressions:
    - minute (0-59)
    - hour (0-23)
    - day of month (1-31)
    - month (1-12)
    - day of week (0-6, Sunday=0)

    Requires the `croniter` package: pip install croniter
    Or install with scheduler extras: pip install -e ".[scheduler]"

    Example spec:
        - id: consolidation_nightly
          type: cron
          cron_expression: "0 2 * * *"  # 2 AM daily

    P03 Use Case:
        - Consolidation window: "0 2-5 * * *" (2AM-5AM hourly)
    """

    def __init__(
        self,
        spec: "TriggerSpec",
        pipeline_id: str,
        timezone: str = "UTC",
    ):
        super().__init__(spec, pipeline_id)
        self._timezone = timezone
        self._cron: Any = None  # croniter instance
        self._task: asyncio.Task | None = None
        self._callback: TriggerCallback | None = None

    async def start(self, callback: TriggerCallback) -> None:
        """Start cron trigger engine."""
        if self._running:
            logger.warning(
                "CronTriggerEngine %s already running",
                self.spec.id,
                extra={"trigger_id": self.spec.id},
            )
            return

        try:
            from croniter import croniter
        except ImportError as e:
            raise RuntimeError(
                "croniter not installed. Install with: pip install croniter "
                "or pip install -e '.[scheduler]'"
            ) from e

        if not self.spec.cron_expression:
            raise ValueError(f"Cron trigger {self.spec.id} missing cron_expression")

        # Validate cron expression
        try:
            self._cron = croniter(self.spec.cron_expression)
        except (KeyError, ValueError) as e:
            raise ValueError(
                f"Invalid cron expression '{self.spec.cron_expression}' for trigger "
                f"{self.spec.id}: {e}"
            ) from e

        self._callback = callback
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

        logger.info(
            "CronTriggerEngine %s started with expression: %s",
            self.spec.id,
            self.spec.cron_expression,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "cron_expression": self.spec.cron_expression,
                "timezone": self._timezone,
            },
        )

    async def stop(self) -> None:
        """Stop cron trigger engine."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(
            "CronTriggerEngine %s stopped (fired %d times)",
            self.spec.id,
            self._fire_count,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
            },
        )

    async def _run_loop(self) -> None:
        """Main loop - sleep until next cron time, then fire."""
        while self._running:
            try:
                # Get next scheduled time
                next_fire = self._cron.get_next(float)
                now = time.time()
                delay = next_fire - now

                if delay > 0:
                    logger.debug(
                        "CronTrigger %s sleeping for %.1f seconds until next fire",
                        self.spec.id,
                        delay,
                        extra={
                            "trigger_id": self.spec.id,
                            "delay_seconds": delay,
                            "next_fire": next_fire,
                        },
                    )
                    await asyncio.sleep(delay)

                if self._running and self._callback:
                    event = self._create_event(
                        {
                            "scheduled_time": next_fire,
                            "trigger_type": "cron",
                            "cron_expression": self.spec.cron_expression,
                        }
                    )
                    self._record_fire(event)
                    self._callback(event)

                    logger.info(
                        "CronTrigger %s fired (count=%d)",
                        self.spec.id,
                        self._fire_count,
                        extra={
                            "trigger_id": self.spec.id,
                            "pipeline_id": self.pipeline_id,
                            "fire_count": self._fire_count,
                            "scheduled_time": next_fire,
                        },
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "CronTrigger %s error: %s",
                    self.spec.id,
                    str(e),
                    exc_info=True,
                    extra={
                        "trigger_id": self.spec.id,
                        "pipeline_id": self.pipeline_id,
                        "error": str(e),
                    },
                )
                # Sleep before retry to prevent tight error loop
                await asyncio.sleep(60)

    def get_next_fire_time(self) -> float | None:
        """
        Return next scheduled fire time (for debugging/observability).

        Returns:
            Unix timestamp of next fire time, or None if not started
        """
        if self._cron:
            from croniter import croniter

            # Create new iterator to avoid advancing the internal state
            cron = croniter(self.spec.cron_expression)
            return cron.get_next(float)
        return None


class IdleTriggerEngine(TriggerEngine):
    """
    Trigger when system is idle for specified duration.

    Optionally waits for minimum pending work count before firing.
    Uses ActivityTracker for idle detection.

    Example spec:
        - id: consolidation_idle
          type: idle
          idle_seconds: 300  # 5 minutes
          min_pending: 100   # Optional: require 100+ pending items

    P03 Use Case:
        - Fire when idle 5 minutes AND 100+ pending embeddings
    """

    def __init__(
        self,
        spec: "TriggerSpec",
        pipeline_id: str,
        activity_tracker: "ActivityTracker",
        syscalls: "Syscalls | None" = None,
    ):
        super().__init__(spec, pipeline_id)
        self._tracker = activity_tracker
        self._syscalls = syscalls
        self._callback: TriggerCallback | None = None
        self._listener_id: str | None = None

    async def start(self, callback: TriggerCallback) -> None:
        """Start idle trigger engine."""
        if self._running:
            logger.warning(
                "IdleTriggerEngine %s already running",
                self.spec.id,
                extra={"trigger_id": self.spec.id},
            )
            return

        if not self.spec.idle_seconds:
            raise ValueError(f"Idle trigger {self.spec.id} missing idle_seconds")

        self._callback = callback
        self._running = True
        self._listener_id = f"trigger_{self.spec.id}_{self.pipeline_id}"

        # Register with activity tracker
        await self._tracker.register_idle_listener(
            listener_id=self._listener_id,
            callback=self._on_idle,
            threshold_seconds=self.spec.idle_seconds,
        )

        logger.info(
            "IdleTriggerEngine %s started (idle_seconds=%.1f, min_pending=%s)",
            self.spec.id,
            self.spec.idle_seconds,
            self.spec.min_pending or "none",
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "idle_seconds": self.spec.idle_seconds,
                "min_pending": self.spec.min_pending,
            },
        )

    async def stop(self) -> None:
        """Stop idle trigger engine."""
        self._running = False

        if self._listener_id:
            await self._tracker.unregister_idle_listener(self._listener_id)
            self._listener_id = None

        logger.info(
            "IdleTriggerEngine %s stopped (fired %d times)",
            self.spec.id,
            self._fire_count,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
            },
        )

    def _on_idle(self) -> None:
        """Callback when idle threshold met."""
        if not self._running or not self._callback:
            return

        # Check min_pending condition if specified
        if self.spec.min_pending and self.spec.min_pending > 0:
            pending = self._get_pending_count()
            if pending < self.spec.min_pending:
                logger.debug(
                    "IdleTrigger %s skipped: pending=%d < min_pending=%d",
                    self.spec.id,
                    pending,
                    self.spec.min_pending,
                    extra={
                        "trigger_id": self.spec.id,
                        "pending_count": pending,
                        "min_pending": self.spec.min_pending,
                    },
                )
                return

        # Fire the trigger
        idle_secs = self._tracker.idle_seconds()
        event = self._create_event(
            {
                "idle_seconds": idle_secs,
                "trigger_type": "idle",
                "pending_count": self._get_pending_count() if self.spec.min_pending else None,
            }
        )
        self._record_fire(event)
        self._callback(event)

        logger.info(
            "IdleTrigger %s fired (count=%d, idle=%.1fs)",
            self.spec.id,
            self._fire_count,
            idle_secs,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
                "idle_seconds": idle_secs,
            },
        )

    def _get_pending_count(self) -> int:
        """Get pending item count via syscalls."""
        if not self._syscalls:
            return 0

        try:
            # Use query_count syscall to get pending items
            # This is sync because callback is sync - run in thread if async needed
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context but callback is sync
                # For now, return 0 and log - proper fix needs async callback
                logger.warning(
                    "IdleTrigger %s cannot query pending count from sync callback",
                    self.spec.id,
                )
                return 0

            result = loop.run_until_complete(
                self._syscalls.query_count(
                    table=self.spec.table or "st_vec",
                    where=self.spec.condition or "status = 'pending'",
                )
            )
            return result
        except Exception as e:
            logger.error(
                "IdleTrigger %s failed to get pending count: %s",
                self.spec.id,
                str(e),
                extra={
                    "trigger_id": self.spec.id,
                    "error": str(e),
                },
            )
            return 0


# Type hint for ActivityTracker (avoid circular import)
if TYPE_CHECKING:
    from k0.scheduler.activity import ActivityTracker


def create_trigger_engine(
    spec: "TriggerSpec",
    pipeline_id: str,
    syscalls: "Syscalls | None" = None,
    activity_tracker: Any = None,  # ActivityTracker for IDLE triggers (Phase 2)
) -> TriggerEngine:
    """
    Factory function to create appropriate trigger engine.

    Args:
        spec: Trigger specification from pipeline YAML
        pipeline_id: Pipeline this trigger belongs to
        syscalls: Syscalls instance for threshold/idle queries
        activity_tracker: ActivityTracker for IDLE triggers

    Returns:
        Appropriate TriggerEngine subclass instance

    Raises:
        ValueError: If required dependencies missing for trigger type
    """
    from k0.runtime.schemas import TriggerType

    if spec.type == TriggerType.INTERVAL:
        return IntervalTriggerEngine(spec, pipeline_id)

    elif spec.type == TriggerType.THRESHOLD:
        if syscalls is None:
            raise ValueError(f"Threshold trigger {spec.id} requires syscalls for query_count")
        return ThresholdTriggerEngine(spec, pipeline_id, syscalls)

    elif spec.type == TriggerType.MANUAL:
        return ManualTriggerEngine(spec, pipeline_id)

    elif spec.type == TriggerType.CRON:
        return CronTriggerEngine(spec, pipeline_id)

    elif spec.type == TriggerType.IDLE:
        if activity_tracker is None:
            raise ValueError(
                f"Idle trigger {spec.id} requires activity_tracker. "
                "Ensure ActivityTracker is started before creating IDLE triggers."
            )
        return IdleTriggerEngine(spec, pipeline_id, activity_tracker, syscalls)

    else:
        raise ValueError(f"Unsupported trigger type: {spec.type}")
