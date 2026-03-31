"""
k1.concierge.ledger.recovery -- Crash recovery orchestrator.

M9 E9.5.1: Unified recovery from ledger events.

The CrashRecoveryOrchestrator reads all ledger events for a session
and rebuilds the FSM's protocol state by calling rebuild methods on
each sub-component. This enables zero-state-loss recovery after a
process crash.

Recovery order (dependency-safe):
    1. Project task states -> rebuild TaskBridge
    2. Project cancel state -> rebuild CancellationHandler
    3. Project suspension state -> rebuild SuspensionManager
    4. Project HITL state -> rebuild HILCoordinator
    5. Project pending results -> rebuild FSMTurnState
    6. Project history -> rebuild _history
    7. Derive _active_task_ids from projected task states
    8. Derive FSM state from event patterns

Reference: v3_milestones.md E9.5.1 (CrashRecoveryOrchestrator)
Reference: v3_milestones.md E9.5.3 (FSM state derivation)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from k1.concierge.ledger.projections import (
    project_cancel_state,
    project_history,
    project_pending_results,
    project_task_states,
)
from k1.concierge.protocols.hitl_persistence import TaskStatus

if TYPE_CHECKING:
    from k1.concierge.ledger.store import ILedgerStore, LedgerEntry

logger = logging.getLogger(__name__)


@dataclass
class CrashRecoveryReport:
    """Summary of a crash recovery attempt.

    M9 E9.5.1: Returned by CrashRecoveryOrchestrator.recover().

    Attributes:
        recovered:           Whether recovery was attempted and succeeded.
        event_count:         Total ledger events replayed.
        tasks_restored:      Number of task states restored to TaskBridge.
        cancelled_restored:  Number of cancelled tasks restored.
        suspensions_restored: Number of active suspensions restored.
        hitl_pending_restored: Number of pending HITL requests restored.
        pending_results_restored: Number of pending results restored.
        history_entries:     Number of history entries rebuilt.
        active_task_count:   Number of active (non-terminal) tasks.
        derived_state:       The FSM state derived from event patterns.
        error:               Error message if recovery failed.
    """

    recovered: bool = False
    event_count: int = 0
    tasks_restored: int = 0
    cancelled_restored: int = 0
    suspensions_restored: int = 0
    hitl_pending_restored: int = 0
    pending_results_restored: int = 0
    history_entries: int = 0
    active_task_count: int = 0
    derived_state: str = "LISTENING"
    error: str = ""
    _details: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """One-line summary of recovery results."""
        if not self.recovered:
            reason = self.error or "no events"
            return f"Recovery skipped: {reason}"
        return (
            f"Recovered {self.event_count} events: "
            f"{self.tasks_restored} tasks, "
            f"{self.active_task_count} active, "
            f"{self.suspensions_restored} suspended, "
            f"{self.hitl_pending_restored} HITL pending, "
            f"{self.pending_results_restored} pending results, "
            f"{self.history_entries} history entries -> "
            f"state={self.derived_state}"
        )


class CrashRecoveryOrchestrator:
    """Rebuilds FSM protocol state from ledger events.

    M9 E9.5.1: Orchestrates recovery across all sub-components.

    Usage:
        orchestrator = CrashRecoveryOrchestrator()
        report = orchestrator.recover(fsm, ledger_store, session_id)
    """

    def recover(
        self,
        fsm: Any,
        ledger_store: ILedgerStore,
        session_id: str,
    ) -> CrashRecoveryReport:
        """Execute crash recovery from ledger events.

        Reads all events for the session and rebuilds FSM sub-component
        state. This is a synchronous operation -- all projections and
        rebuilds are pure functions on in-memory data.

        M9 E9.5.5: If the ledger store is unavailable or raises,
        returns a safe fallback report (recovered=False) without
        affecting current FSM state.

        Args:
            fsm: The ConciergeController instance to recover into.
            ledger_store: ILedgerStore to read events from.
            session_id: Session to recover.

        Returns:
            CrashRecoveryReport summarizing the recovery.
        """
        report = CrashRecoveryReport()

        # E9.5.5: Fallback safety -- never make things worse
        try:
            entries = ledger_store.read(session_id)
        except Exception as exc:
            report.error = f"Ledger read failed: {exc}"
            logger.error("Crash recovery failed: %s", exc)
            return report

        if not entries:
            report.error = "No events found"
            return report

        report.event_count = len(entries)

        try:
            self._do_recover(fsm, entries, report)
            report.recovered = True
        except Exception as exc:
            report.error = f"Recovery failed: {exc}"
            logger.error("Crash recovery error: %s", exc, exc_info=True)

        return report

    def _do_recover(
        self,
        fsm: Any,
        entries: list[LedgerEntry],
        report: CrashRecoveryReport,
    ) -> None:
        """Internal recovery logic. Separated for exception isolation."""

        # 1. Project task states -> rebuild TaskBridge
        task_states = project_task_states(entries)
        report.tasks_restored = fsm._task_bridge.rebuild_from_projection(task_states)

        # 2. Project cancel state -> rebuild CancellationHandler
        _active, cancelled = project_cancel_state(entries)
        report.cancelled_restored = fsm._cancel_handler.rebuild_from_events(entries)

        # 3. Project suspension state -> rebuild SuspensionManager
        report.suspensions_restored = fsm._suspension_manager.rebuild_from_events(entries)

        # 4. Project HITL state -> rebuild HILCoordinator (if wired)
        if fsm._hil_coordinator is not None:
            report.hitl_pending_restored = fsm._hil_coordinator.rebuild_from_events(entries)

        # 5. Project pending results -> rebuild FSMTurnState
        pending = project_pending_results(entries)
        report.pending_results_restored = fsm._turn_state.rebuild_from_projection(pending)

        # 6. Project history -> store in report (controller can apply)
        history = project_history(entries)
        report.history_entries = len(history)
        report._details["history"] = history

        # 7. Derive _active_task_ids from projected task states
        active_ids: set[str] = set()
        for task_id, entry in task_states.items():
            if entry.status in (
                TaskStatus.DISPATCHED,
                TaskStatus.IN_PROGRESS,
                TaskStatus.SUSPENDED,
            ):
                active_ids.add(task_id)
        report.active_task_count = len(active_ids)
        report._details["active_task_ids"] = active_ids

        # 8. Derive FSM state from event patterns (E9.5.3)
        report.derived_state = self._derive_fsm_state(entries, task_states, pending)

        logger.info("Crash recovery complete: %s", report.summary())

    def _derive_fsm_state(
        self,
        entries: list[LedgerEntry],
        task_states: dict[str, Any],
        pending: Any,
    ) -> str:
        """Derive ConciergeState from the latest event patterns.

        M9 E9.5.3: State derivation rules (priority order):
            1. task.suspended without task.resumed -> CLARIFYING_WORKER
            2. Pending results non-empty -> WEAVING
            3. Active tasks exist -> COMPANIONING
            4. user_input without response.final -> DISPATCHING
            5. Otherwise -> LISTENING

        Returns:
            String name of the derived ConciergeState.
        """
        # Check for active suspensions
        has_active_suspension = any(
            entry.status == TaskStatus.SUSPENDED
            for entry in task_states.values()
            if hasattr(entry, "status")
        )
        if has_active_suspension:
            return "CLARIFYING_WORKER"

        # Check for pending results
        if pending and len(pending) > 0:
            return "WEAVING"

        # Check for active tasks
        has_active = any(
            entry.status in (TaskStatus.DISPATCHED, TaskStatus.IN_PROGRESS)
            for entry in task_states.values()
            if hasattr(entry, "status")
        )
        if has_active:
            return "COMPANIONING"

        # Check if last event was user input without response
        last_user_input = False
        last_response_final = False
        for entry in entries:
            if entry.event_type == "conversation.user_input.received":
                last_user_input = True
                last_response_final = False
            elif entry.event_type == "conversation.weave.emitted":
                last_response_final = True
                last_user_input = False

        if last_user_input and not last_response_final:
            return "DISPATCHING"

        return "LISTENING"
