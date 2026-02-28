"""
poc.k1_poc.actors.back_pool -- BackPool Worker Management (M7 E7.1).

Replaces the single-worker Back execution model with a parallel pool
where each task gets an isolated worker slot. Enforces pool_size and
max_concurrent_per_session limits. Workers are tracked by task_id and
released on task completion.

Key invariants:
  - Each worker's react_loop runs in its own asyncio.Task with its
    own SS snapshot. Workers do NOT share mutable state.
  - The FSM + TaskBridge remain the single writer for task_state and
    task_artifacts. Workers only READ SS and EMIT events.
  - Pool size bounds the maximum number of concurrent react_loops.
  - max_concurrent_per_session prevents one chatty session from
    monopolizing all workers.

V3 Milestone 7 E7.1.1-7.1.4
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from poc.k1_poc.protocols.task_lease import TaskLease

logger = logging.getLogger(__name__)


# =====================================================================
# E7.1.1 -- BackPoolConfig
# =====================================================================


@dataclass
class BackPoolConfig:
    """Configuration for the BackPool worker manager.

    M7 E7.1.1: Controls pool sizing, session concurrency limits,
    lease TTL, and dependency ordering.

    Attributes:
        pool_size: Maximum number of concurrent react_loops. Default 3
            balances parallelism with SS consistency (each worker reads
            SS once at start; concurrent workers see independent snapshots).
        max_concurrent_per_session: Maximum concurrent workers for a
            single session. Prevents one chatty session from monopolizing
            all workers. Default 2.
        lease_ttl_s: Default time-to-live for task leases in seconds.
            After this duration without renewal, the lease expires and
            the worker is reclaimed. Default 300.0 (5 minutes).
        reclaim_check_interval_s: How often the lease expiry watcher
            scans for expired leases. Default 30.0.
        enable_dependency_ordering: Whether to hold dependent tasks in
            a ready-queue until predecessors complete. Default True.
        max_renewals: Maximum number of lease renewals allowed per
            task. Default 3. After this, the lease expires normally.
        lease_grace_period_s: Grace period in seconds after cooperative
            cancel before hard-killing the asyncio.Task. Default 5.0.
    """

    pool_size: int = 3
    max_concurrent_per_session: int = 2
    lease_ttl_s: float = 300.0
    reclaim_check_interval_s: float = 30.0
    enable_dependency_ordering: bool = True
    max_renewals: int = 3
    lease_grace_period_s: float = 5.0

    def __post_init__(self) -> None:
        if self.pool_size < 1:
            raise ValueError(f"pool_size must be >= 1, got {self.pool_size}")
        if self.max_concurrent_per_session < 1:
            raise ValueError(
                f"max_concurrent_per_session must be >= 1, "
                f"got {self.max_concurrent_per_session}"
            )
        if self.lease_ttl_s <= 0:
            raise ValueError(f"lease_ttl_s must be > 0, got {self.lease_ttl_s}")
        if self.reclaim_check_interval_s <= 0:
            raise ValueError(
                f"reclaim_check_interval_s must be > 0, " f"got {self.reclaim_check_interval_s}"
            )
        if self.max_renewals < 0:
            raise ValueError(f"max_renewals must be >= 0, got {self.max_renewals}")
        if self.lease_grace_period_s < 0:
            raise ValueError(
                f"lease_grace_period_s must be >= 0, " f"got {self.lease_grace_period_s}"
            )


# =====================================================================
# E7.1.2 -- WorkerSlot + BackPool
# =====================================================================


@dataclass
class WorkerSlot:
    """An isolated execution context for a single Back task.

    M7 E7.1.2: Each worker slot represents one concurrent react_loop.
    Contains the task_id, a unique worker_id, the asyncio.Task reference,
    and the creation timestamp. The lease field is populated by E7.2
    when TaskLease is created at dispatch time.

    Attributes:
        task_id:    The task this worker is executing.
        worker_id:  Unique identifier for this worker slot (uuid4).
        created_at: Monotonic timestamp (ns) when the slot was acquired.
        session_id: Session this worker belongs to (for concurrency limits).
        async_task: The asyncio.Task running the react_loop (bound later).
        lease:      TaskLease reference (populated by E7.2, None for E7.1).
    """

    task_id: str
    worker_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=time.monotonic_ns)
    session_id: str | None = None
    async_task: asyncio.Task | None = field(default=None, repr=False)
    lease: TaskLease | None = None  # E7.2: TaskLease bound at acquire_worker

    def bind_task(self, task: asyncio.Task, lease: Any = None) -> None:
        """Bind an asyncio.Task and optional lease to this worker slot.

        Args:
            task: The asyncio.Task running the react_loop.
            lease: Optional TaskLease (E7.2).
        """
        self.async_task = task
        if lease is not None:
            self.lease = lease

    @property
    def is_running(self) -> bool:
        """Whether the bound asyncio.Task is still running."""
        return self.async_task is not None and not self.async_task.done()


class BackPoolExhausted(Exception):
    """Raised when all worker slots are occupied.

    The caller must queue the envelope and retry when a worker is
    released. This prevents blocking the consumer loop.
    """

    def __init__(
        self,
        pool_size: int,
        active_count: int,
        *,
        reason: str = "pool_full",
    ) -> None:
        self.pool_size = pool_size
        self.active_count = active_count
        self.reason = reason
        super().__init__(
            f"BackPool exhausted: {active_count}/{pool_size} workers active " f"(reason={reason})"
        )


class SessionLimitReached(BackPoolExhausted):
    """Raised when a session has reached its max_concurrent_per_session."""

    def __init__(
        self,
        session_id: str,
        session_count: int,
        max_per_session: int,
    ) -> None:
        self.session_id = session_id
        self.session_count = session_count
        self.max_per_session = max_per_session
        super().__init__(
            pool_size=max_per_session,
            active_count=session_count,
            reason="session_limit",
        )


class BackPool:
    """Parallel worker pool for Back task execution.

    M7 E7.1.2: Manages worker lifecycle with pool_size and
    max_concurrent_per_session limits. Each task gets an isolated
    WorkerSlot with its own asyncio.Task.

    Thread safety: BackPool is designed for single-threaded asyncio
    usage (same event loop as the coordinator consumer).

    Attributes:
        config:    BackPoolConfig controlling pool behavior.
        _workers:  Active worker slots indexed by task_id.
        _overflow: Envelopes queued when pool is full (FIFO).
        _on_worker_acquired: Optional callback for observability.
        _on_worker_released: Optional callback for observability.
    """

    def __init__(
        self,
        config: BackPoolConfig | None = None,
        *,
        on_worker_acquired: Callable[[WorkerSlot], Any] | None = None,
        on_worker_released: Callable[[WorkerSlot, str], Any] | None = None,
    ) -> None:
        self.config = config or BackPoolConfig()
        self._workers: dict[str, WorkerSlot] = {}
        self._overflow: list[Any] = []  # Envelope queue for exhausted pool
        self._released_task_ids: set[str] = set()  # E7.3.4: track released/cancelled tasks
        self._on_worker_acquired = on_worker_acquired
        self._on_worker_released = on_worker_released
        logger.info(
            "BackPool: initialized pool_size=%d max_per_session=%d "
            "lease_ttl=%.1fs dep_ordering=%s",
            self.config.pool_size,
            self.config.max_concurrent_per_session,
            self.config.lease_ttl_s,
            self.config.enable_dependency_ordering,
        )

    # -----------------------------------------------------------------
    # Worker lifecycle
    # -----------------------------------------------------------------

    def acquire_worker(
        self,
        task_id: str,
        *,
        session_id: str | None = None,
        cancellation_token: Any | None = None,
    ) -> WorkerSlot:
        """Acquire a worker slot for a task.

        M7 E7.1.2: Checks pool_size and max_concurrent_per_session
        limits. If pool is full, raises BackPoolExhausted. If session
        limit is reached, raises SessionLimitReached.

        M7 E7.5.3: Accepts optional cancellation_token from the FSM
        cancel handler so that the lease binds to the SAME token used
        by the FSM, arbiter, and HITL timeout paths (single source of
        truth for cancel propagation).

        Args:
            task_id: The task to assign a worker to.
            session_id: Optional session ID for per-session limits.
            cancellation_token: Optional pre-existing token from FSM
                cancel_handler (M7 E7.5.3 unification).

        Returns:
            WorkerSlot with unique worker_id.

        Raises:
            BackPoolExhausted: If all worker slots are occupied.
            SessionLimitReached: If session concurrency limit hit.
        """
        # Check if task already has a worker (idempotent guard)
        if task_id in self._workers:
            logger.warning(
                "BackPool.acquire_worker: task_id=%s already has worker=%s",
                task_id,
                self._workers[task_id].worker_id,
            )
            return self._workers[task_id]

        # Clean up completed workers before checking limits
        self._cleanup_done_workers()

        # Check pool-level limit
        active_count = len(self._workers)
        if active_count >= self.config.pool_size:
            logger.warning(
                "BackPool.acquire_worker: pool exhausted %d/%d for task_id=%s",
                active_count,
                self.config.pool_size,
                task_id,
            )
            raise BackPoolExhausted(self.config.pool_size, active_count)

        # Check per-session limit
        if session_id is not None:
            session_count = sum(1 for w in self._workers.values() if w.session_id == session_id)
            if session_count >= self.config.max_concurrent_per_session:
                logger.warning(
                    "BackPool.acquire_worker: session limit %d/%d for " "session=%s task_id=%s",
                    session_count,
                    self.config.max_concurrent_per_session,
                    session_id,
                    task_id,
                )
                raise SessionLimitReached(
                    session_id,
                    session_count,
                    self.config.max_concurrent_per_session,
                )

        # Create worker slot with TaskLease (E7.2.2)
        from poc.k1_poc.protocols.task_lease import create_task_lease

        lease = create_task_lease(
            task_id=task_id,
            worker_id=str(uuid.uuid4()),
            lease_ttl_s=self.config.lease_ttl_s,
            max_renewals=self.config.max_renewals,
            cancellation_token=cancellation_token,
        )
        slot = WorkerSlot(
            task_id=task_id,
            session_id=session_id,
            worker_id=lease.worker_id,
            lease=lease,
        )
        self._workers[task_id] = slot

        utilization = len(self._workers) / self.config.pool_size

        # M7 E7.1.4: Log warning when pool utilization > 80%
        if utilization > 0.8:
            logger.warning(
                "BackPool: pool utilization %.0f%% (%d/%d) -- "
                "approaching capacity after acquiring worker for task=%s",
                utilization * 100,
                len(self._workers),
                self.config.pool_size,
                task_id,
            )

        logger.info(
            "BackPool.acquire_worker: task_id=%s worker_id=%s " "pool=%d/%d session=%s",
            task_id,
            slot.worker_id,
            len(self._workers),
            self.config.pool_size,
            session_id or "N/A",
        )

        # Observability callback
        if self._on_worker_acquired is not None:
            try:
                self._on_worker_acquired(slot)
            except Exception:
                logger.exception("BackPool: on_worker_acquired callback failed")

        return slot

    def release_worker(
        self,
        task_id: str,
        *,
        reason: str = "completed",
    ) -> WorkerSlot | None:
        """Release a worker slot back to the pool.

        M7 E7.1.2: Cleans up the slot and makes it available for
        new tasks. If task_id is not found, returns None.

        Args:
            task_id: The task whose worker to release.
            reason: Why the worker is being released. One of
                "completed", "cancelled", "lease_expired",
                "suspended", "error".

        Returns:
            The released WorkerSlot, or None if not found.
        """
        slot = self._workers.pop(task_id, None)
        if slot is None:
            logger.debug(
                "BackPool.release_worker: no worker for task_id=%s "
                "(already released or never acquired)",
                task_id,
            )
            return None

        # E7.3.4: Track released task_ids for late-envelope discard
        self._released_task_ids.add(task_id)

        # Update lease status (E7.2.2)
        if slot.lease is not None:
            if reason == "cancelled":
                slot.lease.cancel()
            elif reason == "lease_expired":
                slot.lease.expire()
            else:
                slot.lease.release()

        logger.info(
            "BackPool.release_worker: task_id=%s worker_id=%s " "reason=%s pool=%d/%d",
            task_id,
            slot.worker_id,
            reason,
            len(self._workers),
            self.config.pool_size,
        )

        # Observability callback
        if self._on_worker_released is not None:
            try:
                self._on_worker_released(slot, reason)
            except Exception:
                logger.exception("BackPool: on_worker_released callback failed")

        return slot

    def get_active_workers(self) -> list[WorkerSlot]:
        """Return all active worker slots.

        M7 E7.1.2: Replaces the coordinator's _pending_back_tasks list.

        Returns:
            List of active WorkerSlot instances.
        """
        self._cleanup_done_workers()
        return list(self._workers.values())

    def get_worker_for_task(self, task_id: str) -> WorkerSlot | None:
        """Get the worker slot for a specific task.

        Args:
            task_id: The task to look up.

        Returns:
            WorkerSlot if found, None otherwise.
        """
        return self._workers.get(task_id)

    # -----------------------------------------------------------------
    # Pool state queries
    # -----------------------------------------------------------------

    @property
    def active_count(self) -> int:
        """Number of currently active workers."""
        return len(self._workers)

    @property
    def pool_available(self) -> int:
        """Number of available worker slots."""
        return max(0, self.config.pool_size - len(self._workers))

    @property
    def utilization(self) -> float:
        """Pool utilization as a fraction (0.0 to 1.0)."""
        if self.config.pool_size == 0:
            return 1.0
        return len(self._workers) / self.config.pool_size

    def session_count(self, session_id: str) -> int:
        """Count active workers for a given session.

        Args:
            session_id: The session to count.

        Returns:
            Number of active workers for this session.
        """
        return sum(1 for w in self._workers.values() if w.session_id == session_id)

    def has_worker(self, task_id: str) -> bool:
        """Check if a task has an active worker."""
        return task_id in self._workers

    def is_task_released(self, task_id: str) -> bool:
        """Check if a task was previously released or cancelled.

        M7 E7.3.4: Used by BackTopicRouter to discard late-arriving
        envelopes for tasks whose lease has already been released.

        Args:
            task_id: The task to check.

        Returns:
            True if the task was previously released.
        """
        return task_id in self._released_task_ids

    # -----------------------------------------------------------------
    # Lease management (E7.2.5)
    # -----------------------------------------------------------------

    def get_lease(self, task_id: str) -> TaskLease | None:
        """Get the TaskLease for a specific task.

        Args:
            task_id: The task to look up.

        Returns:
            TaskLease if found, None otherwise.
        """
        slot = self._workers.get(task_id)
        return slot.lease if slot is not None else None

    def renew_lease(
        self,
        task_id: str,
        extension_s: float = 60.0,
    ) -> bool:
        """Renew the lease for a long-running task.

        M7 E7.2.5: Called by the Back react_loop between iterations
        when it needs more time. Default extension = 60s.

        Args:
            task_id: The task whose lease to renew.
            extension_s: Extension duration in seconds.

        Returns:
            True if renewal succeeded, False if denied or not found.
        """
        slot = self._workers.get(task_id)
        if slot is None or slot.lease is None:
            logger.warning(
                "BackPool.renew_lease: no worker/lease for task_id=%s",
                task_id,
            )
            return False

        return slot.lease.renew(extension_s=extension_s)

    def get_expired_leases(self) -> list[WorkerSlot]:
        """Return all worker slots with expired leases.

        M7 E7.2.3: Used by the lease expiry watcher to find
        workers whose leases have exceeded TTL.

        Returns:
            List of WorkerSlot instances with expired leases.
        """
        expired = []
        for slot in self._workers.values():
            if slot.lease is not None and slot.lease.is_expired:
                expired.append(slot)
        return expired

    # -----------------------------------------------------------------
    # Lease expiry watcher (E7.2.3)
    # -----------------------------------------------------------------

    async def start_lease_watcher(self, bus: Any = None) -> asyncio.Task:
        """Start the background lease expiry watcher.

        M7 E7.2.3: Periodically scans active leases for expiry.
        For each expired lease:
          (a) Cancel the CancellationToken (cooperative exit).
          (b) Wait grace period for the react_loop to complete.
          (c) If still running, hard-cancel the asyncio.Task.
          (d) Release the worker slot.
          (e) Emit task.failed with reason="lease_expired".

        Args:
            bus: Optional bus for emitting task.failed events.

        Returns:
            The background asyncio.Task running the watcher.
        """
        self._lease_watcher_bus = bus
        self._lease_watcher_running = True
        task = asyncio.create_task(self._lease_watcher_loop())
        task.set_name("backpool-lease-watcher")
        self._lease_watcher_task = task
        logger.info(
            "BackPool: lease watcher started " "interval=%.1fs grace=%.1fs",
            self.config.reclaim_check_interval_s,
            self.config.lease_grace_period_s,
        )
        return task

    async def stop_lease_watcher(self) -> None:
        """Stop the background lease expiry watcher."""
        self._lease_watcher_running = False
        watcher = getattr(self, "_lease_watcher_task", None)
        if watcher is not None and not watcher.done():
            watcher.cancel()
            try:
                await watcher
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("BackPool: lease watcher stopped")

    async def _lease_watcher_loop(self) -> None:
        """Background loop that checks for expired leases.

        Runs every reclaim_check_interval_s. For each expired lease,
        performs cooperative cancel -> grace period -> hard kill.
        """
        while getattr(self, "_lease_watcher_running", False):
            try:
                await asyncio.sleep(self.config.reclaim_check_interval_s)
            except asyncio.CancelledError:
                break

            expired_slots = self.get_expired_leases()
            for slot in expired_slots:
                await self._reclaim_expired_worker(slot)

    async def _reclaim_expired_worker(self, slot: WorkerSlot) -> None:
        """Reclaim a single expired worker slot.

        Steps:
          1. Cancel the CancellationToken (cooperative).
          2. Wait grace_period for the asyncio.Task to finish.
          3. Hard-cancel the asyncio.Task if still running.
          4. Release the worker slot.
          5. Emit task.failed with reason="lease_expired".
        """
        from poc.k1_poc.protocols.cancellation import CancelReason

        task_id = slot.task_id
        logger.warning(
            "BackPool: lease expired for task_id=%s worker_id=%s " "-- initiating reclamation",
            task_id,
            slot.worker_id,
        )

        # Step 1: Cooperative cancel via CancellationToken
        if slot.lease is not None and slot.lease.cancellation_token is not None:
            slot.lease.cancellation_token.cancel(CancelReason.TIMEOUT)
            slot.lease.expire()

        # Step 2: Wait grace period for react_loop to exit
        if slot.async_task is not None and not slot.async_task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(slot.async_task),
                    timeout=self.config.lease_grace_period_s,
                )
                logger.info(
                    "BackPool: task_id=%s exited cooperatively " "within grace period",
                    task_id,
                )
            except asyncio.TimeoutError:
                # Step 3: Hard-cancel the asyncio.Task
                logger.warning(
                    "BackPool: task_id=%s did not exit within "
                    "grace period (%.1fs) -- hard cancelling",
                    task_id,
                    self.config.lease_grace_period_s,
                )
                slot.async_task.cancel()
                try:
                    await slot.async_task
                except (asyncio.CancelledError, Exception):
                    pass
            except (asyncio.CancelledError, Exception):
                pass

        # Step 4: Release the worker slot
        self.release_worker(task_id, reason="lease_expired")

        # Step 5: Emit task.failed with reason="lease_expired"
        bus = getattr(self, "_lease_watcher_bus", None)
        if bus is not None:
            try:
                from poc.k1_poc.bus.builders import build_task_failed

                env = build_task_failed(
                    payload={
                        "task_id": task_id,
                        "worker_id": slot.worker_id,
                        "reason": "lease_expired",
                        "lease_id": slot.lease.lease_id if slot.lease else None,
                    }
                )
                bus.publish(env)
                logger.info(
                    "BackPool: emitted task.failed for " "lease-expired task_id=%s",
                    task_id,
                )
            except Exception:
                logger.debug(
                    "BackPool: failed to emit task.failed for " "lease-expired task",
                    exc_info=True,
                )

    # -----------------------------------------------------------------
    # Overflow queue (for pool-exhausted envelopes)
    # -----------------------------------------------------------------

    def enqueue_overflow(self, envelope: Any) -> None:
        """Push an envelope into the overflow queue.

        M7 E7.1.3: When acquire_worker raises BackPoolExhausted,
        the caller pushes the envelope here for retry.

        Args:
            envelope: The envelope that could not be dispatched.
        """
        self._overflow.append(envelope)
        logger.info(
            "BackPool.enqueue_overflow: queued envelope (overflow=%d)",
            len(self._overflow),
        )

    def dequeue_overflow(self) -> Any | None:
        """Pop the next envelope from the overflow queue (FIFO).

        Returns:
            Next envelope, or None if queue is empty.
        """
        if self._overflow:
            return self._overflow.pop(0)
        return None

    @property
    def overflow_depth(self) -> int:
        """Number of envelopes in the overflow queue."""
        return len(self._overflow)

    def drain_overflow(self) -> list[Any]:
        """Return all ready overflow envelopes and clear the queue.

        Returns:
            List of envelopes that were in the overflow queue.
        """
        drained = list(self._overflow)
        self._overflow.clear()
        return drained

    # -----------------------------------------------------------------
    # Internal cleanup
    # -----------------------------------------------------------------

    def _cleanup_done_workers(self) -> None:
        """Remove worker slots whose asyncio.Task has completed.

        This handles the case where a worker's task finished but
        release_worker was not explicitly called (defensive cleanup).
        """
        done_tasks = [
            task_id
            for task_id, slot in self._workers.items()
            if slot.async_task is not None and slot.async_task.done()
        ]
        for task_id in done_tasks:
            slot = self._workers.pop(task_id, None)
            if slot:
                logger.info(
                    "BackPool._cleanup_done_workers: auto-released "
                    "task_id=%s worker_id=%s (task completed without "
                    "explicit release)",
                    task_id,
                    slot.worker_id,
                )
                if self._on_worker_released is not None:
                    try:
                        self._on_worker_released(slot, "auto_cleanup")
                    except Exception:
                        logger.exception(
                            "BackPool: on_worker_released callback failed " "during cleanup"
                        )

    # -----------------------------------------------------------------
    # Pool state snapshot (for observability)
    # -----------------------------------------------------------------

    def get_pool_state(self) -> dict[str, Any]:
        """Return a snapshot of the pool state for observability.

        M7 E7.1.4: Provides pool utilization data for metrics
        and health checks.

        Returns:
            Dict with active, size, available, utilization, overflow,
            and workers list.
        """
        self._cleanup_done_workers()
        return {
            "active": len(self._workers),
            "size": self.config.pool_size,
            "available": self.pool_available,
            "utilization": round(self.utilization, 3),
            "overflow": len(self._overflow),
            "workers": [
                {
                    "task_id": slot.task_id,
                    "worker_id": slot.worker_id,
                    "session_id": slot.session_id,
                    "is_running": slot.is_running,
                    "created_at": slot.created_at,
                    "lease_status": slot.lease.status.value if slot.lease else None,
                    "lease_remaining_s": round(slot.lease.remaining_s, 3) if slot.lease else None,
                    "lease_renewed_count": slot.lease.renewed_count if slot.lease else 0,
                }
                for slot in self._workers.values()
            ],
        }

    def __repr__(self) -> str:
        return (
            f"BackPool(active={len(self._workers)}/{self.config.pool_size}, "
            f"overflow={len(self._overflow)})"
        )


__all__ = [
    "BackPoolConfig",
    "WorkerSlot",
    "BackPool",
    "BackPoolExhausted",
    "SessionLimitReached",
]
