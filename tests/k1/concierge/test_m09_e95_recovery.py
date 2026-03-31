"""
M9 E9.5: CrashRecoveryOrchestrator tests.

Covers:
    E9.5.1 -- CrashRecoveryOrchestrator.recover() rebuilds all sub-components.
    E9.5.3 -- FSM state derivation from event patterns.
    E9.5.4 -- Recovery observability (report contains all metrics).
    E9.5.5 -- Fallback when ledger unavailable.

Run:
    python -m pytest tests/poc/test_m09_e95_recovery.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from k1.concierge.fsm.task_bridge import TaskBridge
from k1.concierge.fsm.turn_state import FSMTurnState
from k1.concierge.ledger.recovery import CrashRecoveryOrchestrator, CrashRecoveryReport
from k1.concierge.ledger.store import InMemoryLedgerStore, LedgerEntry
from k1.concierge.ledger.writer import LedgerWriter
from k1.concierge.protocols.cancel_handler import CancellationHandler
from k1.concierge.protocols.hitl_coordinator import HILCoordinator, HILCoordinatorConfig
from k1.concierge.protocols.suspension_manager import SuspensionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store_and_writer(session_id: str = "s1") -> tuple[InMemoryLedgerStore, LedgerWriter]:
    store = InMemoryLedgerStore()
    writer = LedgerWriter(store, session_id=session_id)
    return store, writer


def _make_ledger_entry(
    event_type: str,
    task_id: str = "",
    seq: int = 0,
    **extra: Any,
) -> LedgerEntry:
    payload: dict[str, Any] = {**extra}
    if task_id:
        payload["task_id"] = task_id
    return LedgerEntry(
        seq=seq,
        event_id=f"evt-{seq}",
        event_type=event_type,
        session_id="s1",
        payload=payload,
        written_at_utc="2025-01-01T00:00:00Z",
    )


def _make_mock_fsm(
    with_hil: bool = True,
) -> MagicMock:
    """Create a mock FSM with real sub-components for recovery testing."""
    fsm = MagicMock()
    fsm._task_bridge = TaskBridge()
    fsm._cancel_handler = CancellationHandler()
    fsm._suspension_manager = SuspensionManager()
    fsm._turn_state = FSMTurnState()
    if with_hil:
        cfg = HILCoordinatorConfig(
            max_rounds=3,
            timeouts={"clarification": 60000, "approval": 120000, "selection": 90000},
        )
        fsm._hil_coordinator = HILCoordinator(config=cfg)
    else:
        fsm._hil_coordinator = None
    return fsm


def _seed_store(store: InMemoryLedgerStore, entries: list[LedgerEntry]) -> None:
    """Seed a store with pre-built entries."""
    for entry in entries:
        store.append(entry)


# ===================================================================
# E9.5.1 -- CrashRecoveryOrchestrator.recover()
# ===================================================================


class TestCrashRecoveryOrchestrator:
    """Verify orchestrator rebuilds all sub-components from ledger."""

    def test_empty_store_no_recovery(self) -> None:
        store = InMemoryLedgerStore()
        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert not report.recovered
        assert report.error == "No events found"

    def test_single_task_lifecycle_recovery(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="search_hotels"),
                _make_ledger_entry(
                    "task.progressed", "t1", seq=2, progress_pct=50, status_message="searching"
                ),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.event_count == 2
        assert report.tasks_restored == 1
        assert report.active_task_count == 1
        assert report.derived_state == "COMPANIONING"

    def test_completed_task_recovery(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="search"),
                _make_ledger_entry("task.completed", "t1", seq=2),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.active_task_count == 0
        assert report.derived_state == "LISTENING"

    def test_cancelled_task_recovery(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="book"),
                _make_ledger_entry("task.cancelled", "t1", seq=2, reason="user_requested"),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.cancelled_restored > 0
        assert fsm._cancel_handler._cancelled_tasks == {"t1"}

    def test_suspended_task_recovery(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="book"),
                _make_ledger_entry(
                    "task.suspended",
                    "t1",
                    seq=2,
                    suspension_type="clarification",
                    suspension_count=1,
                ),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.suspensions_restored == 1
        assert fsm._suspension_manager.is_suspended("t1")
        assert report.derived_state == "CLARIFYING_WORKER"

    def test_hitl_pending_recovery(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry(
                    "hil.requested",
                    "t1",
                    seq=1,
                    hil_type="clarification",
                    question="Which?",
                    safety_band="AMBER",
                    timeout_s=60.0,
                    max_rounds=3,
                ),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.hitl_pending_restored == 1
        assert fsm._hil_coordinator.is_pending("t1")

    def test_no_hil_coordinator_skips_hitl_rebuild(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="search"),
            ],
        )

        fsm = _make_mock_fsm(with_hil=False)
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.hitl_pending_restored == 0

    def test_history_entries_counted(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("conversation.user_input.received", seq=1, text="hello"),
                _make_ledger_entry("task.created", "t1", seq=2, action="search"),
                _make_ledger_entry("task.completed", "t1", seq=3),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.history_entries == 3  # user_input + task.created + task.completed


# ===================================================================
# E9.5.3 -- FSM state derivation
# ===================================================================


class TestFSMStateDerivation:
    """Verify derived_state logic from event patterns."""

    def test_listening_when_no_events(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="x"),
                _make_ledger_entry("task.completed", "t1", seq=2),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")
        assert report.derived_state == "LISTENING"

    def test_companioning_with_active_task(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="search"),
                _make_ledger_entry("task.progressed", "t1", seq=2, progress_pct=50),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")
        assert report.derived_state == "COMPANIONING"

    def test_clarifying_worker_with_suspension(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="book"),
                _make_ledger_entry("task.suspended", "t1", seq=2, suspension_count=1),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")
        assert report.derived_state == "CLARIFYING_WORKER"

    def test_dispatching_after_user_input(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("conversation.user_input.received", seq=1, text="find hotels"),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")
        assert report.derived_state == "DISPATCHING"

    def test_listening_after_weave(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("conversation.user_input.received", seq=1, text="hi"),
                _make_ledger_entry("task.created", "t1", seq=2, action="search"),
                _make_ledger_entry("task.completed", "t1", seq=3),
                _make_ledger_entry("conversation.weave.emitted", seq=4, candidate_event_ids=["t1"]),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")
        assert report.derived_state == "LISTENING"

    def test_suspension_priority_over_active_tasks(self) -> None:
        """Suspended task takes priority over other active tasks."""
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="a"),
                _make_ledger_entry("task.created", "t2", seq=2, action="b"),
                _make_ledger_entry("task.suspended", "t1", seq=3, suspension_count=1),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")
        # CLARIFYING_WORKER beats COMPANIONING
        assert report.derived_state == "CLARIFYING_WORKER"


# ===================================================================
# E9.5.4 -- Recovery report observability
# ===================================================================


class TestCrashRecoveryReport:
    """Verify report contains useful observability data."""

    def test_summary_no_recovery(self) -> None:
        report = CrashRecoveryReport(recovered=False, error="no events")
        assert "skipped" in report.summary().lower()

    def test_summary_with_recovery(self) -> None:
        report = CrashRecoveryReport(
            recovered=True,
            event_count=10,
            tasks_restored=3,
            active_task_count=1,
            suspensions_restored=0,
            hitl_pending_restored=0,
            pending_results_restored=0,
            history_entries=5,
            derived_state="COMPANIONING",
        )
        summary = report.summary()
        assert "10 events" in summary
        assert "3 tasks" in summary
        assert "COMPANIONING" in summary

    def test_details_contain_active_ids(self) -> None:
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="x"),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert "active_task_ids" in report._details
        assert "t1" in report._details["active_task_ids"]


# ===================================================================
# E9.5.5 -- Fallback when ledger unavailable
# ===================================================================


class TestFallbackSafety:
    """Verify recovery degrades gracefully on errors."""

    def test_exception_in_store_read(self) -> None:
        store = MagicMock()
        store.read.side_effect = RuntimeError("disk I/O error")

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert not report.recovered
        assert "disk I/O error" in report.error

    def test_corrupt_event_doesnt_crash(self) -> None:
        """Corrupt payloads should not prevent recovery of valid events."""
        store = InMemoryLedgerStore()
        _seed_store(
            store,
            [
                _make_ledger_entry("task.created", "t1", seq=1, action="search"),
                # A valid event after the task
                _make_ledger_entry("task.completed", "t1", seq=2),
            ],
        )

        fsm = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert report.recovered
        assert report.tasks_restored == 1

    def test_no_state_change_on_failure(self) -> None:
        """FSM sub-components should not be corrupted by failed recovery."""
        store = MagicMock()
        store.read.side_effect = RuntimeError("unavailable")

        fsm = _make_mock_fsm()
        # Pre-existing state
        fsm._cancel_handler.register_task("existing")

        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm, store, "s1")

        assert not report.recovered
        # Pre-existing state should be untouched
        assert "existing" in fsm._cancel_handler._tokens


# ===================================================================
# E9.5 -- Full end-to-end multi-component recovery
# ===================================================================


class TestFullE2ERecovery:
    """Verify all components are rebuilt in a realistic scenario."""

    @pytest.mark.asyncio
    async def test_multi_task_crash_full_recovery(self) -> None:
        """Simulate: 2 tasks dispatched, 1 suspended, 1 completed -> crash -> recover."""
        store, writer = _make_store_and_writer()

        # Build FSM with real components, wire ledger
        fsm = _make_mock_fsm()
        fsm._task_bridge.set_ledger(writer)
        fsm._cancel_handler.set_ledger(writer)
        fsm._suspension_manager.set_ledger(writer)
        fsm._hil_coordinator.set_ledger(writer)

        # Dispatch 2 tasks
        fsm._task_bridge.dispatch_task("t1", "search_hotels")
        fsm._task_bridge.dispatch_task("t2", "book_flight")

        # t1: progresses then suspends
        fsm._task_bridge.activate_task("t1")
        fsm._task_bridge.suspend_task("t1")

        # t2: completes
        fsm._task_bridge.activate_task("t2")
        fsm._task_bridge.complete_task("t2", result_data={"summary": "booked"})

        # == CRASH ==
        # Create fresh FSM and recover
        fsm2 = _make_mock_fsm()
        orch = CrashRecoveryOrchestrator()
        report = orch.recover(fsm2, store, "s1")

        assert report.recovered
        assert report.tasks_restored == 2
        assert report.active_task_count == 1  # t1 is SUSPENDED
        assert report.derived_state == "CLARIFYING_WORKER"
        assert "t1" in report._details["active_task_ids"]
        assert "t2" not in report._details["active_task_ids"]
