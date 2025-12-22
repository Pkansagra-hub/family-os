"""
Scheduler Audit Logging - Structured audit events for triggers.

All scheduler trigger events are logged with structured JSON for auditability.
Follows the same pattern as k0/fabric/audit.py for consistency.

Related:
- k0/scheduler/concurrency.py: SingleFlightGate
- k0/scheduler/scheduler.py: PipelineScheduler
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

# Dedicated audit logger - separate namespace for audit filtering
audit_logger = logging.getLogger("k0.scheduler.audit")


@dataclass(frozen=True, slots=True)
class TriggerFiredEvent:
    """Logged when trigger activates pipeline."""

    event: str
    timestamp: str
    pipeline_id: str
    trigger_id: str
    trigger_type: str
    execution_count: int = 0


@dataclass(frozen=True, slots=True)
class TriggerSkippedEvent:
    """Logged when trigger is skipped due to overlap policy."""

    event: str
    timestamp: str
    pipeline_id: str
    trigger_id: str
    trigger_type: str
    reason: str  # "already_running", "coalesced"


@dataclass(frozen=True, slots=True)
class TriggerQueuedEvent:
    """Logged when trigger is queued for later execution."""

    event: str
    timestamp: str
    pipeline_id: str
    trigger_id: str
    trigger_type: str
    replaced_trigger_id: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineRunStartEvent:
    """Logged when pipeline execution starts."""

    event: str
    timestamp: str
    pipeline_id: str
    trigger_id: str
    trigger_type: str
    run_number: int


@dataclass(frozen=True, slots=True)
class PipelineRunCompleteEvent:
    """Logged when pipeline execution completes."""

    event: str
    timestamp: str
    pipeline_id: str
    trigger_id: str
    duration_ms: float
    success: bool
    error: str | None = None


class SchedulerAuditor:
    """
    Audit logger for scheduler events.

    Provides structured logging for all trigger and pipeline execution events.
    Uses a dedicated logger namespace (k0.scheduler.audit) for easy filtering.

    Example:
        auditor = get_scheduler_auditor()
        auditor.log_trigger_fired("P03", "trigger-1", "interval", 1)
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Initialize the auditor with optional custom logger."""
        self._logger = logger or audit_logger

    def _now_iso(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def log_trigger_fired(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
        execution_count: int = 0,
    ) -> None:
        """
        Log trigger activation.

        Args:
            pipeline_id: ID of the pipeline being triggered
            trigger_id: ID of the trigger that fired
            trigger_type: Type of trigger (interval, threshold, manual)
            execution_count: Total execution count for this pipeline
        """
        event = TriggerFiredEvent(
            event="trigger.fired",
            timestamp=self._now_iso(),
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            execution_count=execution_count,
        )
        self._logger.info(asdict(event))

    def log_trigger_skipped(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
        reason: str,
    ) -> None:
        """
        Log trigger skip.

        Args:
            pipeline_id: ID of the pipeline
            trigger_id: ID of the trigger that was skipped
            trigger_type: Type of trigger
            reason: Why it was skipped (already_running, coalesced)
        """
        event = TriggerSkippedEvent(
            event="trigger.skipped",
            timestamp=self._now_iso(),
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            reason=reason,
        )
        self._logger.warning(asdict(event))

    def log_trigger_queued(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
        replaced_trigger_id: str | None = None,
    ) -> None:
        """
        Log trigger queued for later execution.

        Args:
            pipeline_id: ID of the pipeline
            trigger_id: ID of the trigger that was queued
            trigger_type: Type of trigger
            replaced_trigger_id: ID of trigger that was coalesced (if any)
        """
        event = TriggerQueuedEvent(
            event="trigger.queued",
            timestamp=self._now_iso(),
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            replaced_trigger_id=replaced_trigger_id,
        )
        self._logger.info(asdict(event))

    def log_pipeline_run_start(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
        run_number: int,
    ) -> None:
        """
        Log pipeline execution start.

        Args:
            pipeline_id: ID of the pipeline
            trigger_id: ID of the trigger that initiated the run
            trigger_type: Type of trigger
            run_number: Sequential run number for this pipeline
        """
        event = PipelineRunStartEvent(
            event="pipeline.run.start",
            timestamp=self._now_iso(),
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            run_number=run_number,
        )
        self._logger.info(asdict(event))

    def log_pipeline_run_complete(
        self,
        pipeline_id: str,
        trigger_id: str,
        duration_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """
        Log pipeline execution completion.

        Args:
            pipeline_id: ID of the pipeline
            trigger_id: ID of the trigger that initiated the run
            duration_ms: Execution duration in milliseconds
            success: Whether the run succeeded
            error: Error message if failed
        """
        event = PipelineRunCompleteEvent(
            event="pipeline.run.complete",
            timestamp=self._now_iso(),
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            duration_ms=round(duration_ms, 3),
            success=success,
            error=error,
        )
        if success:
            self._logger.info(asdict(event))
        else:
            self._logger.error(asdict(event))


# Global auditor instance
_auditor: SchedulerAuditor | None = None


def get_scheduler_auditor() -> SchedulerAuditor:
    """Get the global scheduler auditor."""
    global _auditor
    if _auditor is None:
        _auditor = SchedulerAuditor()
    return _auditor


def reset_scheduler_auditor() -> None:
    """Reset the global auditor (for testing)."""
    global _auditor
    _auditor = None
