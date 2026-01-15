"""
Scheduler Concurrency Controls.

Implements single-flight gating to prevent concurrent runs of the same pipeline.

Per ADR-K004 Concurrency Policy:
- INTERVAL triggers: SKIP if already running
- THRESHOLD/MANUAL triggers: QUEUE (max depth 1, coalesce)

Related:
- k0/scheduler/scheduler.py: PipelineScheduler
- k0/scheduler/triggers.py: TriggerEngine implementations
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OverlapPolicy(str, Enum):
    """What to do when trigger fires while pipeline is running."""

    SKIP = "skip"  # Drop this trigger (interval behavior)
    QUEUE = "queue"  # Queue one pending run (threshold/manual behavior)


@dataclass
class PendingRun:
    """A queued trigger waiting to run."""

    trigger_id: str
    trigger_type: str
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RunStats:
    """Statistics for a pipeline's run history."""

    total_runs: int = 0
    total_skipped: int = 0
    total_queued: int = 0
    last_run_at: datetime | None = None
    last_skip_at: datetime | None = None


class SingleFlightGate:
    """
    Ensures only one run per pipeline at a time.

    Per ADR-K004 Concurrency Policy:
    - INTERVAL triggers: SKIP if already running
    - THRESHOLD/MANUAL triggers: QUEUE (max depth 1, coalesce)

    Example:
        gate = SingleFlightGate()
        if await gate.try_acquire("P03", "trigger-1", "interval"):
            task = asyncio.create_task(run_pipeline(...))
            gate.mark_running("P03", task)
            try:
                await task
            finally:
                pending = await gate.release("P03")
                if pending:
                    # Handle queued run
                    pass
    """

    def __init__(self) -> None:
        """Initialize the single-flight gate."""
        self._running: dict[str, asyncio.Task] = {}
        self._pending: dict[str, PendingRun | None] = {}
        self._stats: dict[str, RunStats] = {}
        self._lock = asyncio.Lock()

    async def try_acquire(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
    ) -> bool:
        """
        Try to acquire the run slot for a pipeline.

        Args:
            pipeline_id: ID of the pipeline
            trigger_id: ID of the trigger firing
            trigger_type: Type of trigger (interval, threshold, manual)

        Returns:
            True if acquired and pipeline can run, False if skipped/queued
        """
        async with self._lock:
            stats = self._stats.setdefault(pipeline_id, RunStats())

            if pipeline_id in self._running:
                # Already running - apply overlap policy
                policy = self._get_overlap_policy(trigger_type)

                if policy == OverlapPolicy.SKIP:
                    stats.total_skipped += 1
                    stats.last_skip_at = datetime.now(timezone.utc)
                    logger.warning(
                        "Skipping trigger %s for %s: already running",
                        trigger_id,
                        pipeline_id,
                        extra={
                            "pipeline_id": pipeline_id,
                            "trigger_id": trigger_id,
                            "trigger_type": trigger_type,
                            "action": "skip",
                        },
                    )
                    return False

                else:  # QUEUE
                    # Coalesce: replace any existing pending
                    existing = self._pending.get(pipeline_id)
                    if existing:
                        logger.info(
                            "Coalescing trigger %s for %s: replacing pending %s",
                            trigger_id,
                            pipeline_id,
                            existing.trigger_id,
                            extra={
                                "pipeline_id": pipeline_id,
                                "trigger_id": trigger_id,
                                "replaced_trigger_id": existing.trigger_id,
                                "action": "coalesce",
                            },
                        )
                    else:
                        logger.info(
                            "Queuing trigger %s for %s: already running",
                            trigger_id,
                            pipeline_id,
                            extra={
                                "pipeline_id": pipeline_id,
                                "trigger_id": trigger_id,
                                "action": "queue",
                            },
                        )

                    self._pending[pipeline_id] = PendingRun(
                        trigger_id=trigger_id,
                        trigger_type=trigger_type,
                    )
                    stats.total_queued += 1
                    return False

            # Not running - can acquire slot
            return True

    def mark_running(self, pipeline_id: str, task: asyncio.Task) -> None:
        """
        Mark a pipeline as running.

        Args:
            pipeline_id: ID of the pipeline
            task: The asyncio.Task running the pipeline
        """
        self._running[pipeline_id] = task
        stats = self._stats.setdefault(pipeline_id, RunStats())
        stats.total_runs += 1
        stats.last_run_at = datetime.now(timezone.utc)

        logger.debug(
            "Pipeline %s marked as running (run #%d)",
            pipeline_id,
            stats.total_runs,
            extra={
                "pipeline_id": pipeline_id,
                "total_runs": stats.total_runs,
            },
        )

    async def release(self, pipeline_id: str) -> PendingRun | None:
        """
        Release the run slot for a pipeline.

        Args:
            pipeline_id: ID of the pipeline

        Returns:
            Pending run if one was queued, None otherwise
        """
        async with self._lock:
            self._running.pop(pipeline_id, None)
            pending = self._pending.pop(pipeline_id, None)

            if pending:
                logger.info(
                    "Released %s with pending run from trigger %s",
                    pipeline_id,
                    pending.trigger_id,
                    extra={
                        "pipeline_id": pipeline_id,
                        "pending_trigger_id": pending.trigger_id,
                    },
                )
            else:
                logger.debug(
                    "Released %s (no pending runs)",
                    pipeline_id,
                    extra={"pipeline_id": pipeline_id},
                )

            return pending

    def is_running(self, pipeline_id: str) -> bool:
        """
        Check if pipeline is currently running.

        Args:
            pipeline_id: ID of the pipeline

        Returns:
            True if pipeline has a running task
        """
        return pipeline_id in self._running

    def get_stats(self, pipeline_id: str) -> RunStats | None:
        """
        Get run statistics for a pipeline.

        Args:
            pipeline_id: ID of the pipeline

        Returns:
            RunStats if available, None otherwise
        """
        return self._stats.get(pipeline_id)

    def get_all_stats(self) -> dict[str, RunStats]:
        """
        Get run statistics for all pipelines.

        Returns:
            Dict mapping pipeline_id to RunStats
        """
        return dict(self._stats)

    def _get_overlap_policy(self, trigger_type: str) -> OverlapPolicy:
        """
        Get overlap policy based on trigger type.

        Args:
            trigger_type: Type of trigger

        Returns:
            OverlapPolicy for this trigger type
        """
        if trigger_type.lower() == "interval":
            return OverlapPolicy.SKIP
        else:
            # THRESHOLD, MANUAL, and future types use QUEUE
            return OverlapPolicy.QUEUE


# Global gate instance
_gate: SingleFlightGate | None = None


def get_single_flight_gate() -> SingleFlightGate:
    """Get the global single-flight gate."""
    global _gate
    if _gate is None:
        _gate = SingleFlightGate()
    return _gate


def reset_single_flight_gate() -> None:
    """Reset the global gate (for testing)."""
    global _gate
    _gate = None
