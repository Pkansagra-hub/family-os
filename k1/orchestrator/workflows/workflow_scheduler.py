"""
k1.orchestrator.workflows.workflow_scheduler -- WorkflowScheduler (4.2.1).

Periodic tick-based scheduler that fires due workflow triggers and enqueues
WorkflowRunRequest messages into the Orchestrator mailbox.

Design:
  - Tick interval defaults to 1 s (cron precision +/- 1 s, acceptable for V1).
  - Uses croniter for CRON next-fire computation with timezone awareness.
  - EVENT and MANUAL triggers set next_fire = MAX_FLOAT (no schedule).
  - Crash recovery (ADR-1.1.9): first tick fires any missed triggers
    (next_fire_time < now), then computes the correct next fire time.
  - MailboxFullError is caught per-trigger: logged and retried on the
    next tick (trigger state is NOT updated, so it remains "due").

Constructor dependency chain (OrchestratorFactory step ?):
  1. storage: IWorkflowStoragePort -- for get_due_triggers, update_trigger_state, get_workflow
  2. mailbox: IMailboxPort -- for enqueue(WorkflowRunRequest, priority="INTERACTIVE")
  3. state_port: IStateReadPort -- reserved for future user-timezone override
  4. clock: SystemClock -- for utc_now()
  5. tick_interval_s: float -- defaults to 1.0

Anti-hallucination rules:
  - Priority is INTERACTIVE (per SEM-3), NEVER REALTIME.
  - get_due_triggers() returns (workflow_id, TriggerSpec) pairs.
  - Scheduler must look up WorkflowSpec to obtain version for WorkflowRunRequest.
  - compute_next_fire() is a module-level pure function.
  - _tick() catches all per-trigger exceptions to avoid one bad trigger
    blocking others.

Exports:
  WorkflowScheduler, compute_next_fire
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter

from k1.orchestrator.ports.mailbox_port import IMailboxPort, MailboxFullError
from k1.orchestrator.ports.state_read_port import IStateReadPort
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import TriggerSpec, TriggerType, WorkflowRunRequest
from k1.orchestrator.workflows.system_clock import SystemClock

logger = logging.getLogger(__name__)

# Sentinel: next fire time for non-scheduled triggers (EVENT, MANUAL).
MAX_FLOAT: float = sys.float_info.max


# ---------------------------------------------------------------------------
# Pure helper -- compute next fire time
# ---------------------------------------------------------------------------


def compute_next_fire(trigger: TriggerSpec, now: float) -> float:
    """Compute the next fire time for a trigger after *now*.

    Args:
        trigger: The TriggerSpec describing the trigger type and schedule.
        now: Current UTC timestamp (seconds since epoch).

    Returns:
        Next fire time as a UTC float timestamp.
        EVENT and MANUAL triggers return ``MAX_FLOAT`` (no schedule).

    Raises:
        ValueError: If a CRON trigger has an invalid schedule expression.
    """
    if trigger.type == TriggerType.CRON:
        if not trigger.schedule:
            raise ValueError("CRON trigger requires a schedule expression")
        # Build timezone-aware base time for croniter
        tz_info = ZoneInfo(trigger.timezone or "UTC")
        base_dt = datetime.fromtimestamp(now, tz=tz_info)
        cron = croniter(trigger.schedule, base_dt)
        next_dt: datetime = cron.get_next(datetime)
        return next_dt.timestamp()

    # EVENT and MANUAL are not time-scheduled
    return MAX_FLOAT


# ---------------------------------------------------------------------------
# WorkflowScheduler
# ---------------------------------------------------------------------------


class WorkflowScheduler:
    """Periodic tick scheduler for workflow triggers (4.2.1).

    Lifecycle::

        scheduler = WorkflowScheduler(storage, mailbox, state_port, clock)
        await scheduler.start()   # begins tick loop
        ...
        await scheduler.stop()    # cancels tick task

    Each tick:
      1. ``now = clock.utc_now()``
      2. Query due triggers (``next_fire_time <= now AND enabled``).
      3. For each due trigger, build a ``WorkflowRunRequest`` and enqueue
         it to the mailbox at **INTERACTIVE** priority.
      4. Update trigger state (``next_fire``, ``last_fire``).

    Crash recovery (ADR-1.1.9): On the very first tick after start,
    any trigger whose ``next_fire_time < now`` is immediately fired.
    This prevents silent skips after a restart.
    """

    def __init__(
        self,
        storage: IWorkflowStoragePort,
        mailbox: IMailboxPort,
        state_port: IStateReadPort,
        clock: SystemClock,
        tick_interval_s: float = 1.0,
    ) -> None:
        self._storage = storage
        self._mailbox = mailbox
        self._state_port = state_port
        self._clock = clock
        self._tick_interval_s = tick_interval_s
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start the periodic tick loop.

        Creates an ``asyncio.Task`` that runs ``_tick_loop()`` until
        ``stop()`` is called.  Calling ``start()`` when already running
        is a no-op.
        """
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())
        logger.info("WorkflowScheduler started (tick_interval=%.1fs)", self._tick_interval_s)

    async def stop(self) -> None:
        """Cancel the tick task and wait for it to finish.

        Calling ``stop()`` when not running is a no-op.
        """
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("WorkflowScheduler stopped")

    @property
    def running(self) -> bool:
        """True while the tick loop is active."""
        return self._running

    # -- Core loop -----------------------------------------------------------

    async def _tick_loop(self) -> None:
        """Run ``_tick()`` in a loop until cancelled."""
        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self._tick_interval_s)
        except asyncio.CancelledError:
            pass

    async def _tick(self) -> None:
        """Single scheduler tick: fire all due triggers.

        Per-trigger errors (storage lookup, mailbox full, etc.) are
        caught and logged so that one bad trigger does not block others.
        If a trigger fails to enqueue (MailboxFullError), we intentionally
        do NOT update its state -- it remains "due" and will be retried
        on the next tick.
        """
        now = self._clock.utc_now()
        try:
            due = await self._storage.get_due_triggers(now)
        except Exception:
            logger.exception("WorkflowScheduler: failed to query due triggers")
            return

        for workflow_id, trigger in due:
            try:
                await self._fire_trigger(workflow_id, trigger, now)
            except MailboxFullError:
                # Do not update trigger state -- retry next tick.
                logger.warning(
                    "WorkflowScheduler: mailbox full, deferring trigger "
                    "for workflow_id=%s to next tick",
                    workflow_id,
                )
            except Exception:
                logger.exception(
                    "WorkflowScheduler: error firing trigger for " "workflow_id=%s",
                    workflow_id,
                )

    # -- Per-trigger dispatch ------------------------------------------------

    async def _fire_trigger(
        self,
        workflow_id: str,
        trigger: TriggerSpec,
        now: float,
    ) -> None:
        """Build a WorkflowRunRequest, enqueue it, and advance trigger state.

        Raises:
            MailboxFullError: Propagated to ``_tick()`` for retry logic.
        """
        # Look up the workflow to obtain version (required by WorkflowRunRequest).
        spec = await self._storage.get_workflow(workflow_id)
        if spec is None:
            logger.warning(
                "WorkflowScheduler: workflow %s not found, skipping trigger",
                workflow_id,
            )
            return
        if not spec.active:
            logger.debug(
                "WorkflowScheduler: workflow %s inactive, skipping trigger",
                workflow_id,
            )
            return

        request = WorkflowRunRequest(
            workflow_id=workflow_id,
            version=spec.version,
            trigger_type=trigger.type,
            trace_id=str(uuid4()),
            trigger_context={"triggered_at": now},
            priority="INTERACTIVE",
        )

        # Enqueue -- MailboxFullError propagates to caller.
        self._mailbox.enqueue(request, priority="INTERACTIVE")

        logger.info(
            "WorkflowScheduler: fired trigger for workflow_id=%s " "(type=%s, request_id=%s)",
            workflow_id,
            trigger.type.value,
            request.request_id,
        )

        # Advance trigger state only AFTER successful enqueue.
        next_fire = compute_next_fire(trigger, now)
        await self._storage.update_trigger_state(
            workflow_id,
            next_fire=next_fire,
            last_fire=now,
        )
