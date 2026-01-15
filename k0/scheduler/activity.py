"""
Activity tracking for idle detection triggers.

The ActivityTracker is a kernel-level component that records system activity.
It integrates with BusDispatcher to automatically record activity on each
event dispatch.

Architecture (ADR-K004):
    Layer 3 of Capability Mesh - Supports IdleTriggerEngine for
    idle-based pipeline activation.

P03 Use Case:
    - Fire consolidation when system idle for 5 minutes
    - AND at least 100 pending items in embedding queue

Related:
- k0/scheduler/triggers.py: IdleTriggerEngine
- k0/bus/dispatcher.py: BusDispatcher integration
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class IdleListener:
    """Registered idle listener with callback and threshold."""

    id: str
    callback: Callable[[], None]
    threshold_seconds: float
    fired: bool = False  # Reset when activity occurs


class ActivityTracker:
    """
    Tracks system activity for idle detection.

    Thread-safe. Called from BusDispatcher on every event dispatch
    and from API handlers on user requests.

    Lifecycle:
        1. Created during kernel boot
        2. start() begins the idle check loop
        3. record_activity() called on every bus dispatch
        4. Idle listeners fire when threshold exceeded
        5. stop() during kernel shutdown

    Metrics (future):
        - activity_tracker_records_total: Count of activity records
        - activity_tracker_idle_seconds: Current idle duration gauge
        - activity_tracker_listeners_total: Number of registered listeners
    """

    def __init__(self, check_interval: float = 1.0):
        """
        Initialize activity tracker.

        Args:
            check_interval: How often to check idle conditions (seconds)
        """
        self._last_activity = time.monotonic()
        self._listeners: dict[str, IdleListener] = {}
        self._lock = asyncio.Lock()
        self._check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None

    def record_activity(self) -> None:
        """
        Record activity (called on bus dispatch, API request, etc.).

        This resets the idle timer and marks all listeners as unfired
        so they can fire again after the next idle period.

        Thread-safe via atomic timestamp update.
        """
        self._last_activity = time.monotonic()

        # Reset fired flags so listeners can fire again
        for listener in self._listeners.values():
            listener.fired = False

        logger.debug(
            "Activity recorded, idle timer reset",
            extra={"listener_count": len(self._listeners)},
        )

    def idle_seconds(self) -> float:
        """Return seconds since last activity."""
        return time.monotonic() - self._last_activity

    async def register_idle_listener(
        self,
        listener_id: str,
        callback: Callable[[], None],
        threshold_seconds: float,
    ) -> None:
        """
        Register callback to fire when idle exceeds threshold.

        Args:
            listener_id: Unique identifier for this listener
            callback: Sync callback to invoke when idle threshold met
            threshold_seconds: Minimum idle duration before firing

        Note:
            Callback is invoked from async context but should be sync.
            If callback needs async, wrap in asyncio.create_task().
        """
        async with self._lock:
            self._listeners[listener_id] = IdleListener(
                id=listener_id,
                callback=callback,
                threshold_seconds=threshold_seconds,
            )
            logger.info(
                "Registered idle listener %s (threshold=%.1fs)",
                listener_id,
                threshold_seconds,
                extra={
                    "listener_id": listener_id,
                    "threshold_seconds": threshold_seconds,
                },
            )

    async def unregister_idle_listener(self, listener_id: str) -> bool:
        """
        Unregister an idle listener.

        Returns:
            True if listener was found and removed, False otherwise.
        """
        async with self._lock:
            if listener_id in self._listeners:
                del self._listeners[listener_id]
                logger.info("Unregistered idle listener %s", listener_id)
                return True
            return False

    async def start(self) -> None:
        """Start the idle check loop."""
        if self._running:
            logger.warning("ActivityTracker already running")
            return

        self._running = True
        self._last_activity = time.monotonic()  # Reset on start
        self._task = asyncio.create_task(self._check_loop())
        logger.info(
            "ActivityTracker started (check_interval=%.1fs)",
            self._check_interval,
        )

    async def stop(self) -> None:
        """Stop the idle check loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ActivityTracker stopped")

    @property
    def is_running(self) -> bool:
        """Check if tracker is running."""
        return self._running

    @property
    def listener_count(self) -> int:
        """Get number of registered listeners."""
        return len(self._listeners)

    async def _check_loop(self) -> None:
        """Main loop - periodically check idle conditions."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)

                idle = self.idle_seconds()

                async with self._lock:
                    for listener in self._listeners.values():
                        if not listener.fired and idle >= listener.threshold_seconds:
                            logger.info(
                                "Idle threshold met for %s (idle=%.1fs, threshold=%.1fs)",
                                listener.id,
                                idle,
                                listener.threshold_seconds,
                                extra={
                                    "listener_id": listener.id,
                                    "idle_seconds": idle,
                                    "threshold_seconds": listener.threshold_seconds,
                                },
                            )
                            try:
                                listener.callback()
                                listener.fired = True
                            except Exception as e:
                                logger.error(
                                    "Idle listener %s callback error: %s",
                                    listener.id,
                                    str(e),
                                    exc_info=True,
                                    extra={
                                        "listener_id": listener.id,
                                        "error": str(e),
                                    },
                                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "ActivityTracker check loop error: %s",
                    str(e),
                    exc_info=True,
                )


# Singleton for kernel-wide activity tracking
_activity_tracker: ActivityTracker | None = None


def get_activity_tracker() -> ActivityTracker:
    """
    Get the global ActivityTracker instance.

    Creates a new instance if one doesn't exist.
    """
    global _activity_tracker
    if _activity_tracker is None:
        _activity_tracker = ActivityTracker()
    return _activity_tracker


def set_activity_tracker(tracker: ActivityTracker | None) -> None:
    """
    Set the global ActivityTracker instance.

    Use for testing or custom configurations.
    Pass None to reset the singleton.
    """
    global _activity_tracker
    _activity_tracker = tracker
