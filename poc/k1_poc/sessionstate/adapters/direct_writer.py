"""
DirectWriterAdapter - Direct Mutation for Standalone/Testing
=============================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.3 Define Writer Port
ISSUE: 3.3.2

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Direct mutation for standalone operation and testing.
    Bypasses Concierge queue, calls MutationGuard directly.

USE CASE:
    - Standalone mode (no Concierge)
    - Testing
    - Development

SINGLE WRITER ENFORCEMENT:
    In standalone mode, DirectWriterAdapter IS the single writer.
    In production, Concierge uses ConciergeAdapter instead.

==============================================================================
CLASS: DirectWriterAdapter
==============================================================================
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from ..ports.writer import (
    BatchRequest,
    BatchResult,
    IWriterPort,
    MutationRequest,
    MutationResponse,
    MutationStatus,
    RejectionCategory,
    WriterAuthorization,
)

if TYPE_CHECKING:
    from ..guard import MutationGuard
    from ..manager import SessionStateManager

logger = logging.getLogger(__name__)


class DirectWriterAdapter(IWriterPort):
    """
    Direct mutation adapter for standalone mode.

    Bypasses Concierge, calls MutationGuard and applies mutations directly.
    Thread-safe with internal lock for mutation serialization.

    Attributes:
        _manager: SessionStateManager reference
        _guard: MutationGuard reference
        _writer_id: Writer identifier (default: 'direct')
        _authorized_writers: Set of authorized writer IDs
        _lock: Threading lock for mutation serialization
        _stats: Mutation statistics

    Example:
        adapter = DirectWriterAdapter(manager, guard)

        request = MutationRequest.create(
            section="beliefs_active",
            operation="append",
            data={"fact": "user prefers dark mode"},
            writer_id="direct",
            cognitive_trace_id=str(uuid.uuid4()),
            estimated_bytes=100,
        )

        response = adapter.request_mutation(request)

        if response.approved:
            print(f"New size: {response.new_size_bytes}")
        else:
            print(f"Rejected: {response.reason}")
    """

    __slots__ = (
        "_manager",
        "_guard",
        "_writer_id",
        "_authorized_writers",
        "_lock",
        "_stats",
    )

    def __init__(
        self,
        manager: SessionStateManager,
        guard: MutationGuard,
        writer_id: str = "direct",
        authorized_writers: Optional[Set[str]] = None,
    ) -> None:
        """
        Initialize DirectWriterAdapter.

        Args:
            manager: SessionStateManager to mutate
            guard: MutationGuard for preflight validation
            writer_id: Writer identifier for this adapter
            authorized_writers: Set of allowed writer IDs (None = all allowed)
        """
        self._manager = manager
        self._guard = guard
        self._writer_id = writer_id
        self._authorized_writers = authorized_writers  # None = all allowed
        self._lock = threading.RLock()
        self._stats: Dict[str, Any] = {
            "total_requests": 0,
            "applied_count": 0,
            "rejected_count": 0,
            "failed_count": 0,
            "total_duration_ms": 0.0,
            "total_bytes_delta": 0,
        }
        # M4 E4.5.4: Per-turn mutation tracking for audit events
        self._turn_stats: Dict[str, Any] = self._empty_turn_stats()

        logger.info(
            "DirectWriterAdapter initialized (writer_id=%s, session=%s)",
            writer_id,
            manager.session_id[:8] if manager.session_id else "none",
        )

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def writer_id(self) -> str:
        """
        Get writer identifier.

        Returns:
            str: Writer ID (default: 'direct')
        """
        return self._writer_id

    @property
    def is_connected(self) -> bool:
        """
        Check if writer port is connected and ready.

        Returns:
            bool: Always True for direct adapter
        """
        return True

    # =========================================================================
    # MUTATION OPERATIONS
    # =========================================================================

    def request_mutation(
        self,
        request: MutationRequest,
    ) -> MutationResponse:
        """
        Process a single mutation request.

        Args:
            request: Mutation request with all details

        Returns:
            MutationResponse: Result with status, reason, and metrics

        Flow:
            1. Check request expiration
            2. Validate writer authorization
            3. Call MutationGuard.preflight()
            4. If approved, apply mutation via SessionStateManager
            5. Return response with metrics
        """
        start_time = time.perf_counter()

        with self._lock:
            self._stats["total_requests"] += 1

            # 1. Check expiration
            if request.is_expired():
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._stats["rejected_count"] += 1
                self._record_turn_mutation(
                    request.section,
                    "rejected",
                    reason="Request expired",
                    duration_ms=duration_ms,
                )
                logger.debug(
                    "Request expired: request_id=%s, section=%s",
                    request.request_id,
                    request.section,
                )
                return MutationResponse.rejected(
                    request_id=request.request_id,
                    section=request.section,
                    operation=request.operation,
                    reason="Request expired",
                    category=RejectionCategory.VALIDATION,
                    duration_ms=duration_ms,
                )

            # 2. Validate writer authorization
            auth = self.validate_writer(request.writer_id)
            if not auth.authorized:
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._stats["rejected_count"] += 1
                self._record_turn_mutation(
                    request.section,
                    "rejected",
                    reason=auth.reason,
                    duration_ms=duration_ms,
                )
                logger.warning(
                    "Unauthorized writer: writer_id=%s, request_id=%s",
                    request.writer_id,
                    request.request_id,
                )
                return MutationResponse.rejected(
                    request_id=request.request_id,
                    section=request.section,
                    operation=request.operation,
                    reason=auth.reason,
                    category=RejectionCategory.AUTHORIZATION,
                    duration_ms=duration_ms,
                )

            # 2b. M4 E4.2.4: LLM tool writers may only write to
            #     llm_writable_sections; reject system-owned sections.
            if request.writer_id.startswith("tool:"):
                from poc.k1_poc.config import get_config

                allowlist = get_config().sessionstate.llm_writable_sections
                if request.section not in allowlist:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    self._stats["rejected_count"] += 1
                    self._record_turn_mutation(
                        request.section,
                        "rejected",
                        reason="system-owned section",
                        duration_ms=duration_ms,
                    )
                    logger.warning(
                        "Tool write to system-owned section blocked: "
                        "writer_id=%s, section=%s, request_id=%s",
                        request.writer_id,
                        request.section,
                        request.request_id,
                    )
                    return MutationResponse.rejected(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        reason=(
                            f"Section '{request.section}' is system-owned, " "not LLM-writable"
                        ),
                        category=RejectionCategory.AUTHORIZATION,
                        duration_ms=duration_ms,
                    )

            # 3. Preflight validation via MutationGuard
            approval = self._guard.preflight(
                section=request.section,
                operation=request.operation,
                estimated_bytes=request.estimated_bytes,
            )

            if not approval.approved:
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._stats["rejected_count"] += 1
                self._record_turn_mutation(
                    request.section,
                    "rejected",
                    reason=approval.reason,
                    duration_ms=duration_ms,
                )
                logger.info(
                    "Mutation rejected by guard: section=%s, op=%s, reason=%s, trace=%s",
                    request.section,
                    request.operation,
                    approval.reason,
                    request.cognitive_trace_id,
                )
                return MutationResponse.rejected(
                    request_id=request.request_id,
                    section=request.section,
                    operation=request.operation,
                    reason=approval.reason,
                    category=self._map_rejection_category(approval.reason_code),
                    available_bytes=approval.total_available_bytes,
                    duration_ms=duration_ms,
                )

            # 4. Apply mutation via manager
            try:
                result = self._manager.mutate(
                    section=request.section,
                    operation=request.operation,
                    data=request.data,
                    estimated_bytes=request.estimated_bytes,
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._stats["failed_count"] += 1
                self._record_turn_mutation(
                    request.section,
                    "failed",
                    duration_ms=duration_ms,
                )
                logger.error(
                    "Mutation exception: section=%s, op=%s, error=%s, trace=%s",
                    request.section,
                    request.operation,
                    str(e),
                    request.cognitive_trace_id,
                    exc_info=True,
                )
                return MutationResponse.failed(
                    request_id=request.request_id,
                    section=request.section,
                    operation=request.operation,
                    error=str(e),
                    duration_ms=duration_ms,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._stats["total_duration_ms"] += duration_ms

            # 5. Handle result
            if result.success:
                bytes_delta = getattr(result, "bytes_delta", 0)
                self._stats["applied_count"] += 1
                self._stats["total_bytes_delta"] += bytes_delta
                self._record_turn_mutation(
                    request.section,
                    "approved",
                    bytes_delta=bytes_delta,
                    duration_ms=duration_ms,
                )
                logger.debug(
                    "Mutation applied: section=%s, op=%s, bytes=%d, trace=%s",
                    request.section,
                    request.operation,
                    bytes_delta,
                    request.cognitive_trace_id,
                )
                return MutationResponse.approved(
                    request_id=request.request_id,
                    section=request.section,
                    operation=request.operation,
                    new_size_bytes=getattr(result, "new_size_bytes", 0),
                    bytes_delta=bytes_delta,
                    available_bytes=getattr(result, "available_bytes", 0),
                    duration_ms=duration_ms,
                )
            else:
                self._stats["rejected_count"] += 1
                reason = getattr(result, "reason", None) or getattr(
                    result, "error", "Unknown error"
                )
                self._record_turn_mutation(
                    request.section,
                    "rejected",
                    reason=str(reason),
                    duration_ms=duration_ms,
                )
                logger.info(
                    "Mutation not successful: section=%s, op=%s, reason=%s",
                    request.section,
                    request.operation,
                    reason,
                )
                return MutationResponse.rejected(
                    request_id=request.request_id,
                    section=request.section,
                    operation=request.operation,
                    reason=str(reason),
                    category=RejectionCategory.CAPACITY,
                    available_bytes=getattr(result, "available_bytes", 0),
                    duration_ms=duration_ms,
                )

    def batch_mutations(
        self,
        batch: BatchRequest,
    ) -> BatchResult:
        """
        Process multiple mutations in batch.

        Args:
            batch: Batch of mutation requests

        Returns:
            BatchResult: Aggregated results with per-request responses

        Behavior:
            - Mutations applied in order (by list position)
            - If stop_on_rejection=True: stop at first rejection
            - If stop_on_rejection=False: continue with remaining
        """
        start_time = time.perf_counter()
        responses: List[MutationResponse] = []
        applied_count = 0
        rejected_count = 0
        failed_count = 0
        cancelled_count = 0
        total_bytes_delta = 0
        stopped_early = False

        # Validate batch writer
        auth = self.validate_writer(batch.writer_id)
        if not auth.authorized:
            # Reject all requests in batch
            duration_ms = (time.perf_counter() - start_time) * 1000
            for request in batch.requests:
                responses.append(
                    MutationResponse.rejected(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        reason=auth.reason,
                        category=RejectionCategory.AUTHORIZATION,
                    )
                )
                rejected_count += 1

            return BatchResult(
                batch_id=batch.batch_id,
                total_requests=len(batch.requests),
                applied_count=0,
                rejected_count=rejected_count,
                failed_count=0,
                cancelled_count=0,
                responses=responses,
                duration_ms=duration_ms,
            )

        # Process each request
        for i, request in enumerate(batch.requests):
            response = self.request_mutation(request)
            responses.append(response)

            if response.status == MutationStatus.APPLIED:
                applied_count += 1
                total_bytes_delta += response.bytes_delta
            elif response.status == MutationStatus.REJECTED:
                rejected_count += 1
                if batch.stop_on_rejection:
                    # Cancel remaining requests
                    stopped_early = True
                    for remaining in batch.requests[i + 1 :]:
                        responses.append(
                            MutationResponse.cancelled(
                                request_id=remaining.request_id,
                                reason="Batch stopped due to rejection",
                            )
                        )
                        cancelled_count += 1
                    break
            elif response.status == MutationStatus.FAILED:
                failed_count += 1
            elif response.status == MutationStatus.CANCELLED:
                cancelled_count += 1

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(
            "Batch completed: batch_id=%s, applied=%d, rejected=%d, failed=%d, duration=%.2fms",
            batch.batch_id,
            applied_count,
            rejected_count,
            failed_count,
            duration_ms,
        )

        return BatchResult(
            batch_id=batch.batch_id,
            total_requests=len(batch.requests),
            applied_count=applied_count,
            rejected_count=rejected_count,
            failed_count=failed_count,
            cancelled_count=cancelled_count,
            responses=responses,
            total_bytes_delta=total_bytes_delta,
            duration_ms=duration_ms,
            stopped_early=stopped_early,
        )

    def validate_writer(self, writer_id: str) -> WriterAuthorization:
        """
        Validate writer authorization.

        In standalone mode with no authorized_writers set, all writers are allowed.
        Otherwise, checks against the authorized_writers set.

        Args:
            writer_id: Writer to validate

        Returns:
            WriterAuthorization: Authorization result
        """
        # If no restrictions, authorize everyone
        if self._authorized_writers is None:
            return WriterAuthorization(
                writer_id=writer_id,
                authorized=True,
                permissions=["read", "write", "batch"],
            )

        # Check against allowed set
        if writer_id in self._authorized_writers:
            return WriterAuthorization(
                writer_id=writer_id,
                authorized=True,
                permissions=["read", "write", "batch"],
            )

        return WriterAuthorization(
            writer_id=writer_id,
            authorized=False,
            permissions=[],
            reason=f"Writer '{writer_id}' not in authorized list",
        )

    # =========================================================================
    # ADDITIONAL OPERATIONS
    # =========================================================================

    def cancel_request(self, request_id: str) -> bool:
        """
        Cancel a pending mutation request.

        DirectWriterAdapter processes synchronously, so cancellation
        is not applicable. Always returns False.

        Args:
            request_id: ID of request to cancel

        Returns:
            bool: Always False (no queueing)
        """
        return False

    def get_pending_count(self) -> int:
        """
        Get number of pending mutation requests.

        DirectWriterAdapter processes synchronously, so there are
        never pending requests.

        Returns:
            int: Always 0
        """
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get writer port statistics.

        Returns:
            dict: Statistics including counts and timing
        """
        with self._lock:
            total = self._stats["total_requests"]
            total_duration = self._stats["total_duration_ms"]
            return {
                "writer_id": self._writer_id,
                "total_requests": total,
                "applied_count": self._stats["applied_count"],
                "rejected_count": self._stats["rejected_count"],
                "failed_count": self._stats["failed_count"],
                "total_bytes_delta": self._stats["total_bytes_delta"],
                "avg_duration_ms": round(total_duration / total, 3) if total > 0 else 0.0,
                "pending_count": 0,
            }

    def reset_stats(self) -> None:
        """Reset all statistics counters."""
        with self._lock:
            self._stats = {
                "total_requests": 0,
                "applied_count": 0,
                "rejected_count": 0,
                "failed_count": 0,
                "total_duration_ms": 0.0,
                "total_bytes_delta": 0,
            }

    # =========================================================================
    # M4 E4.5.4: Per-turn mutation audit
    # =========================================================================

    @staticmethod
    def _empty_turn_stats() -> Dict[str, Any]:
        """Create a fresh per-turn stats dict."""
        return {
            "approved_count": 0,
            "rejected_count": 0,
            "failed_count": 0,
            "by_section": {},
            "by_rejection_reason": {},
            "total_bytes_delta": 0,
            "total_duration_ms": 0.0,
        }

    def _record_turn_mutation(
        self,
        section: str,
        status: str,
        reason: Optional[str] = None,
        bytes_delta: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """Record a single mutation decision in per-turn stats.

        Args:
            section: SS section name.
            status: "approved", "rejected", or "failed".
            reason: Rejection reason (only for rejected).
            bytes_delta: Bytes change (only for approved).
            duration_ms: Processing time.
        """
        ts = self._turn_stats
        if section not in ts["by_section"]:
            ts["by_section"][section] = {"approved": 0, "rejected": 0}
        if status == "approved":
            ts["approved_count"] += 1
            ts["by_section"][section]["approved"] += 1
            ts["total_bytes_delta"] += bytes_delta
        elif status == "rejected":
            ts["rejected_count"] += 1
            ts["by_section"][section]["rejected"] += 1
            if reason:
                ts["by_rejection_reason"][reason] = ts["by_rejection_reason"].get(reason, 0) + 1
        elif status == "failed":
            ts["failed_count"] += 1
        ts["total_duration_ms"] += duration_ms

    def snapshot_turn_stats(self) -> Dict[str, Any]:
        """Snapshot and reset per-turn mutation stats.

        Called at turn completion to get the mutation summary before
        resetting for the next turn.

        Returns:
            Dict with approved_count, rejected_count, failed_count,
            by_section, by_rejection_reason, total_bytes_delta,
            total_duration_ms.
        """
        with self._lock:
            snapshot = dict(self._turn_stats)
            snapshot["by_section"] = dict(self._turn_stats["by_section"])
            snapshot["by_rejection_reason"] = dict(self._turn_stats["by_rejection_reason"])
            self._turn_stats = self._empty_turn_stats()
            return snapshot

    @property
    def mutation_stats(self) -> Dict[str, Any]:
        """Current per-turn mutation stats (read-only snapshot).

        Does NOT reset. Use snapshot_turn_stats() at turn end.
        """
        with self._lock:
            return dict(self._turn_stats)

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _map_rejection_category(self, reason_code: Optional[Any]) -> RejectionCategory:
        """
        Map guard rejection reason code to RejectionCategory.

        Args:
            reason_code: Reason code from MutationGuard

        Returns:
            RejectionCategory: Mapped category
        """
        if reason_code is None:
            return RejectionCategory.INTERNAL

        # Convert to string for comparison
        code_str = str(reason_code).lower()

        if "capacity" in code_str or "size" in code_str or "budget" in code_str:
            return RejectionCategory.CAPACITY
        elif "locked" in code_str or "eviction" in code_str or "migration" in code_str:
            return RejectionCategory.LOCKED
        elif "emergency" in code_str:
            return RejectionCategory.EMERGENCY
        elif "section" in code_str or "operation" in code_str or "invalid" in code_str:
            return RejectionCategory.VALIDATION
        else:
            return RejectionCategory.INTERNAL

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"DirectWriterAdapter(writer_id='{self._writer_id}', "
            f"connected={self.is_connected}, "
            f"requests={self._stats['total_requests']})"
        )
