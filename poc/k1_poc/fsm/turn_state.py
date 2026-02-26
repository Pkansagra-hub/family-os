"""
poc.k1_poc.fsm.turn_state -- FSMTurnState (ephemeral turn tracking).

V2 Design Ref: Section 4 (FSMTurnState dataclass)

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
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from k1.bus.envelope import Envelope

logger = logging.getLogger(__name__)


@dataclass
class FSMTurnState:
    """Ephemeral state tracked by the FSM Controller across turns.

    Not visible to the LLM. The FSM handles these structurally:

    | Field                 | FSM Behavior                                        |
    |-----------------------|-----------------------------------------------------|
    | pending_results       | Queues task.complete payloads for Weave delivery     |

    Cancellation: delegated to CancellationHandler (protocols.cancel_handler)
    Suspension:   delegated to SuspensionManager (protocols.suspension_manager)
    """

    pending_results: deque[dict[str, Any]] = field(default_factory=deque)

    # ------------------------------------------------------------------
    # pending_results management (Epic 8.3.2)
    # ------------------------------------------------------------------

    def enqueue_result(
        self,
        task_id: str,
        result: dict[str, Any],
        envelope: Envelope,
    ) -> None:
        """Queue a task.complete result for deferred Front delivery.

        Called when task.complete arrives and Front is busy (FrontLock.busy=True).
        The result stays here until WeaveBatcher drains it.

        Args:
            task_id: The completed task's ID.
            result: The task result payload.
            envelope: The original task.complete envelope (for causal ordering).
        """
        self.pending_results.append(
            {
                "task_id": task_id,
                "result": result,
                "envelope_id": envelope.envelope_id,
                "parent_id": envelope.parent_id,
                "queued_at_ns": envelope.created_ns,
            }
        )
        logger.debug(
            "FSMTurnState: queued result for task %s (queue depth: %d)",
            task_id,
            len(self.pending_results),
        )

    def drain_results(self) -> list[dict[str, Any]]:
        """Drain all pending results for Front presentation.

        Returns a list of all queued results and clears the deque.
        WeaveBatcher calls this after the batch window expires.
        """
        results = list(self.pending_results)
        self.pending_results.clear()
        if results:
            logger.debug("FSMTurnState: drained %d pending results", len(results))
        return results

    @property
    def has_pending_results(self) -> bool:
        """True if there are queued results awaiting Weave delivery."""
        return len(self.pending_results) > 0

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all ephemeral state. Called at session end or test teardown."""
        self.pending_results.clear()
