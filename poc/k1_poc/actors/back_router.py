"""
poc.k1_poc.actors.back_router -- Back Mailbox Topic Router (M7 E7.3).

Routes incoming Back-bound envelopes to the correct handler based on
envelope.topic. Integrates with BackPool for:
  - Synchronous cancel dispatch (no worker slot needed -- immediate)
  - Late-envelope discard (task already completed/cancelled)
  - CancellationToken extraction from TaskLease for handler injection

Routing table:
  task.dispatch.v1          -> back_handler       (async, needs pool worker)
  task.resume.v1            -> back_resume_handler (async, needs pool worker)
  task.cancel.v1            -> back_cancel_handler (sync, NO pool worker)
  clarification.response.v1 -> back_resume_handler (async, needs pool worker)
  unknown topic             -> None (log warning + discard)

V3 Milestone 7 E7.3.1-7.3.4
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from poc.k1_poc.actors.back_pool import BackPool

logger = logging.getLogger(__name__)


# =====================================================================
# E7.3.1 -- BackTopicRouter
# =====================================================================


class BackTopicRouter:
    """Topic-based router for Back mailbox envelopes.

    M7 E7.3.1: Replaces the pattern where the coordinator consumer
    dispatches ALL Back envelopes identically to back_handler. Routes
    each envelope to the correct handler based on topic.

    M7 E7.3.2: Distinguishes cancel (synchronous, no pool worker)
    from dispatch/resume (async, requires pool worker).

    M7 E7.3.4: Discards late-arriving envelopes for tasks whose
    lease has been RELEASED or CANCELLED.

    Attributes:
        _back_pool:      BackPool reference for lease/release checks.
        _routing_table:  Topic string -> handler function mapping.
        _stats:          Routing statistics for observability.
    """

    def __init__(self, back_pool: BackPool | None = None) -> None:
        from poc.k1_poc.actors.back import back_cancel_handler, back_handler, back_resume_handler
        from poc.k1_poc.bus.topics import (
            TOPIC_CLARIFICATION_RESPONSE,
            TOPIC_TASK_CANCEL,
            TOPIC_TASK_DISPATCH,
            TOPIC_TASK_RESUME,
        )

        self._back_pool = back_pool
        self._back_cancel_handler = back_cancel_handler

        # E7.3.1: Routing table -- topic string -> handler function
        self._routing_table: dict[str, Callable] = {
            TOPIC_TASK_DISPATCH: back_handler,
            TOPIC_TASK_RESUME: back_resume_handler,
            TOPIC_TASK_CANCEL: back_cancel_handler,
            TOPIC_CLARIFICATION_RESPONSE: back_resume_handler,
        }

        # Cancel topics bypass pool (E7.3.2)
        self._cancel_topics: frozenset[str] = frozenset({TOPIC_TASK_CANCEL})

        # Stats for observability
        self._stats: dict[str, int] = {
            "routed": 0,
            "cancel_sync": 0,
            "discarded_late": 0,
            "discarded_unknown": 0,
        }

        logger.info(
            "BackTopicRouter: initialized with %d routes, " "pool=%s",
            len(self._routing_table),
            "attached" if back_pool is not None else "detached",
        )

    # -----------------------------------------------------------------
    # Core routing (E7.3.1)
    # -----------------------------------------------------------------

    def route(self, envelope: Any) -> Callable | None:
        """Route an envelope to the correct Back handler.

        M7 E7.3.1: Returns the handler function for the envelope's
        topic. Returns None if the envelope should be discarded
        (unknown topic or late arrival for a completed/cancelled task).

        Args:
            envelope: Bus Envelope with .topic and .payload.

        Returns:
            Handler function, or None to discard.
        """
        topic = getattr(envelope, "topic", "") or ""
        task_id = self._extract_task_id(envelope)

        # E7.3.4: Discard late-arriving envelopes for completed/cancelled tasks
        if self._should_discard(task_id, topic):
            self._stats["discarded_late"] += 1
            logger.debug(
                "BackTopicRouter.route: discarding late envelope "
                "topic=%s task_id=%s (task already released/cancelled)",
                topic,
                task_id,
            )
            return None

        # Look up handler in routing table
        handler = self._routing_table.get(topic)
        if handler is None:
            self._stats["discarded_unknown"] += 1
            logger.warning(
                "BackTopicRouter.route: unknown topic=%r " "envelope_id=%s -- discarding",
                topic,
                getattr(envelope, "envelope_id", None),
            )
            return None

        # Track stats
        if topic in self._cancel_topics:
            self._stats["cancel_sync"] += 1
        self._stats["routed"] += 1

        return handler

    # -----------------------------------------------------------------
    # Cancel topic check (E7.3.2)
    # -----------------------------------------------------------------

    def is_cancel_topic(self, topic: str) -> bool:
        """Check if a topic is a cancel topic (synchronous dispatch).

        M7 E7.3.2: Cancel envelopes bypass the pool -- they are
        processed synchronously to ensure immediate cooperative
        termination of the running Back LLM's react_loop.

        Args:
            topic: The envelope topic string.

        Returns:
            True if the topic is a cancel topic.
        """
        return topic in self._cancel_topics

    # -----------------------------------------------------------------
    # Late-envelope discard (E7.3.4)
    # -----------------------------------------------------------------

    def _should_discard(self, task_id: str, topic: str) -> bool:
        """Check if an envelope should be discarded as a late arrival.

        M7 E7.3.4: Envelopes for tasks whose lease has been RELEASED
        or CANCELLED are discarded. This prevents:
          (a) task.complete arriving after cancel (wastes worker slot)
          (b) stale task.resume for already-completed tasks (race)

        Cancel envelopes are NEVER discarded -- they are how we
        stop things.

        Args:
            task_id: The task this envelope targets.
            topic: The envelope topic.

        Returns:
            True if the envelope should be discarded.
        """
        if not task_id or self._back_pool is None:
            return False

        # Cancel envelopes are never discarded -- they stop running tasks
        if topic in self._cancel_topics:
            return False

        # Check if task was previously released/cancelled
        return self._back_pool.is_task_released(task_id)

    # -----------------------------------------------------------------
    # CancellationToken extraction (E7.3.3)
    # -----------------------------------------------------------------

    def get_cancel_token_for_task(self, task_id: str) -> Any:
        """Extract CancellationToken from the task's lease.

        M7 E7.3.3: The lease's CancellationToken is passed to
        back_handler and back_resume_handler so that
        _build_cancellation_check returns a real check instead
        of _never_cancel.

        Args:
            task_id: The task to look up.

        Returns:
            CancellationToken if a lease exists, else None.
        """
        if self._back_pool is None:
            return None

        lease = self._back_pool.get_lease(task_id)
        if lease is not None and lease.cancellation_token is not None:
            return lease.cancellation_token
        return None

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

    def get_stats(self) -> dict[str, int]:
        """Return routing statistics for observability.

        Returns:
            Dict with routed, cancel_sync, discarded_late,
            discarded_unknown counts.
        """
        return dict(self._stats)

    def __repr__(self) -> str:
        return (
            f"BackTopicRouter(routes={len(self._routing_table)}, "
            f"pool={'attached' if self._back_pool else 'detached'}, "
            f"stats={self._stats})"
        )


__all__ = [
    "BackTopicRouter",
]
