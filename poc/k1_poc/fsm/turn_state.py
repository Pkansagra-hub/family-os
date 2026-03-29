"""
poc.k1_poc.fsm.turn_state -- FSMTurnState (ephemeral turn tracking).

V2 Design Ref: Section 4 (FSMTurnState dataclass)
M2 E2.2.3: Added max_depth overflow and TTL expiry with dead-letter support.

This state is NOT persisted in SessionState. It lives in the Controller's
memory. It tracks transient coordination state that the FSM needs to route
events correctly during concurrent operation.

Lifecycle:
  - Created once when ConciergeController initializes.
  - pending_results: cleared after WeaveBatcher drains all entries.

Cancellation tracking moved to protocols.cancel_handler.CancellationHandler (Epic 2.1).
Suspension context moved to protocols.suspension_manager.SuspensionManager (Epic 2.2).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from k1.bus.envelope import Envelope

if TYPE_CHECKING:
    from poc.k1_poc.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)


@dataclass
class FSMTurnState:
    """Ephemeral state tracked by the FSM Controller across turns.

    Not visible to the LLM. The FSM handles these structurally:

    | Field                 | FSM Behaviour                                       |
    |-----------------------|-----------------------------------------------------|
    | pending_results       | Queues task.complete payloads for Weave delivery     |

    Cancellation: delegated to CancellationHandler (protocols.cancel_handler)
    Suspension:   delegated to SuspensionManager (protocols.suspension_manager)
    """

    pending_results: deque[dict[str, Any]] = field(default_factory=deque)

    # M9 E9.4.4: Optional ledger writer for event sourcing.
    _ledger: LedgerWriter | None = field(default=None, repr=False)

    # M8 E8.3.2: Deferred results held until next user input.
    # When WeavePolicy returns DEFER, results are moved here instead of
    # being scheduled for flush.  On next user input, they are injected
    # into the STANDARD prompt as async_results_context.
    deferred_results: list[dict[str, Any]] = field(default_factory=list)

    # M2 E2.2.3: Configurable depth and TTL guards
    max_depth: int = 16
    ttl_seconds: int = 300

    def set_ledger(self, writer: LedgerWriter) -> None:
        """Attach ledger writer post-construction.

        M9 E9.4.4: Allows wiring ledger after FSMTurnState is
        already created (e.g. bootstrap sequence order).
        """
        self._ledger = writer

    # ------------------------------------------------------------------
    # pending_results management (Epic 8.3.2, M2 E2.2.3)
    # ------------------------------------------------------------------

    def enqueue_result(
        self,
        task_id: str,
        result: dict[str, Any],
        envelope: Envelope,
        urgency: str = "normal",
    ) -> dict[str, Any] | None:
        """Queue a task.complete result for deferred Front delivery.

        Called when task.complete arrives and Front is busy (FrontLock.busy=True).
        The result stays here until WeaveBatcher drains it.

        M2 E2.2.3: If the queue is at max_depth, the oldest result is evicted
        and returned so the caller can publish a dead-letter event.

        M8 E8.1.4: Added urgency label for priority profiling.

        Args:
            task_id: The completed task's ID.
            result: The task result payload.
            envelope: The original task.complete envelope (for causal ordering).
            urgency: Priority label -- "critical", "normal", or "low".

        Returns:
            The evicted result dict if overflow occurred, else None.
        """
        evicted: dict[str, Any] | None = None
        if len(self.pending_results) >= self.max_depth:
            evicted = self.pending_results.popleft()
            logger.warning(
                "FSMTurnState: overflow at max_depth=%d, evicting oldest task=%s",
                self.max_depth,
                evicted.get("task_id", "?"),
            )

        self.pending_results.append(
            {
                "task_id": task_id,
                "result": result,
                "envelope_id": envelope.envelope_id,
                "parent_id": envelope.parent_id,
                "queued_at_ns": time.monotonic_ns(),
                "urgency": urgency,
            }
        )

        # M9 E9.4.4: Write-before-mutate -- emit WeaveCandidateArrived
        if self._ledger is not None:
            from poc.k1_poc.events.weave import WeaveCandidateArrived

            evt = WeaveCandidateArrived(
                task_id=task_id,
                result_data=result,
            )
            self._ledger.append_sync(evt)

        logger.debug(
            "FSMTurnState: queued result for task %s (queue depth: %d)",
            task_id,
            len(self.pending_results),
        )
        return evicted

    def drain_results(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Drain all pending results for Front presentation.

        M2 E2.2.3: Filters out expired results (beyond TTL). Returns a tuple
        of (valid_results, expired_results). The caller publishes dead-letter
        events for each expired result.

        Returns:
            (valid, expired) -- both lists; the deque is cleared.
        """
        if not self.pending_results:
            return [], []

        now_ns = time.monotonic_ns()
        ttl_ns = self.ttl_seconds * 1_000_000_000

        valid: list[dict[str, Any]] = []
        expired: list[dict[str, Any]] = []

        for item in self.pending_results:
            queued_at = item.get("queued_at_ns", 0)
            if queued_at and (now_ns - queued_at) >= ttl_ns:
                expired.append(item)
            else:
                valid.append(item)

        self.pending_results.clear()

        # M9 E9.4.4: Write-before-mutate -- emit WeaveEmitted for drained results
        if self._ledger is not None and valid:
            from poc.k1_poc.events.weave import WeaveEmitted

            # Collect task_ids of drained results as candidate_event_ids
            candidate_ids = [v.get("task_id", "") for v in valid]
            evt = WeaveEmitted(
                candidate_event_ids=candidate_ids,
                response_text_preview="drained",
            )
            self._ledger.append_sync(evt)

        if valid:
            logger.debug("FSMTurnState: drained %d valid pending results", len(valid))
        if expired:
            logger.warning(
                "FSMTurnState: expired %d pending results (ttl=%ds)",
                len(expired),
                self.ttl_seconds,
            )
        return valid, expired

    @property
    def has_pending_results(self) -> bool:
        """True if there are queued results awaiting Weave delivery."""
        return len(self.pending_results) > 0

    @property
    def depth(self) -> int:
        """Current queue depth."""
        return len(self.pending_results)

    # ------------------------------------------------------------------
    # 8.3.2 -- Deferred results management
    # ------------------------------------------------------------------

    def mark_deferred(
        self,
        results: list[dict[str, Any]] | None = None,
        max_consecutive_defers: int = 5,
    ) -> list[dict[str, Any]]:
        """Move pending results to deferred list.

        M8 E8.3.2: When WeavePolicy returns DEFER, results are held
        until the next user input.  Each result tracks its defer_count.
        If any result exceeds max_consecutive_defers, it is returned
        in the force_deliver list for immediate BATCH delivery.

        Args:
            results: Specific results to defer.  If None, drains all
                     pending_results (valid only, expired are discarded).
            max_consecutive_defers: Max times a result can be deferred
                                    before forced delivery (default 5).

        Returns:
            List of results that exceeded max_consecutive_defers and
            must be force-delivered via BATCH.
        """
        if results is None:
            valid, _expired = self.drain_results()
            items = valid
        else:
            items = list(results)

        force_deliver: list[dict[str, Any]] = []

        for item in items:
            defer_count = item.get("defer_count", 0) + 1
            item["defer_count"] = defer_count
            item["deferred"] = True

            if defer_count > max_consecutive_defers:
                logger.info(
                    "FSMTurnState: force-delivering task %s after %d defers",
                    item.get("task_id", "?"),
                    defer_count,
                )
                force_deliver.append(item)
            else:
                self.deferred_results.append(item)
                logger.debug(
                    "FSMTurnState: deferred task %s (defer_count=%d)",
                    item.get("task_id", "?"),
                    defer_count,
                )

        return force_deliver

    def drain_deferred(self) -> list[dict[str, Any]]:
        """Drain all deferred results for injection into STANDARD prompt.

        M8 E8.3.2: Called on user input (_on_user_input).  Returns the
        deferred results for injection as async_results_context in the
        STANDARD prompt.  The list is cleared after draining.

        Returns:
            List of deferred result dicts.
        """
        if not self.deferred_results:
            return []
        results = list(self.deferred_results)
        self.deferred_results.clear()
        logger.debug(
            "FSMTurnState: drained %d deferred results for STANDARD injection",
            len(results),
        )
        return results

    @property
    def has_deferred_results(self) -> bool:
        """True if there are deferred results awaiting next user input."""
        return len(self.deferred_results) > 0

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all ephemeral state. Called at session end or test teardown."""
        self.pending_results.clear()
        self.deferred_results.clear()

    # ------------------------------------------------------------------
    # M9 E9.4.4: Ledger rebuild
    # ------------------------------------------------------------------

    def rebuild_from_projection(self, projected: deque[dict[str, Any]]) -> int:
        """Rebuild pending_results from a ledger projection.

        M9 E9.4.4: Called by CrashRecoveryOrchestrator after
        project_pending_results() replays weave candidate events.

        Returns:
            Number of pending results restored.
        """
        self.pending_results.clear()
        for item in projected:
            self.pending_results.append(item)
        return len(self.pending_results)
        return len(self.pending_results)
