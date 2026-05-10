"""
k1.orchestrator.workflows.gap_detector -- ProactiveGapDetector (4.2.7).

Subscribes to ``k1.fabric.capability.contract_updated.v1`` and
proactively re-compiles affected workflows to detect gaps BEFORE
the next scheduled run.

Design:
  - Event handler is SYNCHRONOUS (IEventSubscriptionPort handlers
    are sync per 1.4.7). Handler enqueues capability_name into an
    asyncio.Queue; ``_process_loop()`` drains and debounces.
  - Debounce: if the same capability fires within 5 s, only the
    latest event is processed (prevents K0 sync flood).
  - Compile is a real call (not dry-run) -- WorkflowCompiler.compile()
    already returns CompilationResult with gap details. Since
    WorkflowSpec is frozen, compile() never mutates the stored spec.
  - Gap classification (SPEC-9) is done by the compiler:
    * CAPABILITY_REMOVED / PERMISSION_CHANGE -> LARGE (PENDING).
    * Auto-resolved params -> SMALL (AUTO_RESOLVED).
  - LARGE gap actions: save gap, deactivate workflow, emit HIL event.
  - SMALL gap actions: emit auto-resolved notification.
  - If no active workflows reference the updated capability, handler
    is a no-op (fast path).
  - Follows K0 P06 curiosity pattern: proactive, non-blocking.

Constructor deps (5):
  registry -- WorkflowRegistry (list_active, save for deactivation)
  compiler -- WorkflowCompiler (compile for gap detection)
  storage  -- IWorkflowStoragePort (save_gap, save_workflow)
  events   -- IEventSubscriptionPort (subscribe)
  delta    -- IDeltaEmitPort (emit gap notifications)

Anti-hallucination rules:
  - compile() does NOT modify stored WorkflowSpecs (frozen).
  - Debounce window is 5 s per capability (not global).
  - Handler is SYNC -- async work goes through asyncio.Queue.
  - SubscriptionHandle used for cleanup in stop().

Exports:
  ProactiveGapDetector
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import replace
from typing import Any, Dict, Optional

from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import ProactiveGapStatus
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONTRACT_UPDATED_TOPIC = "k1.fabric.capability.contract_updated.v1"
_DEBOUNCE_SECONDS = 5.0
# M5.4.3: bound the in-memory queue so that a misbehaving publisher (or a
# very chatty test harness) cannot cause unbounded memory growth.
_QUEUE_MAXSIZE = 1024


# ---------------------------------------------------------------------------
# ProactiveGapDetector
# ---------------------------------------------------------------------------


class ProactiveGapDetector:
    """Proactively detect workflow gaps on capability contract changes (4.2.7).

    Lifecycle:
      ``start()``  -- subscribes to contract update events, starts process loop.
      ``stop()``   -- unsubscribes, cancels process loop.

    On each contract update event:
      1. Extract capability_name from payload.
      2. Find active workflows that reference this capability.
      3. Re-compile each affected workflow.
      4. For LARGE gaps: save gap, deactivate workflow, emit HIL event.
      5. For SMALL/auto-resolved: emit notification.
    """

    def __init__(
        self,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        storage: IWorkflowStoragePort,
        events: IEventSubscriptionPort,
        delta: IDeltaEmitPort,
        gap_scan_cooldown_s: float = 0.0,
        gap_scan_concurrency: int = 5,
    ) -> None:
        self._registry = registry
        self._compiler = compiler
        self._storage = storage
        self._events = events
        self._delta = delta

        # Internal async queue for capability names from sync handler.
        # M5.4.3: bounded so a runaway publisher cannot OOM the kernel.
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        # Debounce tracker: capability_name -> last_enqueued_timestamp
        self._last_seen: Dict[str, float] = {}
        # M5.4.3: per-workflow cooldown so a single capability change
        # cannot retrigger a dry-run compile for the same workflow within
        # this window. Independent from the per-capability debounce above.
        self._workflow_last_checked: Dict[str, float] = {}
        self._gap_scan_cooldown_s: float = max(0.0, float(gap_scan_cooldown_s))
        # M5.4.4: bound _check_workflow() fan-out concurrency.
        self._gap_scan_semaphore: asyncio.Semaphore = asyncio.Semaphore(
            max(1, int(gap_scan_concurrency))
        )
        # Subscription handle for cleanup
        self._subscription_handle: Optional[object] = None
        # Background processing task
        self._process_task: Optional[asyncio.Task[None]] = None
        self._running = False

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Subscribe to contract update events and start processing loop.

        Idempotent: calling start() twice is a no-op.
        """
        if self._running:
            return

        self._running = True
        self._subscription_handle = self._events.subscribe(
            _CONTRACT_UPDATED_TOPIC,
            self._on_contract_updated,
        )
        self._process_task = asyncio.create_task(self._process_loop())

        logger.info(
            "ProactiveGapDetector: started (subscribed to %s)",
            _CONTRACT_UPDATED_TOPIC,
        )

    async def stop(self) -> None:
        """Unsubscribe and cancel processing loop.

        Idempotent: calling stop() twice is a no-op.
        """
        if not self._running:
            return

        self._running = False

        if self._subscription_handle is not None:
            self._events.unsubscribe(self._subscription_handle)
            self._subscription_handle = None

        if self._process_task is not None:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None

        logger.info("ProactiveGapDetector: stopped")

    # -- Sync event handler (called by IEventSubscriptionPort) ---------------

    def _on_contract_updated(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """Sync handler for contract update events.

        Extracts capability_name and enqueues for async processing.
        Debounce: if same capability was enqueued within 5 s, skip.
        """
        capability_name = payload.get("capability_name", "")
        if not capability_name:
            logger.debug("ProactiveGapDetector: ignoring event with no capability_name")
            return

        now = time.time()
        last = self._last_seen.get(capability_name, 0.0)

        if now - last < _DEBOUNCE_SECONDS:
            logger.debug(
                "ProactiveGapDetector: debounced '%s' (%.1fs since last)",
                capability_name,
                now - last,
            )
            return

        self._last_seen[capability_name] = now

        try:
            self._queue.put_nowait(capability_name)
        except asyncio.QueueFull:
            logger.warning(
                "ProactiveGapDetector: queue full, dropping '%s'",
                capability_name,
            )

    # -- Async processing loop -----------------------------------------------

    async def _process_loop(self) -> None:
        """Drain the queue and process capability updates."""
        while self._running:
            try:
                capability_name = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._process_capability(capability_name)
            except Exception:
                logger.exception(
                    "ProactiveGapDetector: error processing '%s'",
                    capability_name,
                )

    async def _process_capability(self, capability_name: str) -> None:
        """Find affected workflows and re-compile for gap detection.

        Steps:
          1. List active workflows referencing this capability.
          2. For each: compile and inspect gaps.
          3. Handle LARGE/SMALL gaps.
        """
        active_specs = await self._registry.list_active()

        # Filter to workflows that reference this capability
        affected = [
            spec
            for spec in active_specs
            if any(s.capability == capability_name for s in spec.steps)
        ]

        if not affected:
            logger.debug(
                "ProactiveGapDetector: no active workflows reference '%s'",
                capability_name,
            )
            return

        logger.info(
            "ProactiveGapDetector: %d workflow(s) affected by '%s' update",
            len(affected),
            capability_name,
        )

        for spec in affected:
            # M5.4.4: bound concurrent dry-run compiles.
            async with self._gap_scan_semaphore:
                await self._check_workflow(spec, capability_name)

    async def _check_workflow(
        self,
        spec: Any,
        capability_name: str,
    ) -> None:
        """Re-compile a single workflow and handle detected gaps.

        WorkflowSpec is frozen, so compile() creates new instances
        internally -- no mutation of stored data.
        """
        # M5.4.3: per-workflow cooldown gate. Prevents a single
        # capability event from triggering rescans across closely-spaced
        # contract updates affecting the same workflow.
        if self._gap_scan_cooldown_s > 0:
            now_ts = time.time()
            last_check = self._workflow_last_checked.get(spec.workflow_id, 0.0)
            if now_ts - last_check < self._gap_scan_cooldown_s:
                logger.debug(
                    "ProactiveGapDetector: cooldown skip for workflow '%s' "
                    "(%.1fs since last check, cooldown=%.1fs)",
                    spec.workflow_id,
                    now_ts - last_check,
                    self._gap_scan_cooldown_s,
                )
                return
            self._workflow_last_checked[spec.workflow_id] = now_ts

        trace_id = str(uuid.uuid4())

        compilation = await self._compiler.compile(spec)

        if compilation.success:
            # No LARGE gaps -- check for auto-resolved
            if compilation.auto_resolved:
                await self._delta.emit(
                    "k1.orchestration.gap.auto_resolved",
                    {
                        "workflow_id": spec.workflow_id,
                        "capability": capability_name,
                        "change_summary": (
                            f"{len(compilation.auto_resolved)} param(s) auto-resolved"
                        ),
                        "auto_resolved": compilation.auto_resolved,
                    },
                    trace_id,
                )
                logger.info(
                    "ProactiveGapDetector: auto-resolved %d param(s) for "
                    "workflow '%s' (capability: '%s')",
                    len(compilation.auto_resolved),
                    spec.workflow_id,
                    capability_name,
                )
            return

        # -- LARGE gaps detected -- deactivate workflow + notify -----------

        pending_gaps = [g for g in compilation.gaps if g.status == ProactiveGapStatus.PENDING]

        # Save each PENDING gap
        for gap in pending_gaps:
            await self._storage.save_gap(gap)

        # Deactivate workflow (spec is frozen -> create new with active=False)
        deactivated = replace(spec, active=False)
        await self._storage.save_workflow(deactivated)

        # Emit HIL notification for large gaps
        await self._delta.emit(
            "k1.orchestration.gap.detected",
            {
                "workflow_id": spec.workflow_id,
                "workflow_name": spec.name,
                "capability": capability_name,
                "gap_count": len(pending_gaps),
                "gap_types": list({g.gap_type for g in pending_gaps}),
                "action": "workflow_deactivated",
            },
            trace_id,
        )

        logger.warning(
            "ProactiveGapDetector: deactivated workflow '%s' -- "
            "%d LARGE gap(s) detected (capability: '%s')",
            spec.workflow_id,
            len(pending_gaps),
            capability_name,
        )
