"""
AsyncSSMBridge -- async wrapper for the sync SessionStateManager.

Issue 2.0.2 – Pre-requisite: give async callers a non-blocking interface
to the threaded SessionStateManager whose write / lifecycle methods
acquire ``threading.RLock``.

Strategy
--------
*  **Write / lifecycle methods** (``mutate``, ``start``, ``stop``,
   ``checkpoint``, ``restore``) are offloaded via ``asyncio.to_thread``
   so the event-loop is never blocked by the underlying ``_write_lock``.

*  **Lock-free reads** (properties and read-API methods) are direct
   pass-throughs — they never acquire the RLock and are documented as
   <1 ms, so a thread hop is unnecessary overhead.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from k1.sessionstate.manager import (
    CheckpointResult,
    ManagerState,
    MutationResult,
    RestoreResult,
    SessionSnapshot,
    SessionStateManager,
    StartResult,
    StopResult,
)


class AsyncSSMBridge:
    """
    Async facade over a sync :class:`SessionStateManager`.

    Parameters
    ----------
    sync_manager : SessionStateManager
        The underlying synchronous manager instance.
    """

    __slots__ = ("_sync",)

    def __init__(self, sync_manager: SessionStateManager) -> None:
        self._sync = sync_manager

    # ===================================================================
    # PROPERTIES — lock-free direct pass-through
    # ===================================================================

    @property
    def session_id(self) -> str:
        return self._sync.session_id

    @property
    def state(self) -> ManagerState:
        return self._sync.state

    @property
    def is_running(self) -> bool:
        return self._sync.is_running

    @property
    def hot(self) -> Any:
        """HotTier reference (lock-free)."""
        return self._sync.hot

    @property
    def warm(self) -> Any:
        """WarmTier reference (lock-free)."""
        return self._sync.warm

    @property
    def local_cold(self) -> Any:
        """LocalColdTier reference (lock-free)."""
        return self._sync.local_cold

    @property
    def size_tracker(self) -> Any:
        """SizeTracker reference (lock-free)."""
        return self._sync.size_tracker

    @property
    def mutation_guard(self) -> Any:
        """MutationGuard reference (lock-free)."""
        return self._sync.mutation_guard

    @property
    def eviction_engine(self) -> Any:
        """EvictionEngine reference (lock-free)."""
        return self._sync.eviction_engine

    @property
    def migration_engine(self) -> Any:
        """MigrationEngine reference (lock-free)."""
        return self._sync.migration_engine

    # ===================================================================
    # READ API — lock-free direct pass-through
    # ===================================================================

    def get_section(self, name: str) -> Any:
        return self._sync.get_section(name)

    def get_hot(self) -> Any:
        return self._sync.get_hot()

    def get_warm(self) -> Any:
        return self._sync.get_warm()

    def get_all_section_sizes(self) -> Dict[str, int]:
        return self._sync.get_all_section_sizes()

    def get_local_cold(self) -> Any:
        return self._sync.get_local_cold()

    def get_snapshot(self) -> SessionSnapshot:
        return self._sync.get_snapshot()

    # ===================================================================
    # WRITE API — offloaded via asyncio.to_thread
    # ===================================================================

    async def mutate(
        self,
        section: str,
        operation: str,
        data: Any,
        estimated_bytes: Optional[int] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> MutationResult:
        """
        Apply a mutation to a section (async).

        Offloads to a worker thread because ``SessionStateManager.mutate``
        acquires ``_write_lock`` (RLock).
        """
        return await asyncio.to_thread(
            self._sync.mutate,
            section,
            operation,
            data,
            estimated_bytes,
            cognitive_trace_id,
        )

    # ===================================================================
    # LIFECYCLE — offloaded via asyncio.to_thread
    # ===================================================================

    async def start(
        self,
        restore_if_exists: bool = True,
        cognitive_trace_id: Optional[str] = None,
    ) -> StartResult:
        """Start the session lifecycle (async)."""
        return await asyncio.to_thread(
            self._sync.start,
            restore_if_exists,
            cognitive_trace_id,
        )

    async def stop(
        self,
        checkpoint_before_stop: bool = True,
        cognitive_trace_id: Optional[str] = None,
    ) -> StopResult:
        """Stop the session lifecycle gracefully (async)."""
        return await asyncio.to_thread(
            self._sync.stop,
            checkpoint_before_stop,
            cognitive_trace_id,
        )

    async def checkpoint(
        self,
        cognitive_trace_id: Optional[str] = None,
    ) -> CheckpointResult:
        """Checkpoint current state to LOCAL COLD (async)."""
        return await asyncio.to_thread(
            self._sync.checkpoint,
            cognitive_trace_id,
        )

    async def restore(
        self,
        session_id: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> RestoreResult:
        """Restore session from LOCAL COLD (async)."""
        return await asyncio.to_thread(
            self._sync.restore,
            session_id,
            cognitive_trace_id,
        )


__all__ = ["AsyncSSMBridge"]
