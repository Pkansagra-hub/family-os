"""
poc.k1_poc.protocols.hitl_persistence -- HITL persistence model and timeout event.

V2 Design Ref: Section 5 (TaskStateEntry schema -- pending_hil, hil_suspensions_count)
V2 Design Ref: Section 9.5 (Suspension Rules, Pending HIL Persistence)
V2 Design Ref: Section 9.6 (Crash Recovery Protocol)
V2 Design Ref: Section 9.10 (Invariants 3, 4, 6)

Epic 13.6: HITL Limits, Timeouts, and Crash Recovery.
M6 E6.1.1: HILSubTask -- formal blocking sub-task model.

This module provides:

    HILSubTaskStatus:    Status enum for HITL sub-task lifecycle.
    HILSubTask:          The formal blocking sub-task model wrapping
                         HILRequest + react_snapshot + resume_token.
    TaskStateEntry:      The persistence model for task state including
                         HITL-specific fields (pending_hil, hil_suspensions_count).
    HILTimeoutEvent:     Bus event emitted when HITL timeout fires.
    CrashRecoveryReport: Summary of crash recovery scan results.

Persistence contract (V2 Section 5):
    TaskStateEntry.pending_hil stores the serialized HILSubTask for
    crash recovery.  When status=SUSPENDED and pending_hil is not None,
    the FSM can reconstruct the HITL state on restart.

Timeout contract (V2 Section 9.5):
    When the timeout timer fires, the FSM emits HILTimeoutEvent on the
    bus and transitions to auto-cancel.  The timeout timer is cancelled
    if the user responds before it fires.

INVARIANTS:
    3. Every HITL cycle closes (timeout guarantees closure).
    4. pending_hil survives process restarts (in Session State).
    6. Max 2 suspensions per task (hil_suspensions_count).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from poc.k1_poc.protocols.hitl import HILRequest

logger = logging.getLogger(__name__)


# =========================================================================
# M6 E6.1.1: HILSubTask -- formal blocking sub-task model
# =========================================================================


class HILSubTaskStatus(str, Enum):
    """Lifecycle status for a HITL blocking sub-task.

    M6 E6.1.1: Replaces scattered in-memory state with formal lifecycle.

    PENDING:    Awaiting user response. Side-effects blocked at L2.
    RESOLVED:   User answered. Resume dispatch imminent.
    TIMED_OUT:  Timeout fired before user answered. Auto-cancel.
    CANCELLED:  Explicitly cancelled (user cancel, limit exceeded, etc.).
    """

    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


@dataclass
class HILSubTask:
    """Formal blocking sub-task model for HITL lifecycle.

    M6 E6.1.1: Single source of truth wrapping HILRequest + suspension
    context + ReAct snapshot into one persist-ready record.

    Replaces the dual-store pattern where SuspensionManager._contexts
    and FSMTurnState.pending_context stored overlapping state.

    Attributes:
        pending_hil_id:    Unique identifier for this HITL sub-task (UUID).
        hil_type:          One of: clarification, approval, selection.
        parent_task_id:    The task_id that triggered this HITL.
        question:          The question asked of the user.
        options:           Structured options (approval/selection).
        side_effects:      Side effects to present (approval).
        safety_band:       Effective safety band after escalation.
        hil_deadline:      Absolute deadline (created_at_ns + timeout_ms * 1e6).
        timeout_ms:        Configured timeout in milliseconds.
        resume_token:      UUID4 token for validating resume events.
        react_snapshot:    Captured ReAct state at suspension point:
                           - prior_messages: list of message dicts
                           - tool_history: list of tool call entries
                           - last_iteration: iteration count at suspension
        status:            Current lifecycle status (PENDING -> RESOLVED/TIMED_OUT/CANCELLED).
        created_at_ns:     Monotonic timestamp when sub-task was created.
        resolved_at_ns:    Monotonic timestamp when sub-task was resolved (0 if not resolved).
        device_id:         Device that originated the task (M5 tracking).
        context:           Additional context from HILRequest.
    """

    pending_hil_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    hil_type: str = "clarification"
    parent_task_id: str = ""
    question: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    safety_band: str = "GREEN"
    hil_deadline: int = 0
    timeout_ms: int = 60_000
    resume_token: str = field(default_factory=lambda: str(uuid.uuid4()))
    react_snapshot: dict[str, Any] = field(
        default_factory=lambda: {
            "prior_messages": [],
            "tool_history": [],
            "last_iteration": 0,
        }
    )
    status: HILSubTaskStatus = HILSubTaskStatus.PENDING
    created_at_ns: int = field(default_factory=time.monotonic_ns)
    resolved_at_ns: int = 0
    device_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute deadline if not already set."""
        if self.hil_deadline == 0 and self.timeout_ms > 0:
            self.hil_deadline = self.created_at_ns + (self.timeout_ms * 1_000_000)

    @classmethod
    def from_hil_request(
        cls,
        request: HILRequest,
        react_snapshot: dict[str, Any] | None = None,
        device_id: str = "",
    ) -> HILSubTask:
        """Create HILSubTask from an HILRequest and captured ReAct state.

        M6 E6.1.2: Factory method used in _on_task_suspended.

        Args:
            request:        The HILRequest from Back's submit_result.
            react_snapshot: Captured ReAct state (prior_messages, tool_history, last_iteration).
            device_id:      Device that originated the task (M5).

        Returns:
            New HILSubTask in PENDING status with resume_token generated.
        """
        snapshot = react_snapshot or {
            "prior_messages": [],
            "tool_history": [],
            "last_iteration": 0,
        }
        return cls(
            hil_type=request.hil_type,
            parent_task_id=request.task_id,
            question=request.question,
            options=list(request.options),
            side_effects=list(request.side_effects),
            safety_band=(
                request.safety_band.value
                if hasattr(request.safety_band, "value")
                else str(request.safety_band)
            ),
            timeout_ms=request.timeout_ms,
            react_snapshot=snapshot,
            device_id=device_id,
            context=dict(request.context),
        )

    def resolve(self, decision_branch: str = "clarified") -> None:
        """Transition to RESOLVED status.

        M6 E6.3.2: Called when user provides answer.

        Args:
            decision_branch: One of: clarified, approved, approved_with_mods,
                           cancelled, selected.
        """
        if self.status != HILSubTaskStatus.PENDING:
            logger.warning(
                "HILSubTask.resolve: ignoring resolve for %s in status %s",
                self.pending_hil_id,
                self.status.value,
            )
            return
        self.status = HILSubTaskStatus.RESOLVED
        self.resolved_at_ns = time.monotonic_ns()
        logger.info(
            "HILSubTask resolved: id=%s type=%s branch=%s",
            self.pending_hil_id[:8],
            self.hil_type,
            decision_branch,
        )

    def time_out(self) -> None:
        """Transition to TIMED_OUT status.

        M6 E6.3.3: Called when timeout fires.
        """
        if self.status != HILSubTaskStatus.PENDING:
            logger.warning(
                "HILSubTask.time_out: ignoring timeout for %s in status %s",
                self.pending_hil_id,
                self.status.value,
            )
            return
        self.status = HILSubTaskStatus.TIMED_OUT
        self.resolved_at_ns = time.monotonic_ns()
        logger.info(
            "HILSubTask timed out: id=%s type=%s",
            self.pending_hil_id[:8],
            self.hil_type,
        )

    def cancel(self, reason: str = "user_cancel") -> None:
        """Transition to CANCELLED status.

        M6 E6.1.5 / E6.3.4: Called on explicit cancel or limit exceeded.

        Args:
            reason: Cancellation reason for audit trail.
        """
        if self.status not in (HILSubTaskStatus.PENDING, HILSubTaskStatus.TIMED_OUT):
            logger.warning(
                "HILSubTask.cancel: ignoring cancel for %s in status %s",
                self.pending_hil_id,
                self.status.value,
            )
            return
        self.status = HILSubTaskStatus.CANCELLED
        self.resolved_at_ns = time.monotonic_ns()
        logger.info(
            "HILSubTask cancelled: id=%s type=%s reason=%s",
            self.pending_hil_id[:8],
            self.hil_type,
            reason,
        )

    @property
    def is_pending(self) -> bool:
        """Whether this sub-task is still awaiting user response."""
        return self.status == HILSubTaskStatus.PENDING

    @property
    def is_terminal(self) -> bool:
        """Whether this sub-task is in a terminal state."""
        return self.status in (
            HILSubTaskStatus.RESOLVED,
            HILSubTaskStatus.TIMED_OUT,
            HILSubTaskStatus.CANCELLED,
        )

    @property
    def elapsed_ms(self) -> int:
        """Milliseconds since creation."""
        return int((time.monotonic_ns() - self.created_at_ns) / 1_000_000)

    @property
    def remaining_timeout_ms(self) -> int:
        """Milliseconds remaining before timeout (0 if expired)."""
        remaining_ns = self.hil_deadline - time.monotonic_ns()
        return max(0, int(remaining_ns / 1_000_000))

    def to_persistence(self) -> dict[str, Any]:
        """Serialize for TaskStateEntry.pending_hil crash recovery.

        M6 E6.4.1: Includes react_snapshot for zero-waste resume after crash.
        Includes suspended_at_ms for timeout checking on recovery.
        """
        return {
            "pending_hil_id": self.pending_hil_id,
            "hil_type": self.hil_type,
            "parent_task_id": self.parent_task_id,
            "question": self.question,
            "options": self.options,
            "side_effects": self.side_effects,
            "safety_band": self.safety_band,
            "hil_deadline": self.hil_deadline,
            "timeout_ms": self.timeout_ms,
            "resume_token": self.resume_token,
            "react_snapshot": self.react_snapshot,
            "status": self.status.value,
            "created_at_ns": self.created_at_ns,
            "resolved_at_ns": self.resolved_at_ns,
            "device_id": self.device_id,
            "context": self.context,
            "suspended_at_ms": int(self.created_at_ns / 1_000_000),
        }

    @classmethod
    def from_persistence(cls, data: dict[str, Any]) -> HILSubTask:
        """Deserialize from TaskStateEntry.pending_hil.

        M6 E6.4.2: Used by scan_for_recovery to reconstruct HILSubTask
        from persisted task_state on FSM startup.
        """
        status_str = data.get("status", "PENDING")
        try:
            status = HILSubTaskStatus(status_str)
        except ValueError:
            status = HILSubTaskStatus.PENDING

        snapshot = data.get(
            "react_snapshot",
            {
                "prior_messages": [],
                "tool_history": [],
                "last_iteration": 0,
            },
        )

        return cls(
            pending_hil_id=data.get("pending_hil_id", str(uuid.uuid4())),
            hil_type=data.get("hil_type", "clarification"),
            parent_task_id=data.get("parent_task_id", ""),
            question=data.get("question", ""),
            options=data.get("options", []),
            side_effects=data.get("side_effects", []),
            safety_band=data.get("safety_band", "GREEN"),
            hil_deadline=data.get("hil_deadline", 0),
            timeout_ms=data.get("timeout_ms", 60_000),
            resume_token=data.get("resume_token", str(uuid.uuid4())),
            react_snapshot=snapshot,
            status=status,
            created_at_ns=data.get("created_at_ns", time.monotonic_ns()),
            resolved_at_ns=data.get("resolved_at_ns", 0),
            device_id=data.get("device_id", ""),
            context=data.get("context", {}),
        )

    def to_hil_request(self) -> HILRequest:
        """Convert back to HILRequest (for recovery re-presentation).

        M6 E6.4.3: Used by _recover_hitl_on_startup to re-present
        recoverable suspensions via Front HITL_RELAY.
        """
        from poc.k1_poc.protocols.hitl import SafetyBand

        try:
            band = SafetyBand(self.safety_band)
        except ValueError:
            band = SafetyBand.GREEN

        return HILRequest(
            task_id=self.parent_task_id,
            hil_type=self.hil_type,
            question=self.question,
            options=list(self.options),
            context=dict(self.context),
            side_effects=list(self.side_effects),
            safety_band=band,
            timeout_ms=self.timeout_ms,
        )


