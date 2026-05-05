"""PlannerAgent -- single-threaded async coordinator [F02].

Owns the mailbox dequeue loop, plan lock (V1 single-plan), cancel set,
and lifecycle phases (INIT, SHUTDOWN, CRASH_RECOVERY).  PlannerAgent is
the entry point of the Planner module.  It receives a fully-wired
PipelineController via constructor injection and drives it for each plan.

Design decisions
----------------
- PlannerAgent is a Layer 3 component (SS30.6).  It imports from
  Layer 2 (PipelineController), Layer 1 (ports), Layer 0 (types/config).
- PlannerAgent does NOT create services -- that is PlannerFactory's
  responsibility (M6).  PlannerAgent receives a fully-wired
  PipelineController via constructor injection.
- V1 concurrency: one plan at a time via ``asyncio.Lock`` (SS24.1).
  Mailbox queues additional requests (FIFO, max depth 5).
- Lifecycle phases: INIT (once at startup), PLAN_START (per plan),
  STAGE_TRANSITION (per stage boundary -- delegated to
  PipelineController), PLAN_END (per plan -- delegated to
  PipelineController), SHUTDOWN (once at stop), CRASH_RECOVERY
  (once at startup if WAL has in-flight plan).
- Cancel protocol (SS24.2): cooperative flag-based, checked between
  stages.  ``_cancel_set: Set[str]`` managed by PlannerAgent, passed
  to PipelineController via ``cancel_check`` closure.

Invariants enforced
-------------------
- V1 single-plan exclusion via ``asyncio.Lock``.
- Cancel set is the sole source of truth for pending cancellations.
- ``_running`` flag provides clean shutdown signalling.

Import graph (Layer 3)
----------------------
k1.planner.planner_agent
  -> k1.planner.pipeline_controller  (PipelineController)
  -> k1.planner.config               (PlannerConfig)
  -> k1.planner.ports.mailbox_port   (IMailboxPort)
  -> k1.planner.ports.event_port     (IEventPort)
  -> k1.fabric.ports.event_port      (SubscriptionHandle)
  -> k1.orchestrator.types           (MicroReplanRequest, CommittedPlan)
  -> asyncio, logging, typing

NEVER import from factory.py (higher layer).

References
----------
- planner.md Section 3.1   (Planner Core -- PlannerAgent)
- planner.md Section 4     (Mailbox & Message Protocol)
- planner.md Section 23    (Lifecycle -- 6 Phases)
- planner.md Section 24    (Concurrency Model)
- planner.md Section 24.1  (V1 Single Plan)
- planner.md Section 24.2  (Cancellation)
- planner.md Section 24.3  (Micro-Replan Concurrency)
- planner.md Section 30.5.1 F02
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, List, Optional, Set

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.types import CommittedPlan, MicroReplanRequest, PlanRequest
from k1.planner.config import PlannerConfig
from k1.planner.events import (
    TOPIC_PLAN_CANCEL,
    TOPIC_PLAN_CANCELLED,
    TOPIC_PLAN_FAILED,
    TOPIC_PLAN_REQUEST,
    PlanCancelledPayload,
    PlanFailedPayload,
)
from k1.planner.pipeline_controller import PipelineController
from k1.planner.ports.event_port import IEventPort
from k1.planner.ports.mailbox_port import IMailboxPort
from k1.planner.types import PlanCancelledError, PlannerError

if TYPE_CHECKING:
    from k1.planner.types import HealthStatus

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Single-threaded async coordinator (Section 3.1, SS30.5.1 F02).

    Owns the mailbox dequeue loop, plan lock (V1 single-plan), cancel
    set, and lifecycle phases.  Drives PipelineController for each plan.

    Constructor
    -----------
    Accepts 4 injected dependencies.  PlannerAgent does NOT create
    services -- that is PlannerFactory's responsibility (M6).  The
    PipelineController is received fully-wired via constructor injection.

    Parameters
    ----------
    mailbox : IMailboxPort
        Inbound mailbox port (enqueue/dequeue/cancel/micro_replan).
    pipeline : PipelineController
        Fully-wired pipeline orchestrator (injected, not created).
    event_port : IEventPort
        Bidirectional event pub/sub port for lifecycle events and
        subscriptions.
    config : PlannerConfig
        Planner configuration (budgets, timeouts, temperatures).

    Internal State
    --------------
    _plan_lock : asyncio.Lock
        V1 single-plan exclusion (SS24.1.1).  Acquired at
        PLAN_START step 3, released at PLAN_END step 2.
    _cancel_set : Set[str]
        Request IDs pending cancellation (SS24.2).  Populated by
        ``on_cancel()``, consumed at 5 cancel checkpoints.
    _running : bool
        Controls the dequeue loop.  Set True at INIT, False at
        SHUTDOWN step 1.
    _subscriptions : List[SubscriptionHandle]
        Event subscriptions created at INIT (SS23.1 step 3), cleaned
        up at SHUTDOWN (SS23.5 step 7).

    Dependency Layer
    ----------------
    Layer 3 (SS30.6) -- imports Layer 2 (PipelineController), Layer 1
    (ports), Layer 0 (types/config).

    Notes
    -----
    PlannerAgent runs as a single-threaded async actor in one Python
    event loop.  No thread pool, no multiprocessing, no parallel plan
    execution (SS24.1).
    """

    __slots__ = (
        "_mailbox",
        "_pipeline",
        "_event_port",
        "_config",
        "_plan_lock",
        "_cancel_set",
        "_running",
        "_subscriptions",
        "_in_flight_request_id",
    )

    def __init__(
        self,
        mailbox: IMailboxPort,
        pipeline: PipelineController,
        event_port: IEventPort,
        config: PlannerConfig,
    ) -> None:
        # -- Validate injected dependencies --
        if mailbox is None:
            raise ValueError("PlannerAgent: mailbox must not be None")
        if pipeline is None:
            raise ValueError("PlannerAgent: pipeline must not be None")
        if event_port is None:
            raise ValueError("PlannerAgent: event_port must not be None")
        if config is None:
            raise ValueError("PlannerAgent: config must not be None")

        # -- Injected dependencies --
        self._mailbox: IMailboxPort = mailbox
        self._pipeline: PipelineController = pipeline
        self._event_port: IEventPort = event_port
        self._config: PlannerConfig = config

        # -- V1 single-plan exclusion (SS24.1.1) --
        self._plan_lock: asyncio.Lock = asyncio.Lock()

        # -- Cancel set (SS24.2) --
        self._cancel_set: Set[str] = set()

        # -- Dequeue loop control --
        self._running: bool = False

        # -- Event subscriptions (SS23.1 step 3, cleaned at SHUTDOWN) --
        self._subscriptions: List[SubscriptionHandle] = []

        # -- In-flight plan tracking (for SHUTDOWN cancel) --
        self._in_flight_request_id: Optional[str] = None

    # -- Properties (read-only for external consumers and testing) --

    @property
    def mailbox(self) -> IMailboxPort:
        """Injected mailbox port (read-only)."""
        return self._mailbox

    @property
    def pipeline(self) -> PipelineController:
        """Injected pipeline controller (read-only)."""
        return self._pipeline

    @property
    def event_port(self) -> IEventPort:
        """Injected event port (read-only)."""
        return self._event_port

    @property
    def config(self) -> PlannerConfig:
        """Planner configuration (read-only)."""
        return self._config

    @property
    def plan_lock(self) -> asyncio.Lock:
        """V1 single-plan exclusion lock (read-only reference).

        Acquired at PLAN_START step 3 (after mailbox dequeue, after
        cancel pre-check).  Released at PLAN_END step 2 (in finally
        block after pipeline.execute() completes or raises).
        """
        return self._plan_lock

    @property
    def cancel_set(self) -> Set[str]:
        """Pending cancellation request IDs (read-only copy).

        Returns a shallow copy to prevent external mutation.
        """
        return set(self._cancel_set)

    @property
    def running(self) -> bool:
        """Whether the dequeue loop is active."""
        return self._running

    @property
    def subscriptions(self) -> List[SubscriptionHandle]:
        """Active event subscriptions (read-only copy)."""
        return list(self._subscriptions)

    @property
    def in_flight_request_id(self) -> Optional[str]:
        """Request ID of the currently executing plan, or None."""
        return self._in_flight_request_id

    # -- Public query methods (factory, kernel, health checks) --

    def get_mailbox(self) -> IMailboxPort:
        """Return the injected mailbox port.

        Used by the kernel Phase 5 wiring to connect the orchestrator's
        send side to the planner's receive side.

        Returns
        -------
        IMailboxPort
            The mailbox port injected at construction time.
        """
        return self._mailbox

    def ready(self) -> bool:
        """Check whether the agent completed startup and is accepting plans.

        Post-wiring validation: factory calls this after ``start()`` to
        confirm the dequeue loop is active and event subscriptions are
        registered.

        Returns
        -------
        bool
            ``True`` when the dequeue loop is running.
        """
        return self._running

    def health(self) -> HealthStatus:
        """Return a snapshot of agent health.

        Used by factory post-wiring validation and runtime health
        endpoints.  Imports ``HealthStatus`` locally to avoid circular
        dependency (types.py is Layer 0, planner_agent.py is Layer 6).

        Returns
        -------
        HealthStatus
            Frozen dataclass with ``status`` and ``details`` fields.
        """
        from k1.planner.types import HealthStatus

        if not self._running:
            return HealthStatus(
                status="UNHEALTHY",
                details={
                    "running": False,
                    "subscriptions": 0,
                    "in_flight_request_id": self._in_flight_request_id,
                },
            )
        return HealthStatus(
            status="HEALTHY",
            details={
                "running": True,
                "subscriptions": len(self._subscriptions),
                "cancel_set_size": len(self._cancel_set),
                "plan_lock_locked": self._plan_lock.locked(),
                "in_flight_request_id": self._in_flight_request_id,
            },
        )

    # -- Event handlers (sync -- called by IEventPort.emit) --

    def _on_plan_request(self, topic: str, payload: Any) -> None:
        """Handle plan.request.v1 -- enqueue PlanRequest to mailbox.

        The handler is synchronous (IEventPort contract) so we schedule
        the async enqueue as a task on the running event loop.

        Parameters
        ----------
        topic : str
            Event topic (unused, always TOPIC_PLAN_REQUEST).
        payload : Any
            Expected to be a PlanRequest instance or a dict with
            PlanRequest fields.
        """
        if not self._running:
            logger.warning(
                "planner_agent.plan_request_rejected_not_running",
                extra={"topic": topic},
            )
            return
        try:
            request: PlanRequest
            if isinstance(payload, PlanRequest):
                request = payload
            elif isinstance(payload, dict):
                # PlanRequest envelopes ride the bus through
                # EventPortProdAdapter, which JSON-encodes them. Use
                # PlanRequest.from_dict so nested SessionSnapshot survives
                # the round trip; ``PlanRequest(**payload)`` would silently
                # explode on missing dataclass fields.
                request = PlanRequest.from_dict(payload)
            else:
                logger.warning(
                    "planner_agent.plan_request_invalid_payload",
                    extra={"payload_type": type(payload).__name__},
                )
                return
            loop = asyncio.get_running_loop()
            loop.create_task(self._safe_enqueue(request))
        except Exception:
            logger.warning(
                "planner_agent.plan_request_handler_failed",
                exc_info=True,
            )

    async def _safe_enqueue(self, request: PlanRequest) -> None:
        """Enqueue a PlanRequest, catching MailboxFullError."""
        try:
            await self._mailbox.enqueue(request)
        except Exception:
            logger.warning(
                "planner_agent.enqueue_failed",
                extra={"request_id": request.request_id},
                exc_info=True,
            )

    def _on_plan_cancel(self, topic: str, payload: Any) -> None:
        """Handle plan.cancel.v1 -- add request_id to cancel set.

        Synchronous: _cancel_set.add() is O(1) and non-blocking.
        """
        try:
            if isinstance(payload, dict):
                request_id = payload.get("request_id", "")
            else:
                request_id = getattr(payload, "request_id", "")
            if not request_id:
                logger.warning(
                    "planner_agent.cancel_missing_request_id",
                    extra={"payload_type": type(payload).__name__},
                )
                return
            self._cancel_set.add(request_id)
            logger.info(
                "planner_agent.cancel_registered",
                extra={"request_id": request_id, "source": "event"},
            )
        except Exception:
            logger.warning(
                "planner_agent.cancel_handler_failed",
                exc_info=True,
            )

    # E5 (HIL Unification): _on_hil_clarification / _on_hil_approval handlers
    # were removed. The planner no longer subscribes to TOPIC_HIL_*_RESP
    # topics; HIL coordination flows through the unified IHILPort adapter
    # injected via PlannerFactory.

    # -- Internal loop --

    async def _run_loop(self) -> None:
        """Mailbox dequeue loop -- processes PlanRequests sequentially.

        Single-threaded async actor loop (SS24.1.2).  Runs while
        ``_running`` is True.  Each iteration:

        1. ``await self._mailbox.dequeue()`` -- blocks until a
           PlanRequest is available (FIFO order, SS24.1.3).
        2. Cancel pre-check (SS24.2.2 checkpoint 1): if
           ``request.request_id in _cancel_set``, discard the request,
           emit ``plan.cancelled.v1``, and continue to next iteration
           without acquiring the lock.
        3. Acquire ``_plan_lock`` (SS24.1.1 -- PLAN_START step 3).
        4. Build ``cancel_check`` closure for checkpoints 2-5.
        5. ``await self._pipeline.execute(request, cancel_check)``.
        6. Finally: discard from cancel set, reset pipeline, release
           lock (PLAN_END).

        Error handling
        --------------
        - ``PlanCancelledError``: already handled by PipelineController
          (``plan.cancelled.v1`` emitted).  PlannerAgent logs and
          continues.
        - ``PlannerError``: already handled by PipelineController
          (``plan.failed.v1`` emitted).  PlannerAgent logs and
          continues.
        - ``Exception``: unexpected error NOT handled by
          PipelineController.  PlannerAgent emits
          ``plan.failed.v1{INTERNAL_ERROR}`` and continues.

        Implemented in Issue 2.3.2.
        """
        while self._running:
            # Block until a PlanRequest is available (FIFO)
            request = await self._mailbox.dequeue()

            # -- Shutdown guard --
            # If _running was set False while blocked on dequeue(),
            # the wake-up sentinel should NOT be processed.
            if not self._running:
                break

            # -- Cancel pre-check (SS24.2.2 checkpoint 1) --
            if request.request_id in self._cancel_set:
                self._cancel_set.discard(request.request_id)
                try:
                    self._event_port.emit(
                        TOPIC_PLAN_CANCELLED,
                        PlanCancelledPayload(
                            request_id=request.request_id,
                            reason="cancelled_before_start",
                            stage="PRE_CHECK",
                            trace_id=request.trace_id,
                        ),
                    )
                except Exception:
                    logger.warning(
                        "planner_agent.cancel_precheck_event_failed",
                        exc_info=True,
                    )
                logger.info(
                    "planner_agent.cancel_precheck",
                    extra={"request_id": request.request_id},
                )
                continue

            # -- Track in-flight request for SHUTDOWN cancel --
            self._in_flight_request_id = request.request_id

            # -- Acquire plan lock (SS24.1.1 -- PLAN_START step 3) --
            await self._plan_lock.acquire()
            try:
                # Cancel check closure for checkpoints 2-5 (SS24.2.2)
                def cancel_check() -> bool:
                    return request.request_id in self._cancel_set

                # Execute pipeline (SKETCH -> EXPAND -> VALIDATE -> COMMIT)
                await self._pipeline.execute(request, cancel_check)
                logger.info(
                    "planner_agent.plan_completed",
                    extra={"request_id": request.request_id},
                )
            except PlanCancelledError:
                # Already handled by PipelineController (emits
                # plan.cancelled.v1 event).  Log and continue.
                logger.info(
                    "planner_agent.plan_cancelled",
                    extra={"request_id": request.request_id},
                )
            except PlannerError as exc:
                # Already handled by PipelineController (emits
                # plan.failed.v1 event).  Log and continue.
                logger.error(
                    "planner_agent.plan_failed",
                    extra={
                        "request_id": request.request_id,
                        "stage": exc.stage,
                        "error": str(exc),
                    },
                )
            except Exception as exc:
                # Unexpected error -- PipelineController did NOT handle
                # this.  Emit plan.failed.v1{INTERNAL_ERROR} ourselves.
                logger.exception(
                    "planner_agent.unexpected_error",
                    extra={"request_id": request.request_id},
                )
                try:
                    self._event_port.emit(
                        TOPIC_PLAN_FAILED,
                        PlanFailedPayload(
                            request_id=request.request_id,
                            stage="INTERNAL",
                            error_code="INTERNAL_ERROR",
                            error_message=str(exc),
                            tokens_used=0,
                            duration_ms=0,
                            trace_id=request.trace_id,
                        ),
                    )
                except Exception:
                    logger.warning(
                        "planner_agent.internal_error_event_failed",
                        exc_info=True,
                    )
            finally:
                # PLAN_END: cleanup cancel set, reset pipeline, release
                # lock.  Order: reset before release so no waiter sees
                # stale pipeline state (asyncio is cooperative, but this
                # is defensively correct).
                self._in_flight_request_id = None
                self._cancel_set.discard(request.request_id)
                self._pipeline.reset()
                self._plan_lock.release()

    async def _crash_recovery(self) -> None:
        """V1 crash recovery -- always discard, set IDLE (SS23.6).

        V1 does NOT implement full crash recovery.  Any in-flight
        plan from a previous run is treated as lost.  The Orchestrator's
        stale-context reaper (45s timeout) emits DEGRADED and the task
        is re-dispatched at MEDIUM tier.

        Full crash recovery (WAL check, staleness evaluation, resume)
        requires reliable WAL reads from K0 and is deferred to V2.

        V1 implementation:
        1. Pipeline already reset to IDLE at INIT step 4.
        2. Log that crash recovery completed (no-op).
        """
        # V1: pipeline was already reset to IDLE in start() step 4.
        # No WAL check, no partial state to recover.
        logger.info(
            "planner_agent.crash_recovery_complete",
            extra={"action": "v1_discard", "note": "no_wal_support"},
        )

    # -- Public interface --

    async def start(self) -> None:
        """Run INIT + CRASH_RECOVERY + enter dequeue loop (SS23.1).

        Sequence:
        1. Validate that pipeline and ports are wired (INIT step 1).
           In V1, all deps are injected at construction and already
           validated by __init__.  This step logs confirmation.
        2. Subscribe to 4 event topics (INIT step 3):
           - k1.planner.plan.request.v1
           - k1.planner.plan.cancel.v1
           - k1.hil.clarification_response.v1
           - k1.hil.approval_response.v1
        3. Set state: FSM -> IDLE, _running = True (INIT step 4).
        4. Run CRASH_RECOVERY (SS23.6) -- V1 simplified: always
           discard, set IDLE.
        5. Enter _run_loop() (dequeue loop, SS24.1.2).

        Implemented in Issue 2.3.5 (INIT lifecycle phase).
        """
        logger.info("planner_agent.init_started")

        # -- Step 1: Validate wiring (SS23.1 step 1) --
        # In V1, services are pre-created by PlannerFactory and injected
        # via constructor.  __init__ already validates non-None.  We log
        # confirmation that all dependencies are wired.
        logger.info(
            "planner_agent.wiring_validated",
            extra={
                "mailbox": type(self._mailbox).__name__,
                "pipeline": type(self._pipeline).__name__,
                "event_port": type(self._event_port).__name__,
            },
        )

        # -- Step 2: (no-op) Ports injected at construction --

        # -- Step 3: Subscribe to 4 event topics (SS23.1 step 3) --
        self._subscriptions.append(
            self._event_port.subscribe(
                TOPIC_PLAN_REQUEST,
                self._on_plan_request,
            )
        )
        self._subscriptions.append(
            self._event_port.subscribe(
                TOPIC_PLAN_CANCEL,
                self._on_plan_cancel,
            )
        )
        logger.info(
            "planner_agent.subscriptions_created",
            extra={"count": len(self._subscriptions)},
        )

        # -- Step 4: Set state (SS23.1 step 4) --
        self._pipeline.reset()  # FSM -> IDLE
        self._cancel_set.clear()
        self._in_flight_request_id = None
        self._running = True

        # -- CRASH_RECOVERY (SS23.6 -- V1 simplified) --
        await self._crash_recovery()

        logger.info("planner_agent.init_complete")

        # -- Step 5: Enter dequeue loop (SS24.1.2) --
        await self._run_loop()

    async def stop(self) -> None:
        """Run SHUTDOWN sequence (SS23.5).

        Sequence:
        1. Set _running = False, reject new enqueues.
        2. Drain mailbox: emit plan.cancelled.v1 for each queued
           request.
        3. Cancel in-flight plan (if any): add to _cancel_set.
           Wait up to config.shutdown_grace_period_ms for the
           in-flight plan to reach a terminal state.
        4. Flush pending deltas (best-effort).  V1: no-op.
        5. Persist partial plan state (fire-and-forget).  V1: skip.
        6. Release _plan_lock if held (safety release).
        7. Unsubscribe all 4 event subscriptions.
        8. Structured log: shutdown.complete.

        Implemented in Issue 2.3.6 (SHUTDOWN phase).
        """
        logger.info("planner_agent.shutdown_started")

        # -- Step 1: Stop accepting (SS23.5 step 1) --
        self._running = False

        # -- Step 2: Drain mailbox (SS23.5 step 2) --
        drained_count = 0
        try:
            drained_requests = self._mailbox.drain()
            for req in drained_requests:
                drained_count += 1
                try:
                    self._event_port.emit(
                        TOPIC_PLAN_CANCELLED,
                        PlanCancelledPayload(
                            request_id=req.request_id,
                            reason="shutdown",
                            stage="QUEUED",
                            trace_id=req.trace_id,
                        ),
                    )
                except Exception:
                    logger.warning(
                        "planner_agent.drain_event_failed",
                        extra={"request_id": req.request_id},
                        exc_info=True,
                    )
        except Exception:
            logger.warning(
                "planner_agent.drain_failed",
                exc_info=True,
            )

        # -- Step 3: Cancel in-flight plan (SS23.5 step 3) --
        in_flight_cancelled = False
        if self._plan_lock.locked() and self._in_flight_request_id:
            self._cancel_set.add(self._in_flight_request_id)
            in_flight_cancelled = True
            logger.info(
                "planner_agent.shutdown_cancel_inflight",
                extra={"request_id": self._in_flight_request_id},
            )
            # Wait for in-flight plan to finish (grace period)
            grace_s = self._config.shutdown_grace_period_ms / 1000.0
            try:
                # Attempt to acquire lock -- blocks until in-flight
                # plan releases it (or timeout).
                await asyncio.wait_for(
                    self._plan_lock.acquire(),
                    timeout=grace_s,
                )
                # Lock acquired = in-flight plan finished.  Release.
                self._plan_lock.release()
            except asyncio.TimeoutError:
                logger.warning(
                    "planner_agent.shutdown_grace_period_exceeded",
                    extra={
                        "grace_ms": self._config.shutdown_grace_period_ms,
                        "request_id": self._in_flight_request_id,
                    },
                )

        # Inject sentinel to unblock dequeue() if loop is waiting
        try:
            sentinel = PlanRequest(
                intent="__shutdown_sentinel__",
                trace_id="__shutdown__",
                request_id="__shutdown_sentinel__",
            )
            await self._mailbox.enqueue(sentinel)
        except Exception:
            pass  # Best-effort; loop may have already exited

        # -- Steps 4-5: V1 no-op (flush deltas, persist partial) --

        # -- Step 6: Safety release lock (SS23.5 step 6) --
        if self._plan_lock.locked():
            try:
                self._plan_lock.release()
            except RuntimeError:
                pass  # Lock not owned by this task

        # -- Step 7: Unsubscribe (SS23.5 step 7) --
        for sub in self._subscriptions:
            try:
                self._event_port.unsubscribe(sub)
            except Exception:
                logger.warning(
                    "planner_agent.unsubscribe_failed",
                    extra={"subscription_id": sub.subscription_id},
                    exc_info=True,
                )
        self._subscriptions.clear()

        # -- Step 8: Log shutdown complete --
        logger.info(
            "planner_agent.shutdown_complete",
            extra={
                "plans_drained": drained_count,
                "in_flight_cancelled": in_flight_cancelled,
            },
        )

    async def on_cancel(self, request_id: str) -> None:
        """Add request_id to cancel set (SS24.2).

        Called by MailboxAdapter when Orchestrator invokes
        ``IPlannerMailbox.send_cancel(request_id)``.

        The cancel set is checked at 5 cancel checkpoints (SS24.2.2):
        1. PlannerAgent dequeue loop pre-check.
        2-5. Between stages via ``cancel_check`` closure passed to
             PipelineController.

        Idempotent: Set ignores duplicate adds (SS24.2.4).

        Parameters
        ----------
        request_id : str
            The request ID to mark as cancelled.

        Implemented in Issue 2.3.4 (cancel set management).
        """
        self._cancel_set.add(request_id)
        logger.info(
            "planner_agent.cancel_registered",
            extra={"request_id": request_id},
        )

    async def micro_replan(
        self,
        request: MicroReplanRequest,
    ) -> Optional[CommittedPlan]:
        """Acquire plan lock, delegate to pipeline.micro_replan (SS24.3).

        Bypasses the mailbox queue.  Acquires ``_plan_lock`` which
        BLOCKS until any current plan completes.  With 10s caller-side
        timeout and typical plan duration 12s p50, micro-replan will
        almost always timeout during active plan (by design --
        Orchestrator falls back to original plan).

        Parameters
        ----------
        request : MicroReplanRequest
            Micro-replan request with completed results, remaining
            steps, and optional discoveries / failure context.

        Returns
        -------
        Optional[CommittedPlan]
            A new CommittedPlan covering replacement steps, or None
            if the micro-replan was rejected by validation.

        Implemented in Issue 2.3.3 (plan lock).
        """
        logger.info(
            "planner_agent.micro_replan_requested",
            extra={"request_id": request.request_id},
        )
        await self._plan_lock.acquire()
        try:

            def cancel_check() -> bool:
                return request.request_id in self._cancel_set

            result = await self._pipeline.micro_replan(request, cancel_check)
            logger.info(
                "planner_agent.micro_replan_completed",
                extra={
                    "request_id": request.request_id,
                    "result": "committed" if result is not None else "rejected",
                },
            )
            return result
        finally:
            self._pipeline.reset()
            self._plan_lock.release()


__all__ = ["PlannerAgent"]
