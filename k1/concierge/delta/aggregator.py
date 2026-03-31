"""
k1.concierge.delta.aggregator -- Batches SessionState deltas in 500ms windows.

V2 Design Ref: Section 5, DeltaAggregator Write Pipeline

Flow:
    Back emits deltas -> DeltaAggregator collects in 500ms window
    -> deduplicates by section+key (last-write-wins)
    -> orders by causal chain (parent_delta_id before child)
    -> flush callback delivers batch to FSM.apply_deltas()

The 500ms window matches the WeaveBatcher window (V2 Section 10)
for consistency.  Both use the same batching pattern: collect,
wait for stragglers, flush.

Batching rules:
    1. First delta starts the batch timer (500ms).
    2. Subsequent deltas within the window are collected.
    3. When the window expires, all collected deltas are:
       a. Deduplicated by section+key (last-write-wins within batch).
       b. Ordered by causal chain (parent_delta_id before child).
       c. Forwarded to the flush callback for FSM application.
    4. If a new delta arrives AFTER flush but BEFORE next window,
       a new batch starts.

The timer is fixed-window (not sliding): once started, the window
duration does not extend when new deltas arrive.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from k1.concierge.config import get_config
from k1.concierge.delta.session_delta import SessionDelta

logger = logging.getLogger(__name__)

# Kept as module constant for backward compatibility; runtime reads from config
DEFAULT_BATCH_WINDOW_MS: int = 500


@dataclass
class DeltaBatch:
    """A collected batch of deltas ready for application.

    Attributes:
        deltas:         Deduplicated, causally-ordered deltas.
        batch_id:       Unique batch identifier (batch-N).
        collected_at_ns: Monotonic timestamp when batch was flushed.
        dedup_count:    Number of deltas removed by deduplication.
    """

    deltas: list[SessionDelta]
    batch_id: str
    collected_at_ns: int
    dedup_count: int = 0


class DeltaAggregator:
    """Collects SessionState deltas in fixed-window batches.

    The aggregator is the FSM's ingest point for Back-originated
    state changes.  It subscribes to delta bus topics and collects
    incoming deltas.  After the batch window expires, it deduplicates,
    orders, and forwards the batch to the flush callback.

    Attributes:
        batch_window_ms: Window duration in milliseconds (default 500).
    """

    __slots__ = (
        "batch_window_ms",
        "_flush_fn",
        "_pending",
        "_timer",
        "_batch_count",
        "_total_deltas",
        "_total_deduped",
    )

    def __init__(
        self,
        flush_fn: Callable[[DeltaBatch], Awaitable[None]],
        batch_window_ms: int | None = None,
    ) -> None:
        if batch_window_ms is None:
            batch_window_ms = get_config().delta.batch_window_ms
        self.batch_window_ms = batch_window_ms
        self._flush_fn = flush_fn
        self._pending: list[SessionDelta] = []
        self._timer: asyncio.Task[None] | None = None
        self._batch_count: int = 0
        self._total_deltas: int = 0
        self._total_deduped: int = 0
        logger.info(
            "DeltaAggregator initialized (batch_window_ms=%d, flush_fn=%s)",
            self.batch_window_ms,
            getattr(flush_fn, "__qualname__", type(flush_fn).__name__),
        )

    async def collect(self, delta: SessionDelta) -> None:
        """Collect a delta into the current batch.

        If this is the first delta in a new window, starts the batch
        timer.  Subsequent deltas extend the pending list but do NOT
        reset the timer (fixed window, not sliding).

        Args:
            delta: The SessionDelta to collect.
        """
        self._pending.append(delta)
        self._total_deltas += 1

        if self._timer is None:
            self._timer = asyncio.create_task(self._wait_and_flush())

    async def _wait_and_flush(self) -> None:
        """Wait for the batch window, then flush."""
        await asyncio.sleep(self.batch_window_ms / 1000.0)
        await self.flush()

    async def flush(self) -> DeltaBatch | None:
        """Flush pending deltas immediately.

        Cancels any active batch timer, deduplicates by section+key
        (last-write-wins), orders by causal chain, and invokes the
        flush callback.

        Can be called manually (e.g., at turn boundaries) or by the
        batch timer.

        Returns:
            The flushed DeltaBatch, or None if nothing to flush.
        """
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

        if not self._pending:
            return None

        raw = list(self._pending)
        self._pending.clear()

        # Dedup: last-write-wins per section+key
        deduped = self._dedup(raw)
        dedup_count = len(raw) - len(deduped)
        self._total_deduped += dedup_count

        # Order by causal chain
        ordered = self._causal_order(deduped)

        self._batch_count += 1
        batch = DeltaBatch(
            deltas=ordered,
            batch_id=f"batch-{self._batch_count}",
            collected_at_ns=time.monotonic_ns(),
            dedup_count=dedup_count,
        )

        logger.info(
            "DeltaAggregator flush: batch=%s deltas=%d deduped=%d",
            batch.batch_id,
            len(ordered),
            dedup_count,
        )

        await self._flush_fn(batch)
        return batch

    @staticmethod
    def _dedup(deltas: list[SessionDelta]) -> list[SessionDelta]:
        """Deduplicate deltas by section+key.  Last-write-wins.

        If two deltas target the same section+key within one batch,
        only the latest (by list position) is kept.  This prevents
        redundant writes (e.g., two task_state updates for the same
        task within 500ms).
        """
        seen: dict[str, SessionDelta] = {}
        for delta in deltas:
            seen[delta.dedup_key()] = delta  # last write wins
        return list(seen.values())

    @staticmethod
    def _causal_order(deltas: list[SessionDelta]) -> list[SessionDelta]:
        """Order deltas by causal chain (parent before child).

        Simple topological sort: deltas with no parent_delta_id (or
        parent not in this batch) come first, then children follow
        their parents.  This preserves causal consistency when the
        flush callback applies deltas sequentially.

        If no causal links exist (common case), input order is
        preserved via dict insertion order.
        """
        if len(deltas) <= 1:
            return deltas

        # Build lookup and classify
        by_id: dict[str, SessionDelta] = {d.delta_id: d for d in deltas}
        has_parent_in_batch: set[str] = {
            d.delta_id for d in deltas if d.parent_delta_id and d.parent_delta_id in by_id
        }

        # Roots: no parent in this batch
        roots = [d for d in deltas if d.delta_id not in has_parent_in_batch]

        # Children map: parent_id -> list of children
        children_map: dict[str, list[SessionDelta]] = {}
        for d in deltas:
            if d.parent_delta_id and d.parent_delta_id in by_id:
                children_map.setdefault(d.parent_delta_id, []).append(d)

        # BFS from roots
        ordered: list[SessionDelta] = []
        queue = list(roots)
        visited: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current.delta_id in visited:
                continue
            visited.add(current.delta_id)
            ordered.append(current)
            for child in children_map.get(current.delta_id, []):
                queue.append(child)

        # Append any orphans (parent not in this batch -- should not happen
        # but defensive)
        for d in deltas:
            if d.delta_id not in visited:
                ordered.append(d)

        return ordered

    @property
    def pending_count(self) -> int:
        """Number of deltas awaiting flush."""
        return len(self._pending)

    @property
    def batch_count(self) -> int:
        """Total batches flushed since creation."""
        return self._batch_count

    @property
    def stats(self) -> dict[str, int]:
        """Aggregator statistics for observability."""
        return {
            "batch_count": self._batch_count,
            "total_deltas": self._total_deltas,
            "total_deduped": self._total_deduped,
            "pending": len(self._pending),
        }