class TaskStatus(str, Enum):
    """Task lifecycle status values.

    V2 Design Ref: Section 5 (TaskStateEntry.status)

    Values:
        DISPATCHED:   Task dispatched to Back, not yet started.
        IN_PROGRESS:  Back is actively executing.
        SUSPENDED:    Waiting for user input (HITL).
        COMPLETED:    Task finished successfully.
        FAILED:       Task failed (error, timeout, etc.).
        CANCELLED:    Task cancelled (user cancel, HITL timeout, etc.).
    """

    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskStateEntry:
    """Persistence model for task state with HITL support.

    V2 Design Ref: Section 5 (TaskStateEntry schema)
    V2 Design Ref: Section 9.5 (pending_hil persistence)
    V2 Design Ref: Section 9.6 (Crash recovery via pending_hil)

    This is the per-task record in the FSM's task_state dictionary.
    It persists to Session State for crash recovery.

    Key HITL fields:
        pending_hil:           Serialized HILRequest (from to_persistence()).
                              Non-None when status=SUSPENDED.
        hil_suspensions_count: Number of HITL rounds this task has used.
                              Max is MAX_SUSPENSIONS_PER_TASK (2).

    Attributes:
        task_id:               Unique task identifier.
        action:                The action being performed.
        status:                Current lifecycle status.
        dispatched_at_ms:      When the task was dispatched.
        completed_at_ms:       When the task completed/failed/cancelled.
        depends_on:            Task dependency (for ordered execution).
        progress_pct:          Estimated progress (0-100).
        pending_hil:           Serialized HILRequest for crash recovery.
        hil_suspensions_count: Total HITL rounds used.
        findings_so_far:       Accumulated results for resume context.
        hil_history:           History of HITL interactions for L2 checks.
        cancel_reason:         Why the task was cancelled (if applicable).
    """

    task_id: str
    action: str = ""
    status: TaskStatus = TaskStatus.DISPATCHED
    dispatched_at_ms: int = 0
    completed_at_ms: int | None = None
    depends_on: str | None = None
    progress_pct: int = 0
    pending_hil: dict[str, Any] | None = None
    hil_suspensions_count: int = 0
    findings_so_far: list[dict[str, Any]] = field(default_factory=list)
    hil_history: list[dict[str, Any]] = field(default_factory=list)
    cancel_reason: str | None = None

    def suspend(self, hil_request: HILRequest, ledger: Any = None) -> None:
        """Mark task as SUSPENDED with pending HITL.

        V2 Design Ref: Section 9.5 (pending_hil persistence)
        V3 M1 E1.2.3: Optional ledger param for event sourcing.

        Args:
            hil_request: The HILRequest to persist for crash recovery.
            ledger: Optional LedgerWriter for event sourcing.
        """
        self.status = TaskStatus.SUSPENDED
        self.pending_hil = hil_request.to_persistence()
        self.hil_suspensions_count += 1
        logger.info(
            "Task %s: suspended [round=%d, type=%s]",
            self.task_id,
            self.hil_suspensions_count,
            hil_request.hil_type,
        )

    def resume(self, ledger: Any = None) -> dict[str, Any] | None:
        """Clear HITL suspension state and return pending_hil for resolution.

        V2 Design Ref: Section 9.5 (pending_hil cleared on resume)
        V3 M1 E1.2.3: Optional ledger param for event sourcing.

        Returns:
            The pending_hil dict (for Back resume context), or None.
        """
        pending = self.pending_hil
        self.pending_hil = None
        self.status = TaskStatus.IN_PROGRESS
        logger.info("Task %s: resumed", self.task_id)
        return pending

    def cancel(self, reason: str = "user_cancel", ledger: Any = None) -> None:
        """Mark task as CANCELLED.

        V2 Design Ref: Section 9.5 (Timeout auto-cancel)
        V3 M1 E1.2.3: Optional ledger param for event sourcing.

        Args:
            reason: Why the task was cancelled.
            ledger: Optional LedgerWriter for event sourcing.
        """
        self.status = TaskStatus.CANCELLED
        self.pending_hil = None
        self.cancel_reason = reason
        self.completed_at_ms = _now_ms()
        logger.info("Task %s: cancelled [reason=%s]", self.task_id, reason)

    def complete(self, ledger: Any = None) -> None:
        """Mark task as COMPLETED.

        V3 M1 E1.2.3: Optional ledger param for event sourcing.
        """
        self.status = TaskStatus.COMPLETED
        self.pending_hil = None
        self.completed_at_ms = _now_ms()

    def fail(self, reason: str = "error", ledger: Any = None) -> None:
        """Mark task as FAILED.

        V3 M1 E1.2.3: Optional ledger param for event sourcing.
        """
        self.status = TaskStatus.FAILED
        self.pending_hil = None
        self.cancel_reason = reason
        self.completed_at_ms = _now_ms()

    def record_hil_interaction(
        self,
        hil_type: str,
        resolution: dict[str, Any],
    ) -> None:
        """Record a completed HITL interaction in history.

        V2 Design Ref: Section 9.8 (L2 defense checks hil_history)

        Args:
            hil_type:   The type of HITL interaction.
            resolution: The user's resolution payload.
        """
        self.hil_history.append(
            {
                "hil_type": hil_type,
                "resolution": resolution,
                "resolved_at_ms": _now_ms(),
            }
        )

    @property
    def is_suspended(self) -> bool:
        """Whether the task is currently suspended for HITL."""
        return self.status == TaskStatus.SUSPENDED

    @property
    def has_pending_hil(self) -> bool:
        """Whether the task has a pending HITL request."""
        return self.pending_hil is not None

    @property
    def is_terminal(self) -> bool:
        """Whether the task is in a terminal state."""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for Session State persistence.

        V2 Design Ref: Section 9.6 (Crash recovery reads from this)
        """
        return {
            "task_id": self.task_id,
            "action": self.action,
            "status": self.status.value,
            "dispatched_at_ms": self.dispatched_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "depends_on": self.depends_on,
            "progress_pct": self.progress_pct,
            "pending_hil": self.pending_hil,
            "hil_suspensions_count": self.hil_suspensions_count,
            "findings_so_far": self.findings_so_far,
            "hil_history": self.hil_history,
            "cancel_reason": self.cancel_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskStateEntry:
        """Deserialize from Session State dict.

        V2 Design Ref: Section 9.6 (Crash recovery reconstruction)
        """
        status_str = data.get("status", "DISPATCHED")
        try:
            status = TaskStatus(status_str)
        except ValueError:
            status = TaskStatus.DISPATCHED
        return cls(
            task_id=data["task_id"],
            action=data.get("action", ""),
            status=status,
            dispatched_at_ms=data.get("dispatched_at_ms", 0),
            completed_at_ms=data.get("completed_at_ms"),
            depends_on=data.get("depends_on"),
            progress_pct=data.get("progress_pct", 0),
            pending_hil=data.get("pending_hil"),
            hil_suspensions_count=data.get("hil_suspensions_count", 0),
            findings_so_far=data.get("findings_so_far", []),
            hil_history=data.get("hil_history", []),
            cancel_reason=data.get("cancel_reason"),
        )


# =========================================================================
# HILTimeoutEvent -- Bus event for HITL timeout auto-cancel
# =========================================================================


@dataclass
class HILTimeoutEvent:
    """Bus event emitted when HITL timeout fires, triggering auto-cancel.

    V2 Design Ref: Section 9.5 (Timeout Policy)
    V2 Design Ref: Section 9.10, Invariant 3

    When the timeout timer fires for a SUSPENDED task:
        1. FSM emits HILTimeoutEvent on the bus.
        2. FSM transitions task to CANCELLED with reason="hil_timeout".
        3. Front is notified via task.failed event.

    Attributes:
        task_id:          The task that timed out.
        hil_type:         The type of HITL that timed out.
        timeout_ms:       The configured timeout that expired.
        elapsed_ms:       Actual time elapsed before timeout fired.
        question:         The question that was unanswered.
        error_code:       Standard error code for timeout.
        reason:           Human-readable reason string.
    """

    task_id: str
    hil_type: str = "clarification"
    timeout_ms: int = 60_000
    elapsed_ms: int = 0
    question: str = ""
    error_code: str = "HITL_TIMEOUT"
    reason: str = "hil_timeout"

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload."""
        return {
            "task_id": self.task_id,
            "hil_type": self.hil_type,
            "timeout_ms": self.timeout_ms,
            "elapsed_ms": self.elapsed_ms,
            "question": self.question,
            "error_code": self.error_code,
            "reason": self.reason,
            "last_error_detail": (
                f"User did not respond within " f"{self.timeout_ms / 1000:.0f}s."
            ),
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HILTimeoutEvent:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            hil_type=data.get("hil_type", "clarification"),
            timeout_ms=data.get("timeout_ms", 60_000),
            elapsed_ms=data.get("elapsed_ms", 0),
            question=data.get("question", ""),
            error_code=data.get("error_code", "HITL_TIMEOUT"),
            reason=data.get("reason", "hil_timeout"),
        )

    @classmethod
    def from_task_state(
        cls,
        entry: TaskStateEntry,
        now_ms: int | None = None,
    ) -> HILTimeoutEvent:
        """Build timeout event from a TaskStateEntry with expired pending_hil.

        V2 Design Ref: Section 9.6 (Crash recovery timeout handling)

        Args:
            entry:  The TaskStateEntry with expired pending_hil.
            now_ms: Current time in ms (for elapsed calculation).

        Returns:
            HILTimeoutEvent for bus emission.
        """
        if now_ms is None:
            now_ms = _now_ms()

        pending = entry.pending_hil or {}
        suspended_at = pending.get("suspended_at_ms", 0)
        timeout = pending.get("timeout_ms", 60_000)
        elapsed = now_ms - suspended_at if suspended_at > 0 else timeout

        return cls(
            task_id=entry.task_id,
            hil_type=pending.get("hil_type", "clarification"),
            timeout_ms=timeout,
            elapsed_ms=elapsed,
            question=pending.get("question", ""),
        )


