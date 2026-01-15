"""
Pipeline Scheduler - Core orchestrator for trigger-based pipeline execution.

The PipelineScheduler manages registered pipelines, their trigger engines,
and coordinates execution when triggers fire.

Architecture (ADR-K004):
    Layer 3 of Capability Mesh - Consumes trigger events from TriggerEngines
    and dispatches pipeline execution to the execution layer.

Key Components:
    - ScheduledPipeline: Container for a pipeline and its trigger engines
    - PipelineScheduler: Central coordinator for all scheduled pipelines

Related:
    - k0/scheduler/triggers.py: TriggerEngine implementations
    - k0/runtime/schemas.py: TriggerSpec, PipelineSpec
    - k0/kernel/syscalls.py: Syscalls for threshold queries
    - docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from .concurrency import get_single_flight_gate
from .triggers import (
    ManualTriggerEngine,
    TriggerCallback,
    TriggerEngine,
    TriggerEvent,
    create_trigger_engine,
)

if TYPE_CHECKING:
    from k0.kernel.syscalls import Syscalls
    from k0.runtime.schemas import PipelineSpec

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """State of a scheduled pipeline."""

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ScheduledPipeline:
    """
    Container for a registered pipeline and its trigger engines.

    Attributes:
        pipeline_id: Unique identifier for the pipeline
        spec: Full pipeline specification
        triggers: List of trigger engines for this pipeline
        state: Current lifecycle state
        execution_count: Number of times pipeline has been executed
        last_execution: Monotonic timestamp of last execution
    """

    pipeline_id: str
    spec: "PipelineSpec"
    triggers: list[TriggerEngine] = field(default_factory=list)
    state: PipelineState = PipelineState.REGISTERED
    execution_count: int = 0
    last_execution: float | None = None


@dataclass
class HotReloadResult:
    """
    Result of a hot reload operation.

    Attributes:
        affected_pipelines: List of pipeline IDs that were reloaded
        success: Whether the reload completed successfully
        error: Error message if failed
        added: Number of pipelines added
        updated: Number of pipelines updated
        removed: Number of pipelines removed
    """

    affected_pipelines: list[str] = field(default_factory=list)
    success: bool = False
    error: str | None = None
    added: int = 0
    updated: int = 0
    removed: int = 0


# Type for pipeline execution callback
PipelineExecutor = Callable[["ScheduledPipeline", TriggerEvent], None]


class PipelineScheduler:
    """
    Central coordinator for scheduled pipeline execution.

    The scheduler:
    1. Registers pipelines with their triggers
    2. Creates and manages trigger engines
    3. Dispatches pipeline execution when triggers fire
    4. Provides manual trigger firing capability

    Example:
        scheduler = PipelineScheduler(syscalls)
        scheduler.register_pipeline(pipeline_spec)
        await scheduler.start()
        # ... later
        await scheduler.stop()
    """

    def __init__(
        self,
        syscalls: "Syscalls",
        executor: PipelineExecutor | None = None,
    ):
        """
        Initialize the pipeline scheduler.

        Args:
            syscalls: Syscalls instance for threshold queries
            executor: Optional callback for pipeline execution
        """
        self._syscalls = syscalls
        self._executor = executor or self._default_executor
        self._pipelines: dict[str, ScheduledPipeline] = {}
        self._running = False
        self._lock = asyncio.Lock()
        self._reload_lock = asyncio.Lock()
        self._drain_timeout_seconds = 30.0

    @property
    def pipelines(self) -> dict[str, ScheduledPipeline]:
        """Get registered pipelines (read-only copy)."""
        return dict(self._pipelines)

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def register_pipeline(self, spec: "PipelineSpec") -> ScheduledPipeline:
        """
        Register a pipeline with the scheduler.

        Creates trigger engines for all triggers defined in the spec.

        Args:
            spec: Pipeline specification from YAML

        Returns:
            ScheduledPipeline container

        Raises:
            ValueError: If pipeline already registered
        """
        if spec.pipeline_id in self._pipelines:
            raise ValueError(f"Pipeline {spec.pipeline_id} already registered")

        # Create trigger engines
        triggers: list[TriggerEngine] = []

        for trigger_spec in spec.triggers or []:
            engine = create_trigger_engine(
                spec=trigger_spec,
                pipeline_id=spec.pipeline_id,
                syscalls=self._syscalls,
            )
            triggers.append(engine)

        scheduled = ScheduledPipeline(
            pipeline_id=spec.pipeline_id,
            spec=spec,
            triggers=triggers,
            state=PipelineState.REGISTERED,
        )

        self._pipelines[spec.pipeline_id] = scheduled

        logger.info(
            "Registered pipeline %s with %d triggers",
            spec.pipeline_id,
            len(triggers),
            extra={
                "pipeline_id": spec.pipeline_id,
                "trigger_count": len(triggers),
                "trigger_ids": [t.spec.id for t in triggers],
            },
        )

        return scheduled

    def unregister_pipeline(self, pipeline_id: str) -> bool:
        """
        Unregister a pipeline from the scheduler.

        Args:
            pipeline_id: ID of pipeline to unregister

        Returns:
            True if pipeline was removed, False if not found
        """
        if pipeline_id not in self._pipelines:
            return False

        scheduled = self._pipelines.pop(pipeline_id)

        logger.info(
            "Unregistered pipeline %s (executed %d times)",
            pipeline_id,
            scheduled.execution_count,
            extra={
                "pipeline_id": pipeline_id,
                "execution_count": scheduled.execution_count,
            },
        )

        return True

    async def start(self) -> None:
        """
        Start all registered trigger engines.

        This begins monitoring for trigger conditions.
        """
        async with self._lock:
            if self._running:
                logger.warning("Scheduler already running")
                return

            self._running = True

            for pipeline_id, scheduled in self._pipelines.items():
                await self._start_pipeline(scheduled)

            logger.info(
                "Started pipeline scheduler with %d pipelines",
                len(self._pipelines),
                extra={"pipeline_count": len(self._pipelines)},
            )

    async def _start_pipeline(self, scheduled: ScheduledPipeline) -> None:
        """Start all triggers for a pipeline."""
        scheduled.state = PipelineState.STARTING

        try:
            callback = self._make_trigger_callback(scheduled)

            for trigger in scheduled.triggers:
                await trigger.start(callback)

            scheduled.state = PipelineState.RUNNING

        except Exception as e:
            scheduled.state = PipelineState.ERROR
            logger.error(
                "Failed to start pipeline %s: %s",
                scheduled.pipeline_id,
                e,
                exc_info=True,
                extra={
                    "pipeline_id": scheduled.pipeline_id,
                    "error": str(e),
                },
            )

    async def stop(self) -> None:
        """
        Stop all trigger engines.

        Gracefully shuts down monitoring for all pipelines.
        """
        async with self._lock:
            if not self._running:
                return

            for scheduled in self._pipelines.values():
                await self._stop_pipeline(scheduled)

            self._running = False

            logger.info(
                "Stopped pipeline scheduler",
                extra={"pipeline_count": len(self._pipelines)},
            )

    async def _stop_pipeline(self, scheduled: ScheduledPipeline) -> None:
        """Stop all triggers for a pipeline."""
        scheduled.state = PipelineState.STOPPING

        for trigger in scheduled.triggers:
            try:
                await trigger.stop()
            except Exception as e:
                logger.error(
                    "Error stopping trigger %s: %s",
                    trigger.spec.id,
                    e,
                    extra={
                        "trigger_id": trigger.spec.id,
                        "pipeline_id": scheduled.pipeline_id,
                        "error": str(e),
                    },
                )

        scheduled.state = PipelineState.STOPPED

    async def hot_reload(
        self,
        new_specs: dict[str, "PipelineSpec"],
        affected_pipelines: set[str] | None = None,
    ) -> HotReloadResult:
        """
        Atomically swap trigger configuration.

        Per ADR-K004:
        1. Build new config in memory
        2. Acquire reload lock
        3. Cancel triggers for affected pipelines
        4. Drain in-flight runs (with timeout)
        5. Install new triggers
        6. Release lock

        Args:
            new_specs: New pipeline specifications
            affected_pipelines: Pipelines to reload (None = all in new_specs)

        Returns:
            HotReloadResult with success/error info
        """
        async with self._reload_lock:
            affected = affected_pipelines or set(new_specs.keys())
            result = HotReloadResult(affected_pipelines=list(affected))

            try:
                # Step 1: Cancel affected triggers
                for pipeline_id in affected:
                    if pipeline_id in self._pipelines:
                        await self._stop_pipeline(self._pipelines[pipeline_id])
                        result.removed += 1

                # Step 2: Drain in-flight runs
                await self._drain_in_flight(affected)

                # Step 3: Unregister old pipelines
                for pipeline_id in affected:
                    self._pipelines.pop(pipeline_id, None)

                # Step 4: Install new triggers
                for pipeline_id, spec in new_specs.items():
                    if pipeline_id in affected:
                        self.register_pipeline(spec)
                        if self._running:
                            await self._start_pipeline(self._pipelines[pipeline_id])
                        result.added += 1

                result.success = True
                logger.info(
                    "Hot reload complete: %d affected, %d added, %d removed",
                    len(affected),
                    result.added,
                    result.removed,
                    extra={
                        "affected": list(affected),
                        "added": result.added,
                        "removed": result.removed,
                    },
                )

            except Exception as e:
                result.success = False
                result.error = str(e)
                logger.error(
                    "Hot reload failed: %s",
                    e,
                    exc_info=True,
                    extra={"error": str(e), "affected": list(affected)},
                )

            return result

    async def _drain_in_flight(self, pipeline_ids: set[str]) -> None:
        """
        Wait for in-flight runs to complete.

        Args:
            pipeline_ids: Pipeline IDs to drain
        """
        gate = get_single_flight_gate()
        in_flight = [pid for pid in pipeline_ids if gate.is_running(pid)]

        if not in_flight:
            return

        logger.info(
            "Draining %d in-flight runs...",
            len(in_flight),
            extra={"in_flight": in_flight},
        )

        # Wait with timeout
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._drain_timeout_seconds

        while in_flight and loop.time() < deadline:
            await asyncio.sleep(0.5)
            in_flight = [pid for pid in in_flight if gate.is_running(pid)]

        if in_flight:
            logger.warning(
                "Drain timeout: %d runs still in flight: %s",
                len(in_flight),
                in_flight,
                extra={"timed_out": in_flight},
            )

    def fire_manual_trigger(
        self,
        pipeline_id: str,
        trigger_id: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Manually fire a trigger.

        Args:
            pipeline_id: Pipeline containing the trigger
            trigger_id: ID of the trigger to fire
            context: Optional context dict to include in the trigger event.
                     For P03, this can include:
                     - reason: Human-readable reason for manual trigger
                     - options: Dict with skip_r5, max_events, space_id, tenant_id

        Returns:
            True if trigger was fired, False if not found or not manual
        """
        scheduled = self._pipelines.get(pipeline_id)
        if not scheduled:
            logger.warning(
                "Cannot fire trigger: pipeline %s not found",
                pipeline_id,
                extra={"pipeline_id": pipeline_id, "trigger_id": trigger_id},
            )
            return False

        for trigger in scheduled.triggers:
            if trigger.spec.id == trigger_id:
                if isinstance(trigger, ManualTriggerEngine):
                    return trigger.fire(context=context)
                else:
                    logger.warning(
                        "Trigger %s is not manual type",
                        trigger_id,
                        extra={
                            "pipeline_id": pipeline_id,
                            "trigger_id": trigger_id,
                            "trigger_type": trigger.spec.type.value,
                        },
                    )
                    return False

        logger.warning(
            "Trigger %s not found in pipeline %s",
            trigger_id,
            pipeline_id,
            extra={"pipeline_id": pipeline_id, "trigger_id": trigger_id},
        )
        return False

    def get_pipeline(self, pipeline_id: str) -> ScheduledPipeline | None:
        """Get a registered pipeline by ID."""
        return self._pipelines.get(pipeline_id)

    def get_trigger_stats(
        self,
        pipeline_id: str | None = None,
    ) -> dict[str, dict]:
        """
        Get statistics for trigger engines.

        Args:
            pipeline_id: Optional filter by pipeline

        Returns:
            Dict mapping trigger_id to stats
        """
        stats = {}

        pipelines = (
            [self._pipelines[pipeline_id]]
            if pipeline_id and pipeline_id in self._pipelines
            else self._pipelines.values()
        )

        for scheduled in pipelines:
            for trigger in scheduled.triggers:
                stats[trigger.spec.id] = {
                    "pipeline_id": scheduled.pipeline_id,
                    "type": trigger.spec.type.value,
                    "is_running": trigger.is_running,
                    "fire_count": trigger.fire_count,
                    "last_fired": trigger.last_fired,
                }

        return stats

    def _make_trigger_callback(self, scheduled: ScheduledPipeline) -> TriggerCallback:
        """Create a callback for trigger events."""

        def callback(event: TriggerEvent) -> None:
            scheduled.execution_count += 1
            scheduled.last_execution = event.fired_at

            logger.info(
                "Trigger %s fired for pipeline %s (execution #%d)",
                event.trigger_id,
                event.pipeline_id,
                scheduled.execution_count,
                extra={
                    "trigger_id": event.trigger_id,
                    "pipeline_id": event.pipeline_id,
                    "execution_count": scheduled.execution_count,
                    "context": event.context,
                },
            )

            self._executor(scheduled, event)

        return callback

    def _default_executor(
        self,
        scheduled: ScheduledPipeline,
        event: TriggerEvent,
    ) -> None:
        """Default executor - logs execution (no-op)."""
        logger.debug(
            "Default executor: would execute %s (trigger=%s)",
            scheduled.pipeline_id,
            event.trigger_id,
            extra={
                "pipeline_id": scheduled.pipeline_id,
                "trigger_id": event.trigger_id,
            },
        )


# Singleton instance
_scheduler_instance: PipelineScheduler | None = None


def get_pipeline_scheduler() -> PipelineScheduler | None:
    """Get the global PipelineScheduler instance."""
    return _scheduler_instance


def set_pipeline_scheduler(scheduler: PipelineScheduler) -> None:
    """Set the global PipelineScheduler instance."""
    global _scheduler_instance
    _scheduler_instance = scheduler


def reset_pipeline_scheduler() -> None:
    """Reset the global scheduler (for testing)."""
    global _scheduler_instance
    _scheduler_instance = None
