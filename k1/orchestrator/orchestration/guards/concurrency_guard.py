"""
k1.orchestrator.orchestration.guards.concurrency_guard -- DAG concurrency gate.

NOT a DAGGuard. Checked in OrchestratorService._process_one() BEFORE
dispatching to DAGExecutor, not during the DAG walk.

Enforces single-DAG-at-a-time (V1, per ADR-1.1.5).

Design:
  - Uses asyncio.Lock (not threading.Lock) -- Orchestrator is
    single-threaded async.
  - acquire() returns False immediately when a DAG is already active
    (non-blocking). Caller re-enqueues the message as DEFERRED.
  - release() MUST be called in a finally block to prevent permanent
    lock after unhandled exceptions.
  - DEFERRED messages re-enter mailbox at BACKGROUND priority
    (don't starve REALTIME).

References:
  - orchestrator-implementation-plan.md Issue 3.2.9
  - ADR-1.1.5 (single-DAG-at-a-time V1)
  - Schema Whiteboard S8 (G4 -- ConcurrencyGuard, pre-dispatch)

Exports:
  ConcurrencyGuard
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class ConcurrencyGuard:
    """Single-DAG-at-a-time gate for OrchestratorService.

    NOT a DAGGuard -- checked before DAGExecutor dispatch, not during
    DAG walk. Uses asyncio.Lock for cooperative single-threaded async
    locking.

    Usage::

        guard = ConcurrencyGuard()

        # In OrchestratorService._process_one():
        if not await guard.acquire():
            # re-enqueue message as DEFERRED at BACKGROUND priority
            return DEFERRED

        try:
            await dag_executor.execute(...)
        finally:
            guard.release()
    """

    __slots__ = ("_lock", "_active")

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._active: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self) -> bool:
        """Attempt non-blocking lock acquisition.

        Returns True if the lock was acquired (no DAG currently active).
        Returns False immediately if a DAG is already running (lock held).

        Caller is responsible for calling release() in a finally block
        when acquire() returns True.
        """
        if self._lock.locked():
            logger.debug("ConcurrencyGuard.acquire: DAG already active, rejecting")
            return False

        await self._lock.acquire()
        self._active = True
        logger.debug("ConcurrencyGuard.acquire: lock acquired")
        return True

    def release(self) -> None:
        """Release the concurrency lock.

        MUST be called in a finally block after acquire() returns True.
        Safe to call even if lock is not held (logs warning, no-op).
        """
        if not self._lock.locked():
            logger.warning("ConcurrencyGuard.release: lock not held, ignoring")
            return

        self._active = False
        self._lock.release()
        logger.debug("ConcurrencyGuard.release: lock released")

    @property
    def active(self) -> bool:
        """Whether a DAG is currently executing under this guard."""
        return self._active

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"ConcurrencyGuard(active={self._active})"
