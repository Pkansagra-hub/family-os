"""
poc.k1_poc.delta.applicator -- FSM Delta Applicator.

V2 Design Ref: Section 5, DeltaAggregator Write Pipeline
V2 Design Ref: Section 5, Single Writer Invariant

The DeltaApplicator is the FSM's entry point for applying batched
deltas to SessionState.  It receives a DeltaBatch from the
DeltaAggregator and applies each delta through MutationGuard
preflight checks.

Pipeline position:
    Back emits deltas -> bus -> DeltaAggregator (500ms batch)
    -> DeltaApplicator.apply(batch)
        -> MutationGuard.preflight() per delta (capacity check)
        -> Write to SS section
        -> Emit k1.session.state.updated.v1 (observability)

Eviction retry (V2 Section 5):
    If MutationGuard rejects a write due to section capacity:
    1. Attempt eviction of oldest entries from the section.
    2. Retry preflight after eviction.
    3. If still rejected, record the rejection and move on.

The existing MutationGuard (poc/k1_poc/sessionstate/guard.py) validates:
    1. Section capacity (does this fit in section budget?)
    2. Tier capacity (does this fit in HOT/WARM budget?)
    3. Total capacity (does this fit in 96KB total?)
Its Approval dataclass carries .approved (bool) and .reason (str).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from poc.k1_poc.delta.aggregator import DeltaBatch
from poc.k1_poc.delta.session_delta import SessionDelta

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    """Result of applying a delta batch to SessionState.

    Attributes:
        batch_id:   Batch identifier from DeltaBatch.
        applied:    Number of deltas successfully applied.
        rejected:   Number of deltas rejected by preflight.
        evicted:    Number of entries evicted to make room.
        rejections: List of rejection details for diagnostics.
    """

    batch_id: str
    applied: int = 0
    rejected: int = 0
    evicted: int = 0
    rejections: list[dict[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total deltas processed (applied + rejected)."""
        return self.applied + self.rejected

    @property
    def success_rate(self) -> float:
        """Fraction of deltas applied (0.0 to 1.0)."""
        if self.total == 0:
            return 1.0
        return self.applied / self.total


class DeltaApplicator:
    """Applies delta batches to SessionState via MutationGuard.

    For each delta in the batch:
        1. MutationGuard.preflight(section, operation, estimated_size)
        2. If approved: write to SS section.
        3. If rejected (capacity): attempt eviction, then retry once.
        4. Track applied/rejected/evicted counts.

    All callbacks are injectable for testability and decoupling.
    The DeltaApplicator does not import MutationGuard or SS directly;
    it operates through function callbacks.

    Attributes:
        _preflight_fn:  MutationGuard.preflight() callback.
                        Signature: (section, operation, estimated_size) -> approval
                        The returned object must have an ``approved`` bool attribute
                        and an optional ``reason`` str attribute.
        _write_fn:      Callback to write to a SS section.
                        Signature: async (section, key, operation, data) -> None
        _evict_fn:      Callback to evict from a section to WARM tier.
                        Signature: async (section, needed_bytes) -> evicted_count
        _notify_fn:     Callback to emit state.updated event.
                        Signature: async (batch_id, applied_count) -> None
    """

    __slots__ = ("_preflight_fn", "_write_fn", "_evict_fn", "_notify_fn")

    def __init__(
        self,
        preflight_fn: Callable[[str, str, int], Any] | None = None,
        write_fn: Callable[[str, str, str, dict], Awaitable[None]] | None = None,
        evict_fn: Callable[[str, int], Awaitable[int]] | None = None,
        notify_fn: Callable[[str, int], Awaitable[None]] | None = None,
    ) -> None:
        self._preflight_fn = preflight_fn
        self._write_fn = write_fn
        self._evict_fn = evict_fn
        self._notify_fn = notify_fn
        logger.info(
            "DeltaApplicator initialized (preflight=%s, write=%s, evict=%s, notify=%s)",
            preflight_fn is not None,
            write_fn is not None,
            evict_fn is not None,
            notify_fn is not None,
        )

    async def apply(self, batch: DeltaBatch) -> ApplyResult:
        """Apply a delta batch to SessionState.

        Processes each delta sequentially through preflight checks
        and writes.  After all deltas are processed, emits a
        notification if any were applied.

        Args:
            batch: The DeltaBatch from DeltaAggregator.

        Returns:
            ApplyResult with counts of applied/rejected/evicted.
        """
        result = ApplyResult(batch_id=batch.batch_id)

        for delta in batch.deltas:
            success = await self._apply_single(delta, result)
            if success:
                result.applied += 1
            else:
                result.rejected += 1

        # Emit observability notification
        if self._notify_fn is not None and result.applied > 0:
            await self._notify_fn(batch.batch_id, result.applied)

        logger.info(
            "DeltaApplicator: batch=%s applied=%d rejected=%d evicted=%d",
            batch.batch_id,
            result.applied,
            result.rejected,
            result.evicted,
        )
        return result

    async def _apply_single(self, delta: SessionDelta, result: ApplyResult) -> bool:
        """Apply a single delta with preflight check and eviction retry.

        Returns True if the delta was successfully applied, False if
        rejected after all retry attempts.
        """
        estimated_size = len(str(delta.data).encode("utf-8"))

        # Preflight capacity check
        if self._preflight_fn is not None:
            approval = self._preflight_fn(delta.section, delta.operation, estimated_size)
            if hasattr(approval, "approved") and not approval.approved:
                # Rejected -- attempt eviction and retry
                if self._evict_fn is not None:
                    evicted = await self._evict_fn(delta.section, estimated_size)
                    result.evicted += evicted
                    if evicted > 0:
                        # Retry preflight after eviction freed space
                        retry = self._preflight_fn(delta.section, delta.operation, estimated_size)
                        if hasattr(retry, "approved") and not retry.approved:
                            result.rejections.append(
                                {
                                    "delta_id": delta.delta_id,
                                    "section": delta.section,
                                    "reason": getattr(
                                        retry,
                                        "reason",
                                        "capacity exceeded after eviction",
                                    ),
                                }
                            )
                            logger.warning(
                                "Delta %s rejected after eviction: %s",
                                delta.delta_id,
                                getattr(retry, "reason", "unknown"),
                            )
                            return False
                    else:
                        # Eviction returned 0 -- nothing could be freed
                        result.rejections.append(
                            {
                                "delta_id": delta.delta_id,
                                "section": delta.section,
                                "reason": getattr(approval, "reason", "capacity exceeded"),
                            }
                        )
                        return False
                else:
                    # No eviction function available -- reject directly
                    result.rejections.append(
                        {
                            "delta_id": delta.delta_id,
                            "section": delta.section,
                            "reason": getattr(approval, "reason", "capacity exceeded"),
                        }
                    )
                    return False

        # Write to SessionState section
        if self._write_fn is not None:
            await self._write_fn(delta.section, delta.key, delta.operation, delta.data)

        return True
