"""
k1.concierge.actors.ready_queue -- Dependency-Ordered Ready Queue (M7 E7.4).

Holds Back-bound envelopes with depends_on until the dependency task
completes. Envelopes without depends_on are immediately ready. The
queue is polled by the coordinator's consumer loop each cycle.

Key design:
  - enqueue() classifies each envelope as immediate/waiting/dep_failed/
    circular/unknown_dep.
  - dequeue_ready() drains all currently-ready envelopes in FIFO order.
  - notify_completed(task_id, status) transitions waiting envelopes to
    ready (if predecessor completed) or marks them as dependency-failed
    (if predecessor failed/cancelled).
  - Circular dependency detection at enqueue time prevents deadlocks.
  - Unknown dependency IDs trigger immediate dispatch with a warning.

Distinct from task/dependency_queue.py:
  TaskDependencyQueue operates on TaskDispatch objects and performs
  $ref parameter hydration. ReadyQueue operates at the envelope/pool
  layer and controls when Back workers are acquired.

V3 Milestone 7 E7.4.1-7.4.3
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================================
# E7.4.1 -- ReadyQueue
# =====================================================================


@dataclass
class ReadyQueue:
    """Dependency-ordered envelope queue for BackPool dispatch.

    M7 E7.4.1: Holds envelopes whose depends_on has not yet completed.
    Released envelopes are made available via dequeue_ready() in FIFO
    order.

    M7 E7.4.2: notify_completed signals task completion and releases
    dependent envelopes. Failed/cancelled predecessors cause dependents
    to fail with reason='dependency_failed'.

    M7 E7.4.3: Circular and missing dependency detection at enqueue
    time prevents deadlocks and silently-stuck tasks.

    Attributes:
        _ready:             FIFO list of envelopes ready for dispatch.
        _waiting:           depends_on task_id -> [(envelope, task_id)].
        _completed:         task_id -> status ('completed'/'failed'/
                            'cancelled'/'error').
        _known_tasks:       Set of all task_ids seen (dispatched or
                            completed).
        _dep_graph:         task_id -> depends_on (for cycle detection).
        _stats:             Counters for observability.
    """

    _ready: list[Any] = field(default_factory=list)
    _waiting: dict[str, list[tuple[Any, str]]] = field(default_factory=dict)
    _completed: dict[str, str] = field(default_factory=dict)
    _known_tasks: set[str] = field(default_factory=set)
    _dep_graph: dict[str, str] = field(default_factory=dict)
    _stats: dict[str, int] = field(
        default_factory=lambda: {
            "immediate": 0,
            "enqueued": 0,
            "released": 0,
            "failed_dep": 0,
            "circular": 0,
            "unknown_dep": 0,
        }
    )

    # -----------------------------------------------------------------
    # Task registration
    # -----------------------------------------------------------------

    def register_task(self, task_id: str) -> None:
        """Register a task_id as known (dispatched to Back).

        Called when the coordinator dispatches a task so that future
        depends_on references to this task_id are recognized.

        Args:
            task_id: The task to register.
        """
        self._known_tasks.add(task_id)

    # -----------------------------------------------------------------
    # Enqueue (E7.4.1 + E7.4.3)
    # -----------------------------------------------------------------

    def enqueue(
        self,
        envelope: Any,
        depends_on: str | None = None,
    ) -> tuple[str, list[str]]:
        """Enqueue an envelope, optionally with a dependency.

        M7 E7.4.1: Envelopes without depends_on are immediately
        ready. Envelopes with depends_on wait until the dependency
        completes.

        M7 E7.4.3: Unknown depends_on triggers immediate dispatch
        with a warning. Circular dependencies fail all participants.

        Args:
            envelope: The Back-bound bus envelope.
            depends_on: Task ID this envelope depends on, or None.

        Returns:
            Tuple of (status, failed_task_ids):
              status:
                'immediate'   -- no dependency, placed in ready queue
                'waiting'     -- buffered, waiting for depends_on
                'dep_failed'  -- dependency already failed/cancelled
                'circular'    -- cycle detected, this task + cycle
                                 participants failed
                'unknown_dep' -- depends_on not recognized, placed in
                                 ready queue (dispatch immediately)
              failed_task_ids:
                Empty list except for 'circular', where it contains
                the task_ids of ALL cycle participants (including
                those removed from the waiting queue).
        """
        task_id = self._extract_task_id(envelope)
        self._known_tasks.add(task_id)

        # No dependency -- immediately ready
        if depends_on is None:
            self._ready.append(envelope)
            self._stats["immediate"] += 1
            return "immediate", []

        # 7.4.3: Unknown dependency -- dispatch immediately with warning
        if depends_on not in self._known_tasks and depends_on not in self._completed:
            logger.warning(
                "ReadyQueue.enqueue: unknown depends_on=%s for "
                "task=%s -- dispatching immediately",
                depends_on,
                task_id,
            )
            self._ready.append(envelope)
            self._stats["unknown_dep"] += 1
            return "unknown_dep", []

        # 7.4.3: Circular dependency detection
        if self._has_cycle(task_id, depends_on):
            logger.error(
                "ReadyQueue.enqueue: circular dependency detected "
                "task=%s -> depends_on=%s -- failing all participants",
                task_id,
                depends_on,
            )
            # Collect and remove all cycle participants from waiting
            cycle_failed = self._remove_cycle_participants(task_id, depends_on)
            # Include the current task_id in the failed set
            cycle_failed.append(task_id)
            self._stats["circular"] += 1
            return "circular", cycle_failed

        # Dependency already completed?
        if depends_on in self._completed:
            dep_status = self._completed[depends_on]
            if dep_status == "completed":
                # Predecessor finished successfully -- immediately ready
                self._ready.append(envelope)
                self._stats["immediate"] += 1
                return "immediate", []
            else:
                # Predecessor failed/cancelled -- dependent fails too
                self._stats["failed_dep"] += 1
                logger.info(
                    "ReadyQueue.enqueue: depends_on=%s has status=%s "
                    "-- task=%s fails with dep_failed",
                    depends_on,
                    dep_status,
                    task_id,
                )
                return "dep_failed", [task_id]

        # Buffer: dependency not yet complete
        self._dep_graph[task_id] = depends_on
        waiters = self._waiting.setdefault(depends_on, [])
        waiters.append((envelope, task_id))
        self._stats["enqueued"] += 1

        logger.info(
            "ReadyQueue.enqueue: task=%s waiting for depends_on=%s " "(queue_depth=%d)",
            task_id,
            depends_on,
            len(waiters),
        )
        return "waiting", []

    # -----------------------------------------------------------------
    # Dequeue (E7.4.1)
    # -----------------------------------------------------------------

    def dequeue_ready(self) -> list[Any]:
        """Return all envelopes that are ready for dispatch.

        M7 E7.4.1: Drains the internal ready list in FIFO order.
        Called by the coordinator's consumer loop each cycle.

        Returns:
            List of envelopes ready for BackPool.acquire_worker().
        """
        if not self._ready:
            return []
        ready = list(self._ready)
        self._ready.clear()
        return ready

    # -----------------------------------------------------------------
    # Notify completion (E7.4.2)
    # -----------------------------------------------------------------

    def notify_completed(
        self,
        task_id: str,
        status: str = "completed",
    ) -> tuple[list[Any], list[str]]:
        """Notify that a task has completed, failed, or been cancelled.

        M7 E7.4.2: Releases dependent envelopes if predecessor
        completed successfully. Marks dependents as failed if
        predecessor status is not 'completed'.

        Args:
            task_id: The completed task's ID.
            status: Completion status: 'completed', 'failed',
                    'cancelled', or 'error'.

        Returns:
            Tuple of (released_envelopes, failed_task_ids):
              released_envelopes: Envelopes now ready for dispatch
                (only when status='completed').
              failed_task_ids: Task IDs of dependents that should
                be failed (when predecessor failed/cancelled).
        """
        self._completed[task_id] = status
        self._known_tasks.add(task_id)

        waiters = self._waiting.pop(task_id, [])
        released_envelopes: list[Any] = []
        failed_task_ids: list[str] = []

        for envelope, waiting_task_id in waiters:
            # Clean up dependency graph
            self._dep_graph.pop(waiting_task_id, None)

            if status == "completed":
                # Predecessor succeeded -- dependent is ready
                self._ready.append(envelope)
                self._stats["released"] += 1
                released_envelopes.append(envelope)
                logger.info(
                    "ReadyQueue.notify_completed: released task=%s " "(predecessor=%s completed)",
                    waiting_task_id,
                    task_id,
                )
            else:
                # Predecessor failed/cancelled -- dependent fails
                self._stats["failed_dep"] += 1
                failed_task_ids.append(waiting_task_id)
                logger.info(
                    "ReadyQueue.notify_completed: task=%s fails " "(predecessor=%s status=%s)",
                    waiting_task_id,
                    task_id,
                    status,
                )

        return released_envelopes, failed_task_ids

    # -----------------------------------------------------------------
    # Cycle detection (E7.4.3)
    # -----------------------------------------------------------------

    def _has_cycle(self, task_id: str, depends_on: str) -> bool:
        """Check if adding task_id -> depends_on creates a cycle.

        M7 E7.4.3: Walks the dependency graph from depends_on
        following existing edges. If we reach task_id, a cycle exists.

        Args:
            task_id: The new task to add.
            depends_on: The dependency to add.

        Returns:
            True if adding this edge creates a cycle.
        """
        # Walk from depends_on through existing graph edges
        visited: set[str] = {task_id}
        current = depends_on
        while current in self._dep_graph:
            if current in visited:
                return True
            visited.add(current)
            current = self._dep_graph[current]
        # Check if the chain ends at task_id (direct or transitive cycle)
        return current == task_id

    def _remove_cycle_participants(
        self,
        task_id: str,
        depends_on: str,
    ) -> list[str]:
        """Remove all cycle participants from the waiting queue.

        M7 E7.4.3: Finds all tasks in the cycle and removes their
        envelopes from the waiting queue.

        Args:
            task_id: The new task that triggered cycle detection.
            depends_on: The dependency that completes the cycle.

        Returns:
            List of task_ids that were removed (cycle participants).
        """
        # Trace the cycle: task_id -> depends_on -> ... -> task_id
        cycle_tasks: list[str] = []
        current = depends_on
        while current != task_id and current in self._dep_graph:
            cycle_tasks.append(current)
            current = self._dep_graph[current]

        # Remove cycle participants from waiting and dep_graph
        removed_task_ids: list[str] = []
        for ct in cycle_tasks:
            self._dep_graph.pop(ct, None)
            # Find and remove from waiting queues
            for dep_id, waiters in list(self._waiting.items()):
                original_len = len(waiters)
                self._waiting[dep_id] = [(env, tid) for env, tid in waiters if tid != ct]
                if len(self._waiting[dep_id]) != original_len:
                    removed_task_ids.append(ct)
                if not self._waiting[dep_id]:
                    del self._waiting[dep_id]

        return removed_task_ids

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_task_id(envelope: Any) -> str:
        """Extract task_id from envelope payload."""
        try:
            payload_bytes = getattr(envelope, "payload", None)
            if payload_bytes:
                payload = json.loads(payload_bytes)
                return payload.get("task_id", "")
        except Exception:
            pass
        return ""

    # -----------------------------------------------------------------
    # State queries
    # -----------------------------------------------------------------

    @property
    def ready_count(self) -> int:
        """Number of envelopes ready for dispatch."""
        return len(self._ready)

    @property
    def waiting_count(self) -> int:
        """Number of envelopes waiting for dependencies."""
        return sum(len(v) for v in self._waiting.values())

    @property
    def total_pending(self) -> int:
        """Total envelopes in queue (ready + waiting)."""
        return self.ready_count + self.waiting_count

    def is_task_completed(self, task_id: str) -> bool:
        """Check if a task has been completed (any status)."""
        return task_id in self._completed

    def get_task_status(self, task_id: str) -> str | None:
        """Get the completion status of a task."""
        return self._completed.get(task_id)

    def get_stats(self) -> dict[str, int]:
        """Return queue statistics for observability."""
        return dict(self._stats)

    def get_queue_state(self) -> dict[str, Any]:
        """Return a snapshot of the queue state for observability.

        Returns:
            Dict with ready, waiting, completed, known_tasks counts
            and detailed waiting list.
        """
        return {
            "ready": self.ready_count,
            "waiting": self.waiting_count,
            "completed_tasks": len(self._completed),
            "known_tasks": len(self._known_tasks),
            "waiting_details": {
                dep_id: [tid for _, tid in waiters] for dep_id, waiters in self._waiting.items()
            },
        }

    def __repr__(self) -> str:
        return (
            f"ReadyQueue(ready={self.ready_count}, "
            f"waiting={self.waiting_count}, "
            f"completed={len(self._completed)})"
        )


__all__ = [
    "ReadyQueue",
]