# =========================================================================
# CrashRecoveryReport -- Summary of recovery scan
# =========================================================================


@dataclass
class CrashRecoveryReport:
    """Summary of crash recovery scan results.

    V2 Design Ref: Section 9.6 (Recovery Sequence)

    Produced by the crash recovery scan on FSM startup.
    Reports which tasks were recovered, timed out, or skipped.

    Attributes:
        recovered_task_ids:  Tasks re-presented to user (within timeout).
        timed_out_task_ids:  Tasks auto-cancelled (past timeout).
        skipped_task_ids:    Non-SUSPENDED or no pending_hil.
        total_scanned:       Total entries scanned.
    """

    recovered_task_ids: list[str] = field(default_factory=list)
    timed_out_task_ids: list[str] = field(default_factory=list)
    skipped_task_ids: list[str] = field(default_factory=list)
    total_scanned: int = 0

    @property
    def recovered_count(self) -> int:
        return len(self.recovered_task_ids)

    @property
    def timed_out_count(self) -> int:
        return len(self.timed_out_task_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_task_ids)


def scan_for_recovery(
    task_state: dict[str, dict[str, Any]],
    now_ms: int | None = None,
) -> CrashRecoveryReport:
    """Scan task_state for SUSPENDED tasks needing recovery.

    V2 Design Ref: Section 9.6 (Recovery Sequence steps 1-7)

    Called on FSM startup.  For each task:
        1. Read pending_hil.suspended_at_ms
        2. Calculate elapsed = now_ms - suspended_at_ms
        3. If elapsed > timeout: mark as timed_out
        4. If elapsed <= timeout: mark as recovered (re-present)

    Args:
        task_state: Persisted task_state dict from Session State.
        now_ms:     Current time in ms (for testing).

    Returns:
        CrashRecoveryReport with categorized task_ids.
    """
    if now_ms is None:
        now_ms = _now_ms()

    report = CrashRecoveryReport(total_scanned=len(task_state))

    for task_id, entry_dict in task_state.items():
        status = entry_dict.get("status", "")
        pending = entry_dict.get("pending_hil")

        if status.upper() != "SUSPENDED" or pending is None:
            report.skipped_task_ids.append(task_id)
            continue

        suspended_at = pending.get("suspended_at_ms", 0)
        timeout_ms = pending.get("timeout_ms", 60_000)
        elapsed = now_ms - suspended_at

        if elapsed >= timeout_ms:
            report.timed_out_task_ids.append(task_id)
            logger.warning(
                "Recovery: task %s timed out (elapsed=%dms, timeout=%dms)",
                task_id,
                elapsed,
                timeout_ms,
            )
        else:
            report.recovered_task_ids.append(task_id)
            logger.info(
                "Recovery: task %s recoverable (remaining=%dms)",
                task_id,
                timeout_ms - elapsed,
            )

    return report


def build_timeout_events(
    report: CrashRecoveryReport,
    task_state: dict[str, dict[str, Any]],
    now_ms: int | None = None,
) -> list[HILTimeoutEvent]:
    """Build HILTimeoutEvent for each timed-out task in the report.

    V2 Design Ref: Section 9.6 (Crash recovery auto-cancel)

    Args:
        report:     The CrashRecoveryReport from scan_for_recovery.
        task_state: The task_state dict.
        now_ms:     Current time in ms.

    Returns:
        List of HILTimeoutEvents to emit on the bus.
    """
    if now_ms is None:
        now_ms = _now_ms()

    events: list[HILTimeoutEvent] = []
    for task_id in report.timed_out_task_ids:
        entry_dict = task_state.get(task_id, {})
        entry = TaskStateEntry.from_dict({"task_id": task_id, **entry_dict})
        events.append(HILTimeoutEvent.from_task_state(entry, now_ms=now_ms))
    return events


# =========================================================================
# Internal helpers
# =========================================================================


def _now_ms() -> int:
    """Current time in milliseconds (monotonic)."""
    return int(time.monotonic_ns() / 1_000_000)
